"""Core GridFinity slicing logic.

The GridFinity system is built on a 42 mm pitch. A bin's outer footprint per
unit is a little under 42 mm (there is a ~0.5 mm gap so bins drop into a
baseplate), but the *repeating period* of the geometry along a grid axis is
exactly 42 mm. That is the key fact this tool relies on:

  * The model's minimum bound along an axis sits on a grid line.
  * Cutting at ``min + k * 42`` for integer ``k`` lands on a grid line.
  * Two cut planes an exact multiple of 42 mm apart see the *same phase* of the
    repeating geometry, so their cross-sections are identical -- which means the
    two remaining pieces weld back together with no gap and no overhang.

So "remove a 42 mm chunk and rejoin" reduces to: slice out the slab between two
grid-aligned planes, slide the far piece back by the slab width, and union.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh

GRID = 42.0  # GridFinity pitch in millimetres (X/Y)
Z_UNIT = 7.0  # GridFinity vertical height unit in millimetres (Z); 0.5U = 3.5 mm
AXES = {"x": 0, "y": 1, "z": 2}


def axis_index(axis: str) -> int:
    """Map 'x'/'y'/'z' (any case) to 0/1/2."""
    try:
        return AXES[axis.lower()]
    except KeyError:
        raise ValueError(f"axis must be one of x, y, z (got {axis!r})") from None


@dataclass
class GridInfo:
    """Description of how a mesh maps onto the 42 mm grid."""

    size: np.ndarray          # bounding-box extents (x, y, z) in mm
    lo: np.ndarray            # bounding-box minimum corner
    hi: np.ndarray            # bounding-box maximum corner
    units: tuple[int, int, int]   # whole 42 mm cells along x, y, z
    remainder: np.ndarray     # leftover mm after the whole cells, per axis

    def cells(self, axis: str) -> int:
        return self.units[axis_index(axis)]

    def describe(self) -> str:
        x, y, z = self.size
        ux, uy, uz = self.units
        rem = self.remainder
        lines = [
            f"Bounding box : {x:.2f} x {y:.2f} x {z:.2f} mm",
            f"Grid (42 mm) : {ux} x {uy} units in XY  (Z = {z:.2f} mm)",
        ]
        for ax, n, r in zip("xy", (ux, uy), rem[:2]):
            if abs(r) < 1e-3:
                note = "exact"
            elif r < 0:
                note = f"{-r:.2f} mm short of {n} whole units (footprint gap)"
            else:
                note = f"{r:.2f} mm over {n} whole units (not a clean grid count)"
            lines.append(f"  {ax.upper()}: {n} unit(s), {note}")
        return "\n".join(lines)


def load_mesh(path: str | Path) -> trimesh.Trimesh:
    """Load an STL or 3MF file as a single concatenated Trimesh."""
    mesh = trimesh.load(path, force="mesh")
    if not isinstance(mesh, trimesh.Trimesh) or mesh.is_empty:
        raise ValueError(f"could not load a mesh from {path}")
    return mesh


def inspect(mesh: trimesh.Trimesh, *, tol: float = 0.5) -> GridInfo:
    """Measure the mesh against the 42 mm grid.

    ``tol`` (mm) is how much under a full multiple of 42 still counts as a whole
    unit -- accommodating the GridFinity footprint gap (a 3-wide bin measures
    ~125.5 mm, i.e. 3*42 - 0.5).
    """
    lo, hi = mesh.bounds
    size = hi - lo
    units = []
    remainder = []
    for s in size:
        n = int(np.floor((s + tol) / GRID))
        units.append(max(n, 0))
        remainder.append(s - n * GRID)
    return GridInfo(
        size=size,
        lo=lo,
        hi=hi,
        units=(units[0], units[1], units[2]),
        remainder=np.array(remainder),
    )


def cut_planes(mesh: trimesh.Trimesh, axis: str, cell: int, count: int) -> tuple[float, float]:
    """Return the (start, end) coordinates of the slab to remove.

    ``cell`` is the 0-based index of the first 42 mm cell to remove (measured
    from the mesh minimum along ``axis``); ``count`` is how many cells.
    """
    if count < 1:
        raise ValueError("count must be >= 1")
    ax = axis_index(axis)
    info = inspect(mesh)
    total = info.units[ax]
    if total < count:
        raise ValueError(
            f"mesh is only {total} unit(s) along {axis.upper()}; cannot remove {count}"
        )
    if not (0 <= cell <= total - count):
        raise ValueError(
            f"cell must be in 0..{total - count} for count={count} "
            f"(mesh has {total} units along {axis.upper()})"
        )
    lo = mesh.bounds[0][ax]
    start = lo + cell * GRID
    end = start + count * GRID
    return start, end


def _slice_keep(mesh: trimesh.Trimesh, axis_vec: np.ndarray, origin: np.ndarray):
    """Slice and keep the side the normal points toward, capping the cut flat.

    Returns None when the kept side is empty (e.g. the cut plane sits on the
    mesh boundary), which is a legitimate case when removing the first or last
    cell.
    """
    piece = mesh.slice_plane(plane_origin=origin, plane_normal=axis_vec, cap=True)
    if piece is None or piece.is_empty:
        return None
    return piece


def _remove_slab(
    mesh: trimesh.Trimesh,
    ax: int,
    start: float,
    end: float,
    *,
    weld: bool = True,
) -> trimesh.Trimesh:
    """Remove the slab between ``start`` and ``end`` along axis ``ax`` and rejoin.

    ``start`` and ``end`` are absolute coordinates along the axis. Everything
    below ``start`` is kept in place; everything above ``end`` is slid back by
    the slab width so its cut face meets the near piece's, then the two are
    welded (or merely concatenated when ``weld`` is False).
    """
    width = end - start

    normal = np.zeros(3)
    normal[ax] = 1.0

    # Keep everything below `start` (normal pointing -axis) ...
    left = _slice_keep(mesh, -normal, _origin(ax, start))
    # ... and everything above `end` (normal pointing +axis).
    right = _slice_keep(mesh, normal, _origin(ax, end))

    # A plane sitting on the mesh boundary leaves only one piece; just shift it.
    if left is None and right is None:
        raise ValueError("slice produced no geometry -- check the cut bounds")

    shift = np.zeros(3)
    shift[ax] = -width
    if right is not None:
        # Slide the far piece back so its cut face meets the near piece's.
        right.apply_translation(shift)

    if left is None:
        return right
    if right is None:
        return left

    if not weld:
        return trimesh.util.concatenate([left, right])

    joined = trimesh.boolean.union([left, right])
    if joined is None or joined.is_empty:
        # Fall back to a plain concatenation rather than failing outright.
        return trimesh.util.concatenate([left, right])
    return joined


def cut(
    mesh: trimesh.Trimesh,
    axis: str,
    cell: int,
    count: int = 1,
    *,
    weld: bool = True,
) -> trimesh.Trimesh:
    """Remove ``count`` 42 mm cells starting at ``cell`` along ``axis`` and rejoin.

    When ``weld`` is True (default) the two remaining pieces are boolean-unioned
    into a single watertight mesh. When False they are merely concatenated --
    faster, and a useful fallback if a boolean backend is unavailable.
    """
    ax = axis_index(axis)
    start, end = cut_planes(mesh, axis, cell, count)
    return _remove_slab(mesh, ax, start, end, weld=weld)


def cut_z(
    mesh: trimesh.Trimesh,
    z_start: float,
    z_end: float,
    *,
    weld: bool = True,
) -> trimesh.Trimesh:
    """Remove the Z section between ``z_start`` and ``z_end`` and rejoin.

    Unlike :func:`cut`, this is not tied to the 42 mm grid: the two heights are
    arbitrary absolute Z coordinates. The section between them is cut out, the
    upper piece is dropped by the section height so its cut face meets the lower
    piece's, and the two are welded back together.

    It is the caller's responsibility to pick heights where the cross-sections
    match (e.g. within a straight-walled region) so the weld is clean -- the
    geometry does not repeat on a fixed pitch the way it does in X/Y.

    Chopping the top (or bottom) off is intentionally out of scope: pick two
    interior heights so both pieces survive. A plane that lands on the boundary
    still works, but degrades to a plain chop.
    """
    z_start = float(z_start)
    z_end = float(z_end)
    lo = float(mesh.bounds[0][2])
    hi = float(mesh.bounds[1][2])
    if z_end < z_start:
        z_start, z_end = z_end, z_start
    if z_end - z_start <= 0:
        raise ValueError("the two Z heights must differ")
    tol = 1e-6
    if z_start < lo - tol or z_end > hi + tol:
        raise ValueError(
            f"Z section {z_start:.3f}..{z_end:.3f} mm lies outside the mesh "
            f"(Z spans {lo:.3f}..{hi:.3f} mm)"
        )
    return _remove_slab(mesh, AXES["z"], z_start, z_end, weld=weld)


def stretch_z(
    mesh: trimesh.Trimesh,
    z_start: float,
    z_end: float,
    copies: int = 1,
    *,
    weld: bool = True,
) -> trimesh.Trimesh:
    """Duplicate the Z section between ``z_start`` and ``z_end`` to make the mesh taller.

    The section between the two heights is copied ``copies`` times and stacked in
    place: everything below ``z_start`` stays put, ``copies`` fresh copies of the
    section are inserted, and everything from ``z_start`` up (the original section
    included) is lifted by ``copies * height``. The result is ``copies * height``
    mm taller.

    Like :func:`cut_z`, this is grid-independent and it is the caller's job to
    pick a section whose top and bottom cross-sections match (e.g. a stretch of
    straight wall) so the inserted copies weld seamlessly. Picking a whole number
    of 7 mm Gridfinity units keeps the taller result a valid stacking height.
    """
    z_start = float(z_start)
    z_end = float(z_end)
    if z_end < z_start:
        z_start, z_end = z_end, z_start
    if z_end - z_start <= 0:
        raise ValueError("the two Z heights must differ")
    if copies < 1:
        raise ValueError("copies must be >= 1")
    lo = float(mesh.bounds[0][2])
    hi = float(mesh.bounds[1][2])
    tol = 1e-6
    if z_start < lo - tol or z_end > hi + tol:
        raise ValueError(
            f"Z section {z_start:.3f}..{z_end:.3f} mm lies outside the mesh "
            f"(Z spans {lo:.3f}..{hi:.3f} mm)"
        )

    ax = AXES["z"]
    height = z_end - z_start
    normal = np.zeros(3)
    normal[ax] = 1.0

    above = _slice_keep(mesh, normal, _origin(ax, z_start))   # z >= z_start
    if above is None:
        raise ValueError("no geometry at or above the section start")
    section = _slice_keep(above, -normal, _origin(ax, z_end))  # the slab itself
    if section is None:
        raise ValueError("the selected section is empty")
    lower = _slice_keep(mesh, -normal, _origin(ax, z_start))   # z <= z_start

    # Lift the whole upper part (its own copy of the section included) clear of
    # the gap, then fill the gap with `copies` fresh copies of the section.
    upper = above
    upper.apply_translation(_origin(ax, copies * height))

    pieces: list[trimesh.Trimesh] = []
    if lower is not None:
        pieces.append(lower)
    for j in range(copies):
        copy = section.copy()
        copy.apply_translation(_origin(ax, j * height))
        pieces.append(copy)
    pieces.append(upper)

    if not weld:
        return trimesh.util.concatenate(pieces)

    joined = trimesh.boolean.union(pieces)
    if joined is None or joined.is_empty:
        return trimesh.util.concatenate(pieces)
    return joined


def _origin(ax: int, value: float) -> np.ndarray:
    o = np.zeros(3)
    o[ax] = value
    return o


def export_mesh(mesh: trimesh.Trimesh, path: str | Path) -> None:
    """Write a mesh to STL or 3MF based on the file extension."""
    suffix = Path(path).suffix.lower()
    if suffix not in (".stl", ".3mf"):
        raise ValueError(f"output must be .stl or .3mf (got {suffix or 'no extension'})")
    mesh.export(path)

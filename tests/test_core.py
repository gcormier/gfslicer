"""Tests for the GridFinity slicing core.

We build synthetic meshes whose geometry repeats with a true 42 mm period so the
weld is expected to be perfect, and assert the exact-length and watertightness
guarantees the tool promises.
"""

import numpy as np
import pytest
import trimesh

from gridfinity_slicer import core


def make_bar(units_x: int, footprint: float = 41.5, height: float = 20.0) -> trimesh.Trimesh:
    """A box `units_x` cells long on X with a real GridFinity-style footprint.

    Width along X is units_x*42 - 0.5 (the footprint gap), so its bounding box
    is *not* a clean multiple of 42, exercising the tolerance handling.
    """
    length_x = units_x * core.GRID - (core.GRID - footprint)
    box = trimesh.creation.box(extents=(length_x, footprint, height))
    # Move so the min corner sits at the origin (a grid line).
    box.apply_translation(-box.bounds[0])
    return box


def make_periodic_bar(units_x: int) -> trimesh.Trimesh:
    """A bar with a notch repeating every 42 mm, so cross-sections at grid lines match."""
    parts = []
    for i in range(units_x):
        cell = trimesh.creation.box(extents=(42.0, 40.0, 20.0))
        cell.apply_translation((i * 42.0 + 21.0, 20.0, 10.0))
        # A bump centred in each cell -> geometry has exact 42 mm period.
        bump = trimesh.creation.box(extents=(10.0, 10.0, 10.0))
        bump.apply_translation((i * 42.0 + 21.0, 20.0, 25.0))
        parts.append(trimesh.boolean.union([cell, bump]))
    bar = trimesh.boolean.union(parts)
    bar.apply_translation(-bar.bounds[0])
    return bar


def test_inspect_counts_units_with_footprint_gap():
    bar = make_bar(3)
    info = core.inspect(bar)
    assert info.units[0] == 3
    assert info.units[1] == 1
    # ~0.5 mm short of a clean multiple, but still counted as whole units.
    assert info.remainder[0] == pytest.approx(-0.5, abs=1e-3)


def test_cut_removes_exactly_42mm():
    bar = make_bar(4)
    before = bar.bounds[1][0] - bar.bounds[0][0]
    result = core.cut(bar, axis="x", cell=1, count=1)
    after = result.bounds[1][0] - result.bounds[0][0]
    assert before - after == pytest.approx(core.GRID, abs=1e-6)


def test_cut_multiple_units():
    bar = make_bar(5)
    before = bar.bounds[1][0] - bar.bounds[0][0]
    result = core.cut(bar, axis="x", cell=1, count=2)
    after = result.bounds[1][0] - result.bounds[0][0]
    assert before - after == pytest.approx(2 * core.GRID, abs=1e-6)


def test_weld_is_watertight_on_periodic_geometry():
    bar = make_periodic_bar(4)
    assert bar.is_watertight
    result = core.cut(bar, axis="x", cell=1, count=1, weld=True)
    assert result.is_watertight
    assert result.volume < bar.volume  # material was removed


def test_cut_volume_drops_by_one_cell_for_uniform_bar():
    bar = make_bar(4)
    result = core.cut(bar, axis="x", cell=2, count=1, weld=True)
    # Uniform cross-section: removing one cell removes ~ one cell of volume.
    cell_volume = core.GRID * 41.5 * 20.0
    assert bar.volume - result.volume == pytest.approx(cell_volume, rel=1e-3)


def test_cell_out_of_range_raises():
    bar = make_bar(3)
    with pytest.raises(ValueError):
        core.cut(bar, axis="x", cell=3, count=1)
    with pytest.raises(ValueError):
        core.cut(bar, axis="x", cell=2, count=2)


def test_too_many_units_raises():
    bar = make_bar(2)
    with pytest.raises(ValueError):
        core.cut(bar, axis="x", cell=0, count=3)


def test_cut_z_removes_exact_section():
    # A tall straight-walled bar: any horizontal section welds cleanly.
    bar = trimesh.creation.box(extents=(41.5, 41.5, 100.0))
    bar.apply_translation(-bar.bounds[0])
    before = bar.bounds[1][2] - bar.bounds[0][2]
    result = core.cut_z(bar, 30.0, 50.0, weld=True)
    after = result.bounds[1][2] - result.bounds[0][2]
    assert before - after == pytest.approx(20.0, abs=1e-6)
    assert result.is_watertight
    assert result.volume < bar.volume


def test_cut_z_accepts_unordered_heights():
    bar = trimesh.creation.box(extents=(20.0, 20.0, 60.0))
    bar.apply_translation(-bar.bounds[0])
    a = core.cut_z(bar, 40.0, 10.0)
    b = core.cut_z(bar, 10.0, 40.0)
    span_a = a.bounds[1][2] - a.bounds[0][2]
    span_b = b.bounds[1][2] - b.bounds[0][2]
    assert span_a == pytest.approx(span_b, abs=1e-6)
    assert span_a == pytest.approx(30.0, abs=1e-6)


def test_cut_z_volume_drops_by_section_for_uniform_bar():
    bar = trimesh.creation.box(extents=(30.0, 25.0, 80.0))
    bar.apply_translation(-bar.bounds[0])
    result = core.cut_z(bar, 20.0, 35.0, weld=True)
    section_volume = 30.0 * 25.0 * 15.0
    assert bar.volume - result.volume == pytest.approx(section_volume, rel=1e-3)


def test_cut_z_equal_heights_raise():
    bar = trimesh.creation.box(extents=(20.0, 20.0, 40.0))
    bar.apply_translation(-bar.bounds[0])
    with pytest.raises(ValueError):
        core.cut_z(bar, 10.0, 10.0)


def test_cut_z_out_of_bounds_raises():
    bar = trimesh.creation.box(extents=(20.0, 20.0, 40.0))
    bar.apply_translation(-bar.bounds[0])
    with pytest.raises(ValueError):
        core.cut_z(bar, 10.0, 60.0)


def test_y_axis_cut():
    bar = make_bar(2)  # 2 on X
    bar_y = bar.copy()
    bar_y.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, (0, 0, 1)))
    bar_y.apply_translation(-bar_y.bounds[0])
    info = core.inspect(bar_y)
    assert info.units[1] == 2  # now 2 along Y
    result = core.cut(bar_y, axis="y", cell=0, count=1)
    after = result.bounds[1][1] - result.bounds[0][1]
    before = bar_y.bounds[1][1] - bar_y.bounds[0][1]
    assert before - after == pytest.approx(core.GRID, abs=1e-6)

# GridFinity Slicer

Cut an exact **N × 42 mm** chunk out of a GridFinity mesh (STL or 3MF) along the
X or Y axis and weld the remaining pieces back into a single watertight model.
Turn a 3×2 bin into a 2×2, shorten a 5-wide tray to a 3-wide, etc.

## Why it works

GridFinity is built on a **42 mm pitch**. A unit's outer footprint is ~41.5 mm
(there's a 0.5 mm gap so bins drop into a baseplate), but the *repeating period*
of the geometry along a grid axis is exactly 42 mm. So:

* the model's minimum bound sits on a grid line,
* cutting at `min + k·42` lands on a grid line, and
* two planes an exact multiple of 42 mm apart see the **same phase** of the
  geometry — identical cross-sections — so the cut faces weld with no gap.

The tool slices out the slab between two grid-aligned planes, slides the far
piece back by the slab width, and boolean-unions the two halves
(via [`manifold3d`](https://github.com/elalish/manifold)).

## Install

Uses [uv](https://docs.astral.sh/uv/):

```bash
uv sync --extra web      # omit --extra web for the CLI only
```

## CLI

```bash
# Inspect: how many 42 mm units is this model?
uv run gridfinity-slicer info bin.stl

# Remove one 42 mm cell along X, starting at cell index 1 (the 2nd cell)
uv run gridfinity-slicer cut bin.stl --axis x --cell 1 --count 1 -o bin_smaller.3mf

# Remove two cells along Y
uv run gridfinity-slicer cut bin.3mf -a y -c 0 -n 2
```

`cut` options:

| flag | meaning | default |
|------|---------|---------|
| `-a, --axis {x,y}` | axis to cut along | `x` |
| `-c, --cell N` | 0-based index of the first 42 mm cell to remove | `0` |
| `-n, --count N` | number of 42 mm cells to remove | `1` |
| `-o, --output FILE` | output `.stl` or `.3mf` | derived from input |
| `--no-weld` | concatenate instead of boolean-welding (faster fallback) | off |

Output format follows the output file's extension (`.stl` or `.3mf`).

## Web UI

```bash
uv run gridfinity-slicer-web        # serves http://127.0.0.1:8000
```

Upload an STL/3MF, see it rendered in 3D with the 42 mm slab to remove
highlighted in red, pick axis / cell / count, then download the rejoined mesh.

## How a cut maps to cells

A 5-unit-wide bar, cutting `--cell 1 --count 2` along X:

```
cells:   | 0 | 1 | 2 | 3 | 4 |      (each 42 mm)
remove:      |^^^^^^^|              cells 1 and 2
result:  | 0 | 3 | 4 |             -> 3 units wide, welded at the cut
```

Removing cell `0` (or the last cell) leaves a single piece, which is just
returned shifted — no weld needed.

## Development

```bash
uv run pytest            # core + web tests
```

The tests build synthetic bars with a true 42 mm period and assert that a cut
removes *exactly* 42 mm and leaves a watertight result.

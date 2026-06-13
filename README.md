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

# Remove an arbitrary Z section between 25 mm and 55 mm and weld the rest
uv run gridfinity-slicer cutz bin.stl --from 25 --to 55 -o bin_shorter.stl
```

`cut` options:

| flag | meaning | default |
|------|---------|---------|
| `-a, --axis {x,y}` | axis to cut along | `x` |
| `-c, --cell N` | 0-based index of the first 42 mm cell to remove | `0` |
| `-n, --count N` | number of 42 mm cells to remove | `1` |
| `-o, --output FILE` | output `.stl` or `.3mf` | derived from input |
| `--no-weld` | concatenate instead of boolean-welding (faster fallback) | off |

`cutz` options:

| flag | meaning | default |
|------|---------|---------|
| `-f, --from MM` | lower Z height of the section to remove | required |
| `-t, --to MM` | upper Z height of the section to remove | required |
| `-o, --output FILE` | output `.stl` or `.3mf` | derived from input |
| `--no-weld` | concatenate instead of boolean-welding (faster fallback) | off |

Output format follows the output file's extension (`.stl` or `.3mf`).

## Cutting along Z

`cutz` removes the slab between two arbitrary Z heights and welds the upper
piece down onto the lower one — handy for shortening the *height* of a bin
(e.g. dropping a tall bin's wall) without re-modelling it. Unlike X/Y, Z is
**not** tied to the 42 mm grid, so you give two absolute heights in millimetres.

Because the geometry doesn't repeat on a fixed pitch in Z, pick two heights with
matching cross-sections — typically anywhere in a straight-walled region — so the
cut faces weld with no gap or overhang. Slicing the top clean off isn't the goal
here (any printing slicer can split an object); `cutz` is for taking a slice out
of the *middle* and gluing the ends back together.

## Web UI

```bash
uv run gridfinity-slicer-web        # serves http://127.0.0.1:8000
```

Upload an STL/3MF, see it rendered in 3D with the slab to remove highlighted in
red, pick axis / cell / count, then download the rejoined mesh. Choose the **Z**
axis to switch to a height-based cut: enter two Z heights and the slab between
them is removed and welded back together.

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

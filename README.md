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

# Make a bin taller: duplicate the 25–32 mm section (1U = 7 mm) twice
uv run gridfinity-slicer stretchz bin.stl --from 25 --to 32 --copies 2 -o bin_taller.stl
```

`cut` options:

| flag | meaning | default |
|------|---------|---------|
| `-a, --axis {x,y}` | axis to cut along | `x` |
| `-c, --cell N` | 0-based index of the first 42 mm cell to remove | `0` |
| `-n, --count N` | number of 42 mm cells to remove | `1` |
| `-o, --output FILE` | output `.stl` or `.3mf` | derived from input |
| `--no-weld` | concatenate instead of boolean-welding (faster fallback) | off |

`cutz` / `stretchz` options:

| flag | meaning | default |
|------|---------|---------|
| `-f, --from MM` | lower Z height of the section | required |
| `-t, --to MM` | upper Z height of the section | required |
| `-n, --copies N` | (`stretchz` only) extra copies of the section to insert | `1` |
| `-o, --output FILE` | output `.stl` or `.3mf` | derived from input |
| `--no-weld` | concatenate instead of boolean-welding (faster fallback) | off |

Output format follows the output file's extension (`.stl` or `.3mf`).

## Adjusting height along Z

Z is the **vertical** axis. GridFinity's vertical pitch is **7 mm per height
unit (1U)**, so heights here move in 1U / ½U (3.5 mm) steps rather than the 42 mm
X/Y grid. Two commands work on a Z *section* — the slab between two heights:

* **`cutz`** removes the section and welds the upper piece down onto the lower one
  — shortens a bin without re-modelling it.
* **`stretchz`** duplicates the section `--copies` times and stacks the copies in
  place — makes a bin taller. Each copy is real geometry lifted from the model,
  so the inserted walls match exactly.

Z is **not** tied to the 42 mm grid, so you give absolute heights in mm. Because
the geometry doesn't repeat on a fixed pitch in Z, pick a section whose top and
bottom cross-sections match — typically anywhere in a straight-walled region — so
the seams weld with no gap or overhang. Choosing a whole number of 7 mm units
keeps the result a valid stacking height. Slicing the top clean off isn't the
goal (any printing slicer can split an object); these are for taking a slice out
of the *middle*, or inserting one, and gluing the ends back together.

In the web UI, pick the **Z** axis, then toggle **Remove** / **Stretch**; the
½U / 1U buttons nudge the section size and the readout shows it in both mm and U.

## Web UI

```bash
uv run gridfinity-slicer-web        # serves http://127.0.0.1:8000
```

Upload an STL/3MF, see it rendered in 3D with the slab to remove highlighted in
red, pick axis / cell / count, then download the rejoined mesh. Choose the **Z**
axis to switch to height-based edits (in 7 mm / 3.5 mm Gridfinity units) and
**Remove** or **Stretch** a section — see *Adjusting height along Z* below.

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

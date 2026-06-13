"""Command-line interface for the GridFinity slicer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import core


def _cmd_info(args: argparse.Namespace) -> int:
    mesh = core.load_mesh(args.input)
    info = core.inspect(mesh)
    print(f"{args.input}")
    print(info.describe())
    print(f"Watertight   : {mesh.is_watertight}")
    return 0


def _cmd_cut(args: argparse.Namespace) -> int:
    mesh = core.load_mesh(args.input)
    info = core.inspect(mesh)

    out = Path(args.output) if args.output else _default_output(args.input, args)

    result = core.cut(
        mesh,
        axis=args.axis,
        cell=args.cell,
        count=args.count,
        weld=not args.no_weld,
    )

    core.export_mesh(result, out)

    removed = args.count * core.GRID
    new_units = info.cells(args.axis) - args.count
    print(f"Removed {args.count} unit(s) ({removed:.0f} mm) along {args.axis.upper()} "
          f"starting at cell {args.cell}.")
    print(f"{args.axis.upper()} units: {info.cells(args.axis)} -> {new_units}")
    print(f"Watertight result: {result.is_watertight}")
    print(f"Wrote {out}")
    return 0


def _cmd_cutz(args: argparse.Namespace) -> int:
    mesh = core.load_mesh(args.input)

    if args.output:
        out = Path(args.output)
    else:
        p = Path(args.input)
        stem = f"{p.stem}_cutz_{args.from_z:g}-{args.to_z:g}"
        out = p.with_name(stem + p.suffix)

    result = core.cut_z(
        mesh,
        z_start=args.from_z,
        z_end=args.to_z,
        weld=not args.no_weld,
    )

    core.export_mesh(result, out)

    lo, hi = sorted((args.from_z, args.to_z))
    removed = hi - lo
    before = mesh.bounds[1][2] - mesh.bounds[0][2]
    print(f"Removed {removed:.2f} mm Z section ({lo:.2f} -> {hi:.2f} mm).")
    print(f"Z height: {before:.2f} -> {before - removed:.2f} mm")
    print(f"Watertight result: {result.is_watertight}")
    print(f"Wrote {out}")
    return 0


def _cmd_stretchz(args: argparse.Namespace) -> int:
    mesh = core.load_mesh(args.input)

    if args.output:
        out = Path(args.output)
    else:
        p = Path(args.input)
        stem = f"{p.stem}_stretchz_{args.from_z:g}-{args.to_z:g}x{args.copies}"
        out = p.with_name(stem + p.suffix)

    result = core.stretch_z(
        mesh,
        z_start=args.from_z,
        z_end=args.to_z,
        copies=args.copies,
        weld=not args.no_weld,
    )

    core.export_mesh(result, out)

    lo, hi = sorted((args.from_z, args.to_z))
    added = (hi - lo) * args.copies
    before = mesh.bounds[1][2] - mesh.bounds[0][2]
    print(f"Inserted {args.copies} copy(ies) of the {hi - lo:.2f} mm section "
          f"({lo:.2f} -> {hi:.2f} mm); added {added:.2f} mm.")
    print(f"Z height: {before:.2f} -> {before + added:.2f} mm")
    print(f"Watertight result: {result.is_watertight}")
    print(f"Wrote {out}")
    return 0


def _default_output(input_path: str, args: argparse.Namespace) -> Path:
    p = Path(input_path)
    stem = f"{p.stem}_cut_{args.axis}{args.cell}x{args.count}"
    return p.with_name(stem + p.suffix)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gridfinity-slicer",
        description="Cut exact 42 mm GridFinity units out of a mesh and weld it back together.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_info = sub.add_parser("info", help="show how a mesh maps onto the 42 mm grid")
    p_info.add_argument("input", help="input STL or 3MF file")
    p_info.set_defaults(func=_cmd_info)

    p_cut = sub.add_parser("cut", help="remove one or more 42 mm cells and rejoin")
    p_cut.add_argument("input", help="input STL or 3MF file")
    p_cut.add_argument("-a", "--axis", choices=["x", "y"], default="x",
                       help="axis to cut along (default: x)")
    p_cut.add_argument("-c", "--cell", type=int, default=0,
                       help="0-based index of the first 42 mm cell to remove (default: 0)")
    p_cut.add_argument("-n", "--count", type=int, default=1,
                       help="number of 42 mm cells to remove (default: 1)")
    p_cut.add_argument("-o", "--output", help="output file (.stl or .3mf); default derives from input")
    p_cut.add_argument("--no-weld", action="store_true",
                       help="concatenate the pieces instead of boolean-welding them")
    p_cut.set_defaults(func=_cmd_cut)

    p_cutz = sub.add_parser(
        "cutz",
        help="remove an arbitrary Z section (two heights) and rejoin",
    )
    p_cutz.add_argument("input", help="input STL or 3MF file")
    p_cutz.add_argument("-f", "--from", dest="from_z", type=float, required=True,
                        help="lower Z height (mm) of the section to remove")
    p_cutz.add_argument("-t", "--to", dest="to_z", type=float, required=True,
                        help="upper Z height (mm) of the section to remove")
    p_cutz.add_argument("-o", "--output", help="output file (.stl or .3mf); default derives from input")
    p_cutz.add_argument("--no-weld", action="store_true",
                        help="concatenate the pieces instead of boolean-welding them")
    p_cutz.set_defaults(func=_cmd_cutz)

    p_stretchz = sub.add_parser(
        "stretchz",
        help="duplicate an arbitrary Z section to make the model taller",
    )
    p_stretchz.add_argument("input", help="input STL or 3MF file")
    p_stretchz.add_argument("-f", "--from", dest="from_z", type=float, required=True,
                            help="lower Z height (mm) of the section to duplicate")
    p_stretchz.add_argument("-t", "--to", dest="to_z", type=float, required=True,
                            help="upper Z height (mm) of the section to duplicate")
    p_stretchz.add_argument("-n", "--copies", type=int, default=1,
                            help="number of extra copies of the section to insert (default: 1)")
    p_stretchz.add_argument("-o", "--output", help="output file (.stl or .3mf); default derives from input")
    p_stretchz.add_argument("--no-weld", action="store_true",
                            help="concatenate the pieces instead of boolean-welding them")
    p_stretchz.set_defaults(func=_cmd_stretchz)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import json
from pathlib import Path
import sys

from .formats import FormatError
from .repair import Repair, load_recipe, write_repair


def main(argv=None):
    parser = argparse.ArgumentParser(description="Targeted Starfield position repair; originals are never overwritten.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "plan", "repair"):
        p = sub.add_parser(name)
        p.add_argument("save", type=Path)
        p.add_argument("--recipe", type=Path, help="JSON recipe; defaults to the experimental Anchorpoint position repair")
        if name == "repair":
            p.add_argument("--output", required=True, type=Path, help="New .sfs file; existing files are refused")
    args = parser.parse_args(argv)
    try:
        recipe = load_recipe(args.recipe)
        if args.command == "repair":
            result = write_repair(args.save, args.output, recipe)
        else:
            result = Repair(args.save.read_bytes(), recipe).report()
            result["writesPerformed"] = False
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (FormatError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, allow_nan=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

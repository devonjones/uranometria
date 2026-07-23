"""Command-line wrapper: uranometria config.yaml [-o output.html]"""

import argparse
import os
import sys

import yaml

from .core import SkymapError, generate


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="uranometria", description="Generate an HTML sky chart from a YAML object list."
    )
    ap.add_argument("config", help="YAML config file")
    ap.add_argument("-o", "--output", help="output HTML path (default: <config>.html)")
    ap.add_argument(
        "--offline",
        action="store_true",
        help="never call the online Sesame resolver for unknown designations",
    )
    ap.add_argument(
        "--mirror",
        action="store_true",
        help="mirrored (celestial-globe) orientation instead of the default "
        "sky view; same as 'mirror: true' in the config",
    )
    args = ap.parse_args(argv)

    out = args.output or os.path.splitext(args.config)[0] + ".html"
    try:
        with open(args.config) as f:
            cfg = yaml.safe_load(f)
        if not isinstance(cfg, dict):
            raise SkymapError(f"{args.config} is not a mapping")
        if args.mirror:
            cfg["mirror"] = True
        warnings = generate(cfg, out, allow_online=not args.offline)
    except (SkymapError, FileNotFoundError, ValueError) as e:
        sys.exit(f"error: {e}")
    for w in warnings:
        print("note:", w, file=sys.stderr)
    size = os.path.getsize(out) // 1024
    print(f"wrote {out} ({size} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

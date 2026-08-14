#!/usr/bin/env python3
"""Create a deterministic RKNN calibration dataset list."""

import argparse
import random
from pathlib import Path


DEFAULT_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".npy", ".png"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a deterministic RKNN calibration list")
    parser.add_argument("source", type=Path, help="directory containing representative inputs")
    parser.add_argument("output", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--relative", action="store_true", help="write paths relative to the list file")
    args = parser.parse_args()

    if not args.source.is_dir():
        parser.error(f"source directory not found: {args.source}")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    iterator = args.source.rglob("*") if args.recursive else args.source.glob("*")
    files = sorted(
        (item.resolve() for item in iterator if item.is_file() and item.suffix.lower() in DEFAULT_EXTENSIONS),
        key=lambda item: str(item),
    )
    if not files:
        parser.error("no supported calibration files found")
    if args.limit is not None and len(files) > args.limit:
        random.Random(args.seed).shuffle(files)
        files = sorted(files[: args.limit], key=lambda item: str(item))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_parent = args.output.resolve().parent
    lines = []
    for item in files:
        if args.relative:
            try:
                line = str(item.relative_to(output_parent))
            except ValueError:
                parser.error("--relative requires source files below the dataset list directory")
        else:
            line = str(item)
        if any(character.isspace() for character in line):
            parser.error(f"RKNN dataset paths must not contain whitespace: {line}")
        lines.append(line)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} calibration samples to {args.output}")


if __name__ == "__main__":
    main()

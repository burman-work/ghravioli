#!/usr/bin/env python3
"""Discover exactly one wheel and one source distribution in a build directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def discover(dist: Path) -> dict[str, Path]:
    """Return resolved artifact paths, failing closed on missing or duplicate files."""

    directory = dist.expanduser().resolve()
    if not directory.is_dir():
        raise ValueError(f"distribution directory does not exist: {dist}")
    wheels = sorted(path.resolve() for path in directory.glob("*.whl") if path.is_file())
    sdists = sorted(path.resolve() for path in directory.glob("*.tar.gz") if path.is_file())
    if len(wheels) != 1:
        raise ValueError(f"expected exactly one wheel in {directory}; found {len(wheels)}")
    if len(sdists) != 1:
        raise ValueError(
            f"expected exactly one source distribution in {directory}; found {len(sdists)}"
        )
    return {"wheel": wheels[0], "sdist": sdists[0]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="emit a JSON object")
    output.add_argument(
        "--github-output",
        type=Path,
        metavar="PATH",
        help="append wheel and sdist paths to a GitHub Actions output file",
    )
    arguments = parser.parse_args()
    try:
        artifacts = discover(arguments.dist)
        serializable = {key: str(value) for key, value in artifacts.items()}
        if arguments.github_output is not None:
            with arguments.github_output.open("a", encoding="utf-8", newline="\n") as output_file:
                for key in ("wheel", "sdist"):
                    output_file.write(f"{key}={serializable[key]}\n")
        elif arguments.json:
            json.dump(serializable, sys.stdout, sort_keys=True)
            sys.stdout.write("\n")
        else:
            for key in ("wheel", "sdist"):
                print(f"{key}: {serializable[key]}")
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

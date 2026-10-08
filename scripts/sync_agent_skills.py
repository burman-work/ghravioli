#!/usr/bin/env python3
"""Synchronize the canonical skill into Codex and Claude discovery paths."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


SKILL_NAME = "grasshopper-python-components"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPOSITORY_ROOT / "skills" / SKILL_NAME
TARGETS = (
    REPOSITORY_ROOT / ".agents" / "skills" / SKILL_NAME,
    REPOSITORY_ROOT / ".claude" / "skills" / SKILL_NAME,
)
INCIDENTAL_NAMES = frozenset({".DS_Store", "Thumbs.db"})


def is_incidental(path: Path) -> bool:
    """Return whether a relative path is operating-system metadata."""

    return any(part in INCIDENTAL_NAMES or part.startswith("._") for part in path.parts)


def snapshot(directory: Path) -> dict[str, bytes]:
    if not directory.is_dir():
        return {}
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file() and not is_incidental(path.relative_to(directory))
    }


def stale_targets() -> list[Path]:
    expected = snapshot(SOURCE)
    return [target for target in TARGETS if snapshot(target) != expected]


def synchronize() -> None:
    expected_paths = set(snapshot(SOURCE))
    for target in TARGETS:
        target.mkdir(parents=True, exist_ok=True)
        for existing in sorted(target.rglob("*"), reverse=True):
            if existing.is_file() and (
                is_incidental(existing.relative_to(target))
                or existing.relative_to(target).as_posix() not in expected_paths
            ):
                existing.unlink()
            elif existing.is_dir() and not any(existing.iterdir()):
                existing.rmdir()
        for source_file in sorted(SOURCE.rglob("*")):
            if source_file.is_file() and not is_incidental(source_file.relative_to(SOURCE)):
                destination = target / source_file.relative_to(SOURCE)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the Codex or Claude copies differ from the canonical skill",
    )
    args = parser.parse_args()

    if not SOURCE.is_dir():
        parser.error(f"canonical skill is missing: {SOURCE}")

    if args.check:
        stale = stale_targets()
        if stale:
            for path in stale:
                print(f"stale skill copy: {path.relative_to(REPOSITORY_ROOT)}")
            return 1
        print("agent skill copies are synchronized")
        return 0

    synchronize()
    print("synchronized agent skill copies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

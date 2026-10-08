#!/usr/bin/env python3
"""Safely unpack a source distribution and run its bundled verification suite."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


def safe_extract(archive: Path, destination: Path) -> Path:
    """Extract regular files and directories without accepting links or traversal."""

    with tarfile.open(archive, mode="r:gz") as package:
        members = package.getmembers()
        roots: set[str] = set()
        for member in members:
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise ValueError(f"unsafe source distribution path: {member.name!r}")
            roots.add(relative.parts[0])
            if not (member.isdir() or member.isfile()):
                raise ValueError(f"unsupported source distribution member: {member.name!r}")
        if len(roots) != 1:
            raise ValueError("source distribution must have one top-level directory")

        for member in members:
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = package.extractfile(member)
            if source is None:
                raise ValueError(f"cannot read source distribution member: {member.name!r}")
            target.write_bytes(source.read())
    return destination / next(iter(roots))


def run_verification(project: Path) -> None:
    """Run the same checks from inside the extracted artifact."""

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project / "src")
    commands = (
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        [sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests", "examples"],
        [sys.executable, "scripts/sync_agent_skills.py", "--check"],
    )
    for command in commands:
        subprocess.run(command, cwd=project, env=environment, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    arguments = parser.parse_args()
    archive = arguments.archive.expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix="ghravioli-sdist-") as directory:
        project = safe_extract(archive, Path(directory))
        run_verification(project)
    print(f"verified source distribution: {archive.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

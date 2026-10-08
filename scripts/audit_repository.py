#!/usr/bin/env python3
"""Scan the current repository tree or all reachable Git blobs for disclosures."""

from __future__ import annotations

import argparse
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRECTORIES = frozenset({".git", ".venv", "build", "dist", "__pycache__"})
SECRET_PATTERNS = (
    ("macOS user path", re.compile("/" + r"Users/[^/\s]+/")),
    ("Windows user path", re.compile(r"[A-Za-z]:\\Users\\")),
    ("GitHub token", re.compile(r"\bgh[opurs]_[A-Za-z0-9]{20,}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[A-Z0-9]{16}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("private key", re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY")),
    (
        "credential assignment",
        re.compile(r"(?i)(?:password|secret|token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"),
    ),
)


def command(*arguments: str) -> bytes:
    """Run a read-only Git command in the repository."""

    return subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def tree_files() -> Iterable[tuple[str, bytes]]:
    """Yield tracked and non-ignored untracked release-candidate files."""

    if (ROOT / ".git").exists():
        relative_paths = (
            Path(value.decode("utf-8", errors="surrogateescape"))
            for value in command(
                "ls-files", "--cached", "--others", "--exclude-standard", "-z"
            ).split(b"\x00")
            if value
        )
        paths = (ROOT / relative_path for relative_path in relative_paths)
    else:
        paths = ROOT.rglob("*")

    for path in sorted(paths):
        if IGNORED_DIRECTORIES.intersection(path.relative_to(ROOT).parts):
            continue
        if path.is_symlink():
            yield path.relative_to(ROOT).as_posix(), b"\x00"
            continue
        if not path.is_file():
            continue
        yield path.relative_to(ROOT).as_posix(), path.read_bytes()


def history_blobs() -> Iterable[tuple[str, bytes]]:
    """Yield every unique blob reachable from any Git ref."""

    seen: set[str] = set()
    for line in command("rev-list", "--objects", "--all").decode("utf-8", errors="replace").splitlines():
        object_id, _, path = line.partition(" ")
        if object_id in seen or command("cat-file", "-t", object_id).strip() != b"blob":
            continue
        seen.add(object_id)
        label = f"{object_id[:12]}:{path or '(unnamed blob)'}"
        yield label, command("cat-file", "blob", object_id)


def load_denied_terms(path: Path | None) -> tuple[str, ...]:
    """Load private literal terms without ever printing their values."""

    if path is None:
        return ()
    return tuple(
        line.strip().casefold()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def scan(items: Iterable[tuple[str, bytes]], denied_terms: tuple[str, ...]) -> list[str]:
    """Return labels and locations only; never echo matching secret content."""

    violations: list[str] = []
    for location, content in items:
        if b"\x00" in content:
            violations.append(f"binary content: {location}")
            continue
        text = content.decode("utf-8", errors="replace")
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                violations.append(f"{label}: {location}")
        folded = text.casefold()
        for index, term in enumerate(denied_terms, start=1):
            if term in folded:
                violations.append(f"private deny term {index}: {location}")
    return violations


def coauthor_violations() -> list[str]:
    """Locate commit trailers that require an explicit publication decision."""

    violations: list[str] = []
    records = command("log", "--all", "--format=%H%x00%B%x00").decode("utf-8", errors="replace")
    parts = records.split("\x00")
    for index in range(0, len(parts) - 1, 2):
        commit_id = parts[index].strip()
        message = parts[index + 1]
        if re.search(r"(?im)^co-authored-by:", message):
            violations.append(f"co-author trailer: commit {commit_id[:12]}")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--tree", action="store_true", help="scan the current working tree")
    mode.add_argument("--history", action="store_true", help="scan every blob reachable from all refs")
    parser.add_argument("--deny-file", type=Path, help="private newline-separated literal terms")
    parser.add_argument(
        "--forbid-coauthor-trailers",
        action="store_true",
        help="flag Co-Authored-By trailers during a history scan",
    )
    arguments = parser.parse_args()

    denied_terms = load_denied_terms(arguments.deny_file)
    items = history_blobs() if arguments.history else tree_files()
    violations = scan(items, denied_terms)
    if arguments.history and arguments.forbid_coauthor_trailers:
        violations.extend(coauthor_violations())
    if violations:
        for violation in sorted(set(violations)):
            print(violation)
        print(f"repository audit failed with {len(set(violations))} finding(s)")
        return 1
    print("repository audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

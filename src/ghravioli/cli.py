"""Command-line interface for ghravioli."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from ghravioli.build import build_file, default_output_path
from ghravioli.clipboard import ClipboardError, ClipboardUnavailable, copy_to_clipboard
from ghravioli.display import (
    contains_unsafe_terminal_text,
    escape_terminal_label,
    escape_terminal_text,
)
from ghravioli.errors import BuildError, ManifestError
from ghravioli.inspect import InspectError, archive_sources, inspect_archive_bytes, inspect_path
from ghravioli.manifest import load_manifest
from ghravioli.model import ComponentManifest, GraphManifest


ClipboardWriter = Callable[[bytes], str]


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    clipboard_writer: ClipboardWriter | None = None,
) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    writer = clipboard_writer or copy_to_clipboard
    try:
        if arguments.command == "validate":
            return _validate(arguments.path, stdout)
        if arguments.command == "build":
            return _build(arguments.path, arguments.output, arguments.at, stdout)
        if arguments.command == "inspect":
            return _inspect(arguments.path, arguments.json, arguments.source, arguments.sha256, stdout)
        if arguments.command == "copy":
            return _copy(arguments.path, writer, arguments.at, stdout, stderr)
        if arguments.command == "code":
            return _code(arguments.path, arguments.component, arguments.unsafe_terminal, stdout)
        if arguments.command == "extract":
            return _extract(arguments.path, arguments.output, stdout)
    except ClipboardUnavailable as error:
        print(f"clipboard unavailable: {escape_terminal_label(str(error))}", file=stderr)
        return 1
    except (ManifestError, BuildError, ClipboardError, InspectError, OSError) as error:
        print(f"error: {escape_terminal_label(str(error))}", file=stderr)
        return 1
    parser.error("a command is required")
    return 2


_AT_HELP = (
    "place the component at canvas position X,Y instead of the default 200,200; "
    "applies to a single-component manifest only"
)


def _position(value: str) -> tuple[float, float]:
    parts = value.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("position must be given as X,Y")
    try:
        x = float(parts[0])
        y = float(parts[1])
    except ValueError:
        raise argparse.ArgumentTypeError("position X,Y must be two numbers")
    if not (math.isfinite(x) and math.isfinite(y)):
        raise argparse.ArgumentTypeError("position X,Y must be finite")
    return (x, y)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ghravioli",
        description="Generate experimental Rhino Grasshopper Python component archives.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate a component or graph manifest")
    validate.add_argument("path", type=Path)

    build = subparsers.add_parser("build", help="build an experimental .ghclip archive")
    build.add_argument("path", type=Path)
    build.add_argument("-o", "--output", type=Path)
    build.add_argument("--at", type=_position, metavar="X,Y", default=None, help=_AT_HELP)

    inspect = subparsers.add_parser("inspect", help="summarize a manifest or .ghclip archive")
    inspect.add_argument("path", type=Path)
    inspection_mode = inspect.add_mutually_exclusive_group()
    inspection_mode.add_argument("--json", action="store_true")
    inspection_mode.add_argument("--source", action="store_true", help="print decoded embedded source")
    inspection_mode.add_argument("--sha256", action="store_true", help="print embedded source hashes")

    copy = subparsers.add_parser("copy", help="build if needed and copy archive text to the clipboard")
    copy.add_argument("path", type=Path)
    copy.add_argument("--at", type=_position, metavar="X,Y", default=None, help=_AT_HELP)

    code = subparsers.add_parser("code", help="print exact Python source from a manifest or archive")
    code.add_argument("path", type=Path)
    code.add_argument(
        "-c",
        "--component",
        type=int,
        metavar="INDEX",
        help="select a one-based component index from a multi-component archive",
    )
    code.add_argument(
        "--unsafe-terminal",
        action="store_true",
        help="allow exact source containing unsafe controls to be written to a terminal",
    )

    extract = subparsers.add_parser("extract", help="extract reviewed source from a .ghclip archive")
    extract.add_argument("path", type=Path)
    extract.add_argument("-o", "--output", type=Path, required=True)
    return parser


def _validate(path: Path, stdout: TextIO) -> int:
    manifest = load_manifest(path)
    if isinstance(manifest, ComponentManifest):
        print(f"valid component: {manifest.id} ({len(manifest.inputs)} inputs, {len(manifest.outputs)} outputs)", file=stdout)
    elif isinstance(manifest, GraphManifest):
        print(f"valid graph: {manifest.id} ({len(manifest.components)} components, automatic wiring disabled)", file=stdout)
    return 0


def _build(path: Path, output: Path | None, position: tuple[float, float] | None, stdout: TextIO) -> int:
    destination = build_file(path, output, position=position)
    print(escape_terminal_label(destination.name), file=stdout)
    return 0


def _inspect(path: Path, as_json: bool, include_source: bool, hashes_only: bool, stdout: TextIO) -> int:
    if include_source or hashes_only:
        if path.suffix.lower() != ".ghclip":
            raise InspectError("--source and --sha256 require a .ghclip archive")
        sources = archive_sources(path)
        if include_source:
            _write_sources(sources, stdout, include_headers=True)
        else:
            for source in sources:
                quoted_name = json.dumps(source["name"], ensure_ascii=True)
                print(f"{source['sha256']}  {quoted_name}", file=stdout)
        return 0
    summary = inspect_path(path)
    if as_json:
        json.dump(summary, stdout, indent=2, sort_keys=True)
        stdout.write("\n")
    else:
        label = summary.get("name", summary.get("path", path.name))
        print(f"{summary['kind']}: {escape_terminal_label(str(label))}", file=stdout)
        if summary["kind"] == "archive":
            print(f"components: {summary['object_count']}", file=stdout)
    return 0


def _copy(
    path: Path,
    writer: ClipboardWriter,
    position: tuple[float, float] | None,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    target = path.expanduser().resolve()
    if target.suffix.lower() == ".ghclip":
        if position is not None:
            raise BuildError(
                target,
                "--at applies when building from a manifest, not to a prebuilt .ghclip",
            )
        archive = target.read_bytes()
        inspect_archive_bytes(archive, display_path=target.name)
        archive_path = target
    else:
        archive_path = build_file(target, default_output_path(target), position=position)
        archive = archive_path.read_bytes()
    try:
        adapter = writer(archive)
    except ClipboardUnavailable as error:
        print(
            "clipboard unavailable: "
            f"{escape_terminal_label(str(error))}; use the generated .ghclip file",
            file=stderr,
        )
        print(escape_terminal_label(archive_path.name), file=stdout)
        return 0
    print(
        f"copied with {adapter}; fallback: {escape_terminal_label(archive_path.name)}",
        file=stdout,
    )
    return 0


def _code(
    path: Path,
    component_index: int | None,
    allow_unsafe_terminal: bool,
    stdout: TextIO,
) -> int:
    if path.suffix.lower() == ".ghclip":
        sources = archive_sources(path)
        if component_index is None and len(sources) != 1:
            raise InspectError(
                f"archive contains {len(sources)} components; use --component INDEX "
                "to choose exact source or use extract"
            )
        selected_index = component_index or 1
        if not 1 <= selected_index <= len(sources):
            raise InspectError(
                f"component index must be between 1 and {len(sources)}"
            )
        selected = sources[selected_index - 1]
        _write_exact_source(selected["source"], stdout, allow_unsafe_terminal)
        return 0
    manifest = load_manifest(path)
    if not isinstance(manifest, ComponentManifest):
        raise ManifestError(manifest.path, "code requires a component manifest")
    if component_index not in (None, 1):
        raise ManifestError(manifest.path, "a component manifest only has component index 1")
    _write_exact_source(manifest.source_text, stdout, allow_unsafe_terminal)
    return 0


def _extract(path: Path, output: Path, stdout: TextIO) -> int:
    sources = archive_sources(path)
    output_directory = output.expanduser().resolve()
    if output.expanduser().is_symlink():
        raise InspectError("extract output cannot be a symbolic link")
    if output_directory.exists():
        if not output_directory.is_dir():
            raise InspectError("extract output must be a directory")
        if any(output_directory.iterdir()):
            raise InspectError("extract output directory must be empty")
    else:
        output_directory.mkdir(parents=True)

    destinations = [
        output_directory / f"{index:03d}-{_source_slug(source['name'])}.py"
        for index, source in enumerate(sources, start=1)
    ]
    for destination, source in zip(destinations, sources, strict=True):
        with destination.open("x", encoding="utf-8", newline="") as output_file:
            output_file.write(source["source"])
        print(destination.name, file=stdout)
    return 0


def _write_sources(sources: list[dict[str, str]], stdout: TextIO, *, include_headers: bool) -> None:
    for index, source in enumerate(sources):
        if include_headers:
            if index:
                stdout.write("\n")
            quoted_name = json.dumps(source["name"], ensure_ascii=True)
            print(f"# --- embedded source: {quoted_name} ---", file=stdout)
        stdout.write(escape_terminal_text(source["source"]))
        if source["source"] and not source["source"].endswith("\n"):
            stdout.write("\n")


def _write_exact_source(source: str, stdout: TextIO, allow_unsafe_terminal: bool) -> None:
    is_terminal = callable(getattr(stdout, "isatty", None)) and stdout.isatty()
    if (
        is_terminal
        and not allow_unsafe_terminal
        and contains_unsafe_terminal_text(source, allow_layout=True)
    ):
        raise InspectError(
            "exact source contains unsafe terminal controls; redirect it, use extract, "
            "or pass --unsafe-terminal"
        )
    stdout.write(source)


def _source_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:80] or "component"

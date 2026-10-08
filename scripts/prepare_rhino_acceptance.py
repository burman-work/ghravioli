#!/usr/bin/env python3
"""Create deterministic, private fixtures for the manual Rhino acceptance matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ghravioli import __version__  # noqa: E402
from ghravioli.build import build_file  # noqa: E402
from ghravioli.identity import SequenceIdentityProvider  # noqa: E402
from ghravioli.inspect import archive_sources, inspect_archive  # noqa: E402
from ghravioli.manifest import load_manifest  # noqa: E402
from ghravioli.model import ComponentManifest, GraphManifest  # noqa: E402


FIXTURES = (
    ("scale-points", ROOT / "examples" / "scale_points" / "component.toml"),
    ("json-config", ROOT / "examples" / "json_config" / "component.toml"),
    ("pipeline", ROOT / "examples" / "pipeline.toml"),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo_record(path: Path, kind: str) -> dict[str, str]:
    return {
        "kind": kind,
        "path": path.resolve().relative_to(ROOT).as_posix(),
        "sha256": _sha256(path),
    }


def _bundle_record(path: Path, output: Path, kind: str) -> dict[str, str]:
    return {
        "kind": kind,
        "path": path.relative_to(output).as_posix(),
        "sha256": _sha256(path),
    }


def _component_manifests(manifest: ComponentManifest | GraphManifest) -> list[ComponentManifest]:
    if isinstance(manifest, ComponentManifest):
        return [manifest]
    return [placement.component for placement in manifest.components]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:80] or "component"


def _commit(declared: str | None = None) -> str:
    if declared is not None:
        if not re.fullmatch(r"[0-9a-f]{40}", declared):
            raise ValueError("--commit must be a lowercase 40-character Git commit")
        return declared
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("source is not a Git checkout; pass its origin with --commit")
    commit = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("git did not return a full commit identifier")
    return commit


def prepare(output: Path, *, commit: str | None = None) -> None:
    requested = output.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    if requested.is_symlink():
        raise ValueError("acceptance output cannot be a symbolic link")
    if requested.exists():
        raise ValueError(f"acceptance output already exists: {requested}")
    destination = requested.resolve(strict=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()
    archives = destination / "archives"
    extracted_root = destination / "extracted"
    archives.mkdir()
    extracted_root.mkdir()

    fixture_records: list[dict[str, Any]] = []
    for fixture_id, manifest_path in FIXTURES:
        model = load_manifest(manifest_path)
        archive_path = archives / f"{fixture_id}.ghclip"
        build_file(
            manifest_path,
            archive_path,
            identities=SequenceIdentityProvider(),
        )
        inspect_archive(archive_path)

        components = _component_manifests(model)
        manifest_paths = [manifest_path, *(component.path for component in components)]
        unique_manifests = list(dict.fromkeys(path.resolve() for path in manifest_paths))
        unique_sources = list(dict.fromkeys(component.source_path.resolve() for component in components))

        extracted_directory = extracted_root / fixture_id
        extracted_directory.mkdir()
        extracted_records: list[dict[str, str]] = []
        for index, source in enumerate(archive_sources(archive_path), start=1):
            extracted_path = extracted_directory / f"{index:03d}-{_slug(source['name'])}.py"
            with extracted_path.open("x", encoding="utf-8", newline="") as output_file:
                output_file.write(source["source"])
            extracted_records.append(_bundle_record(extracted_path, destination, "extracted"))

        fixture_records.append(
            {
                "id": fixture_id,
                "archive": _bundle_record(archive_path, destination, "archive"),
                "manifests": [_repo_record(path, "manifest") for path in unique_manifests],
                "sources": [_repo_record(path, "source") for path in unique_sources],
                "extracted": extracted_records,
            }
        )

    evidence = {
        "format_version": 1,
        "candidate": {"name": "ghRavioli", "version": __version__, "commit": _commit(commit)},
        "manual_status": "pending",
        "fixtures": fixture_records,
    }
    (destination / "manifest.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    (destination / "CHECKLIST.md").write_text(
        "# ghRavioli Rhino acceptance bundle\n\n"
        "MANUAL STATUS: PENDING\n\n"
        f"Candidate: {__version__} at `{evidence['candidate']['commit']}`\n\n"
        "This bundle prepares deterministic neutral fixtures; it does not prove Rhino or "
        "clipboard compatibility. Follow `docs/RHINO_ACCEPTANCE.md`, record exact platform "
        "versions, and attach external screenshots and logs privately.\n\n"
        "- [ ] Verify every archive and extracted-source hash against `manifest.json`.\n"
        "- [ ] Complete the Windows matrix.\n"
        "- [ ] Complete the macOS matrix.\n"
        "- [ ] Record clipboard byte/text comparisons.\n"
        "- [ ] Record save, reopen, and recompute evidence.\n",
        encoding="utf-8",
        newline="",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--commit",
        help="lowercase 40-character origin commit (required outside a Git checkout)",
    )
    arguments = parser.parse_args()
    try:
        prepare(arguments.output, commit=arguments.commit)
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"prepared pending Rhino acceptance bundle: {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

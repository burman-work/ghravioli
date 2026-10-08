"""Build Grasshopper archive bytes and write them atomically."""

from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path

from ghravioli import constants
from ghravioli.archive import build_archive
from ghravioli.errors import BuildError
from ghravioli.identity import IdentityProvider
from ghravioli.manifest import load_manifest
from ghravioli.model import ComponentManifest, ComponentPlacement, GraphManifest


def default_output_path(manifest_path: str | Path) -> Path:
    """Return the default `.ghclip` destination beside a manifest."""

    return Path(manifest_path).expanduser().with_suffix(".ghclip")


DEFAULT_COMPONENT_POSITION = (200.0, 200.0)


def _validated_position(path: Path, position: tuple[float, float]) -> tuple[float, float]:
    if not isinstance(position, tuple) or len(position) != 2:
        raise BuildError(path, "position must contain exactly two numeric coordinates")
    coordinates = []
    for value in position:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise BuildError(path, "position coordinates must be numbers")
        try:
            coordinate = float(value)
        except OverflowError as error:
            raise BuildError(path, "position coordinates must be finite") from error
        if not math.isfinite(coordinate):
            raise BuildError(path, "position coordinates must be finite")
        coordinates.append(coordinate)
    return coordinates[0], coordinates[1]


def build_bytes(
    manifest_path: str | Path,
    *,
    identities: IdentityProvider | None = None,
    position: tuple[float, float] | None = None,
) -> bytes:
    """Validate a component or graph manifest and return archive bytes.

    ``position`` overrides where a single-component archive is placed on the
    canvas; it is rejected for a graph, which positions each component itself.
    """

    manifest = load_manifest(manifest_path)
    return _build_manifest_bytes(manifest, identities=identities, position=position)


def _build_manifest_bytes(
    manifest: ComponentManifest | GraphManifest,
    *,
    identities: IdentityProvider | None,
    position: tuple[float, float] | None = None,
) -> bytes:
    if isinstance(manifest, ComponentManifest):
        x, y = _validated_position(manifest.path, position) if position is not None else DEFAULT_COMPONENT_POSITION
        placements = (ComponentPlacement(component=manifest, x=x, y=y),)
    elif isinstance(manifest, GraphManifest):
        if position is not None:
            raise BuildError(
                manifest.path,
                "a placement position applies to a single-component manifest; "
                "a graph sets each component's position in the manifest",
            )
        placements = manifest.components
    else:  # pragma: no cover - union exhaustiveness guard
        raise TypeError(f"unsupported manifest model: {type(manifest).__name__}")
    archive = build_archive(placements, document_name=manifest.name, identities=identities)
    if len(archive) > constants.MAX_ARCHIVE_BYTES:
        raise BuildError(
            manifest.path,
            "archive exceeds maximum "
            f"{constants.MAX_ARCHIVE_BYTES} bytes; actual size is {len(archive)} bytes",
        )
    return archive


def build_file(
    manifest_path: str | Path,
    output_path: str | Path | None = None,
    *,
    identities: IdentityProvider | None = None,
    position: tuple[float, float] | None = None,
) -> Path:
    """Build completely, then atomically replace the requested destination."""

    manifest = load_manifest(manifest_path)
    requested_destination = Path(output_path or default_output_path(manifest_path)).expanduser()
    if requested_destination.is_symlink():
        raise BuildError(requested_destination, "output cannot be a symbolic link")
    destination = requested_destination.resolve()
    protected_paths = _build_input_paths(manifest)
    if destination in protected_paths:
        raise BuildError(destination, "output cannot replace a build input")
    if destination.suffix.lower() != ".ghclip":
        raise BuildError(destination, "output must use the .ghclip suffix")
    parent = destination.parent
    if not parent.is_dir():
        raise BuildError(destination, "output directory does not exist")
    archive = _build_manifest_bytes(manifest, identities=identities, position=position)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(archive)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, destination)
    except OSError as error:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise BuildError(destination, f"cannot write archive: {error.strerror or error}") from error
    return destination


def _build_input_paths(manifest: ComponentManifest | GraphManifest) -> frozenset[Path]:
    if isinstance(manifest, ComponentManifest):
        return frozenset({manifest.path.resolve(), manifest.source_path.resolve()})
    inputs: set[Path] = {manifest.path.resolve()}
    for placement in manifest.components:
        inputs.add(placement.component.path.resolve())
        inputs.add(placement.component.source_path.resolve())
    return frozenset(inputs)

"""Immutable models for component and graph manifests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Port:
    """One declared Grasshopper input or output."""

    name: str
    nickname: str
    description: str
    type: str
    access: str
    optional: bool = False
    panel: bool = False
    default: bool | float | None = None
    minimum: float | None = None
    maximum: float | None = None

    @property
    def label(self) -> str:
        """Return the name a legible archive should show on the canvas."""

        return self.name

    def display_name(self, *, legible: bool) -> str:
        """Return the nickname written into the archive for this port."""

        return self.label if legible else self.nickname

    @property
    def has_range(self) -> bool:
        """Report whether this port declares a complete numeric slider range."""

        return self.minimum is not None and self.maximum is not None


@dataclass(frozen=True, slots=True)
class ComponentManifest:
    """A validated component interface plus its exact Python source."""

    path: Path
    schema_version: int
    target: str
    target_python: str
    id: str
    name: str
    description: str
    source_path: Path
    source_text: str
    inputs: tuple[Port, ...]
    outputs: tuple[Port, ...]
    legible_names: bool = True
    log_panel: bool = True
    input_widgets: bool = True
    standard_output: bool = True

    @property
    def log_output(self) -> Port | None:
        """Return the mandatory ``log`` output declared by this component."""

        return next((port for port in self.outputs if port.name == "log"), None)


@dataclass(frozen=True, slots=True)
class ComponentPlacement:
    """A component positioned in a larger clipboard archive."""

    component: ComponentManifest
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class GraphManifest:
    """A positioned collection of components without automatic wiring."""

    path: Path
    schema_version: int
    id: str
    name: str
    components: tuple[ComponentPlacement, ...]


Manifest = ComponentManifest | GraphManifest

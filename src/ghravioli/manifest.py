"""Read and validate ghravioli TOML manifests."""

from __future__ import annotations

import keyword
import math
import re
import tomllib
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from ghravioli.constants import SLIDER_TYPES, TOGGLE_TYPES
from ghravioli.display import contains_unsafe_terminal_text
from ghravioli.errors import ManifestError
from ghravioli.model import ComponentManifest, ComponentPlacement, GraphManifest, Manifest, Port
from ghravioli.source import (
    TARGET_PYTHON,
    SourceValidationError,
    decode_and_validate_source,
)


SCHEMA_VERSION = 1
TARGET = "rhino8-python3"
MAX_MANIFEST_BYTES = 256 * 1024
MAX_NAME_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 4000
MAX_RELATIVE_PATH_LENGTH = 1000
WINDOWS_INVALID_PATH_CHARACTERS = frozenset('<>:"|?*')
WINDOWS_RESERVED_PATH_NAMES = frozenset(
    {"con", "prn", "aux", "nul", "conin$", "conout$"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
    | {f"com{index}" for index in "¹²³"}
    | {f"lpt{index}" for index in "¹²³"}
)
MAX_PORTS = 128
MAX_GRAPH_COMPONENTS = 256
ACCESS_MODES = frozenset({"item", "list"})
TYPE_TOKENS = frozenset(
    {
        "str",
        "float",
        "bool",
        "point",
        "brep",
        "generic",
        "int",
        "vector",
        "surface",
        "curve",
        "mesh",
        "geometry",
        "plane",
    }
)
COMPONENT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
COMPONENT_FIELDS = frozenset(
    {
        "kind",
        "schema_version",
        "target",
        "target_python",
        "id",
        "name",
        "source",
        "description",
        "inputs",
        "outputs",
        "legible_names",
        "log_panel",
        "input_widgets",
        "standard_output",
    }
)
CANVAS_FLAG_DEFAULTS = {
    "legible_names": True,
    "log_panel": True,
    "input_widgets": True,
    "standard_output": True,
}
GRAPH_FIELDS = frozenset({"kind", "schema_version", "id", "name", "components"})
PLACEMENT_FIELDS = frozenset({"manifest", "x", "y"})
INPUT_PORT_FIELDS = frozenset(
    {"name", "nickname", "description", "type", "access", "optional", "default", "min", "max"}
)
OUTPUT_PORT_FIELDS = frozenset({"name", "nickname", "description", "type", "access", "panel"})


def load_manifest(path: str | Path) -> Manifest:
    """Load a supported TOML manifest and return its validated model."""

    manifest_path = Path(path).expanduser().resolve()
    return _load_manifest_path(manifest_path, stack=frozenset())


def _load_manifest_path(path: Path, *, stack: frozenset[Path]) -> Manifest:
    if path in stack:
        raise ManifestError(path, "cyclic graph manifest reference")
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ManifestError(path, f"cannot read manifest: {error.strerror or error}") from error
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ManifestError(path, f"manifest exceeds {MAX_MANIFEST_BYTES} bytes")

    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ManifestError(path, "manifest must be UTF-8") from error
    except tomllib.TOMLDecodeError as error:
        raise ManifestError(path, f"malformed TOML: {error}") from error

    kind = data.get("kind")
    if kind == "component":
        return _load_component(path, data)
    if kind == "graph":
        return _load_graph(path, data, stack=stack | {path})
    raise ManifestError(path, f"unsupported manifest kind {kind!r}", field="kind")


def _load_component(path: Path, data: dict[str, Any]) -> ComponentManifest:
    _reject_unknown_fields(path, data, COMPONENT_FIELDS)
    schema_version = _schema_version(path, data)
    target = _required_string(path, data, "target")
    if target != TARGET:
        raise ManifestError(path, f"target must be {TARGET!r}", field="target")
    target_python = _required_string(path, data, "target_python")
    if target_python != TARGET_PYTHON:
        raise ManifestError(path, f"target_python must be {TARGET_PYTHON!r}", field="target_python")

    component_id = _required_string(path, data, "id")
    if not COMPONENT_ID_PATTERN.fullmatch(component_id):
        raise ManifestError(
            path,
            "invalid component id; use lowercase letters, numbers and single hyphens",
            field="id",
        )

    name = _required_string(path, data, "name")
    description = _optional_string(path, data, "description", default="")
    source_path, source_text = _load_source(path, data.get("source"))

    inputs = _load_ports(path, data.get("inputs", []), direction="input")
    outputs = _load_ports(path, data.get("outputs", []), direction="output")
    _validate_port_contract(path, inputs, outputs)
    flags = {key: _canvas_flag(path, data, key) for key in CANVAS_FLAG_DEFAULTS}

    return ComponentManifest(
        path=path,
        schema_version=schema_version,
        target=target,
        target_python=target_python,
        id=component_id,
        name=name,
        description=description,
        source_path=source_path,
        source_text=source_text,
        inputs=inputs,
        outputs=outputs,
        **flags,
    )


def _canvas_flag(path: Path, data: dict[str, Any], key: str) -> bool:
    """Read one optional canvas-presentation flag, which defaults to enabled."""

    value = data.get(key, CANVAS_FLAG_DEFAULTS[key])
    if not isinstance(value, bool):
        raise ManifestError(path, "must be a boolean", field=key)
    return value


def _load_graph(path: Path, data: dict[str, Any], *, stack: frozenset[Path]) -> GraphManifest:
    if "connections" in data:
        raise ManifestError(
            path,
            "automatic wiring is experimental and unsupported in schema version 1",
            field="connections",
        )
    _reject_unknown_fields(path, data, GRAPH_FIELDS)
    schema_version = _schema_version(path, data)

    graph_id = _required_string(path, data, "id")
    if not COMPONENT_ID_PATTERN.fullmatch(graph_id):
        raise ManifestError(
            path,
            "invalid graph id; use lowercase letters, numbers and single hyphens",
            field="id",
        )
    name = _required_string(path, data, "name")

    raw_components = data.get("components")
    if not isinstance(raw_components, list) or not raw_components:
        raise ManifestError(path, "components must be a non-empty array of tables", field="components")
    if len(raw_components) > MAX_GRAPH_COMPONENTS:
        raise ManifestError(path, f"components must contain at most {MAX_GRAPH_COMPONENTS} entries", field="components")

    graph_dir = path.parent.resolve()
    placements: list[ComponentPlacement] = []
    seen_ids: set[str] = set()
    for index, raw_component in enumerate(raw_components):
        field = f"components[{index}]"
        if not isinstance(raw_component, dict):
            raise ManifestError(path, "component placement must be a TOML table", field=field)
        _reject_unknown_fields(path, raw_component, PLACEMENT_FIELDS, parent=field)
        relative_manifest = _relative_path(
            path,
            raw_component.get("manifest"),
            field=f"{field}.manifest",
            label="component manifest",
        )
        child_path = (graph_dir / relative_manifest).resolve()
        if not child_path.is_relative_to(graph_dir):
            raise ManifestError(
                path,
                "component manifest must stay inside the graph directory",
                field=f"{field}.manifest",
            )

        try:
            component = _load_manifest_path(child_path, stack=stack)
        except ManifestError as error:
            raise ManifestError(
                error.path,
                error.message,
                field=error.field,
                display_path=relative_manifest.as_posix(),
            ) from error
        if not isinstance(component, ComponentManifest):
            raise ManifestError(path, "graph entries must reference component manifests", field=f"{field}.manifest")
        if component.id in seen_ids:
            raise ManifestError(path, f"duplicate component id {component.id!r}", field="components")
        seen_ids.add(component.id)

        x = _coordinate(path, raw_component.get("x"), field=f"{field}.x")
        y = _coordinate(path, raw_component.get("y"), field=f"{field}.y")
        placements.append(ComponentPlacement(component=component, x=x, y=y))

    return GraphManifest(
        path=path,
        schema_version=schema_version,
        id=graph_id,
        name=name,
        components=tuple(placements),
    )


def _load_source(manifest_path: Path, value: object) -> tuple[Path, str]:
    declared = _relative_path(
        manifest_path,
        value,
        field="source",
        label="source",
    )

    manifest_dir = manifest_path.parent.resolve()
    source_path = (manifest_dir / declared).resolve()
    if not source_path.is_relative_to(manifest_dir):
        raise ManifestError(manifest_path, "source must stay inside the manifest directory", field="source")
    if not source_path.is_file():
        raise ManifestError(manifest_path, f"source file does not exist: {declared}", field="source")

    try:
        source_bytes = source_path.read_bytes()
    except OSError as error:
        raise ManifestError(manifest_path, f"cannot read source: {error.strerror or error}", field="source") from error
    try:
        source_text = decode_and_validate_source(source_bytes, filename=declared.as_posix())
    except SourceValidationError as error:
        raise ManifestError(manifest_path, str(error), field="source") from error
    return source_path, source_text


def _load_ports(path: Path, raw_ports: object, *, direction: str) -> tuple[Port, ...]:
    if not isinstance(raw_ports, list):
        raise ManifestError(path, f"{direction}s must be an array of tables", field=f"{direction}s")
    if len(raw_ports) > MAX_PORTS:
        raise ManifestError(path, f"{direction}s must contain at most {MAX_PORTS} entries", field=f"{direction}s")

    ports: list[Port] = []
    for index, raw_port in enumerate(raw_ports):
        field = f"{direction}s[{index}]"
        if not isinstance(raw_port, dict):
            raise ManifestError(path, "port must be a TOML table", field=field)
        allowed = INPUT_PORT_FIELDS if direction == "input" else OUTPUT_PORT_FIELDS
        _reject_unknown_fields(path, raw_port, allowed, parent=field)

        name = _required_string(path, raw_port, "name", parent=field)
        if not name.isidentifier() or keyword.iskeyword(name):
            raise ManifestError(path, "port name must be a valid Python identifier", field=f"{field}.name")
        if name == "out":
            raise ManifestError(path, "port name 'out' is reserved by the Python component", field=f"{field}.name")

        nickname = _optional_string(path, raw_port, "nickname", default=name, parent=field)
        description = _optional_string(path, raw_port, "description", default="", parent=field)
        type_token = _required_string(path, raw_port, "type", parent=field)
        if type_token not in TYPE_TOKENS:
            supported = ", ".join(sorted(TYPE_TOKENS))
            raise ManifestError(path, f"unsupported type {type_token!r}; choose one of: {supported}", field=f"{field}.type")

        access = _required_string(path, raw_port, "access", parent=field)
        if access not in ACCESS_MODES:
            raise ManifestError(path, "access must be 'item' or 'list'", field=f"{field}.access")

        optional_value = raw_port.get("optional", False)
        if not isinstance(optional_value, bool):
            raise ManifestError(path, "optional must be a boolean", field=f"{field}.optional")
        optional = optional_value if direction == "input" else False

        panel_value = raw_port.get("panel", False)
        if not isinstance(panel_value, bool):
            raise ManifestError(path, "panel must be a boolean", field=f"{field}.panel")
        if panel_value and direction != "output":
            raise ManifestError(path, "panel applies only to an output port", field=f"{field}.panel")
        # `log` always earns a panel when the component asks for one, so saying
        # so explicitly is redundant rather than wrong.
        panel = panel_value or (direction == "output" and name == "log")

        default, minimum, maximum = _load_widget_values(
            path,
            raw_port,
            field=field,
            type_token=type_token,
            access=access,
        )

        ports.append(
            Port(
                name=name,
                nickname=nickname,
                description=description,
                type=type_token,
                access=access,
                optional=optional,
                panel=panel,
                default=default,
                minimum=minimum,
                maximum=maximum,
            )
        )
    return tuple(ports)


def _load_widget_values(
    path: Path,
    raw_port: dict[str, Any],
    *,
    field: str,
    type_token: str,
    access: str,
) -> tuple[bool | float | None, float | None, float | None]:
    """Validate the optional default and range that drive an input widget.

    A widget is only ever generated for an ``item`` port: a slider or toggle
    feeds one value, so wiring one into a ``list`` port would misrepresent what
    the component receives.
    """

    declared = {key for key in ("default", "min", "max") if key in raw_port}
    if not declared:
        return None, None, None
    if access != "item":
        raise ManifestError(
            path,
            "default, min and max apply only to item access ports",
            field=f"{field}.{sorted(declared)[0]}",
        )

    if type_token in TOGGLE_TYPES:
        for key in ("min", "max"):
            if key in raw_port:
                raise ManifestError(path, f"{key} does not apply to a bool port", field=f"{field}.{key}")
        default = raw_port.get("default")
        if default is not None and not isinstance(default, bool):
            raise ManifestError(path, "default must be a boolean", field=f"{field}.default")
        return default, None, None

    if type_token not in SLIDER_TYPES:
        raise ManifestError(
            path,
            f"default, min and max do not apply to a {type_token!r} port",
            field=f"{field}.{sorted(declared)[0]}",
        )

    minimum = _widget_number(path, raw_port, "min", field=field)
    maximum = _widget_number(path, raw_port, "max", field=field)
    if (minimum is None) != (maximum is None):
        raise ManifestError(path, "min and max must be declared together", field=f"{field}.min")
    if minimum is not None and maximum is not None and minimum >= maximum:
        raise ManifestError(path, "min must be smaller than max", field=f"{field}.min")

    default = _widget_number(path, raw_port, "default", field=field)
    if default is not None and minimum is None:
        raise ManifestError(
            path,
            "a numeric default requires min and max",
            field=f"{field}.default",
        )
    if default is not None and minimum is not None and maximum is not None:
        if not minimum <= default <= maximum:
            raise ManifestError(path, "default must fall between min and max", field=f"{field}.default")
    if type_token == "int":
        for key, value in (("min", minimum), ("max", maximum), ("default", default)):
            if value is not None and not value.is_integer():
                raise ManifestError(
                    path,
                    f"{key} must be a whole number for an int port",
                    field=f"{field}.{key}",
                )
    return default, minimum, maximum


def _widget_number(
    path: Path,
    raw_port: dict[str, Any],
    key: str,
    *,
    field: str,
) -> float | None:
    if key not in raw_port:
        return None
    value = raw_port[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ManifestError(path, f"{key} must be a number", field=f"{field}.{key}")
    number = float(value)
    if not math.isfinite(number):
        raise ManifestError(path, f"{key} must be finite", field=f"{field}.{key}")
    return number


def _validate_port_contract(path: Path, inputs: tuple[Port, ...], outputs: tuple[Port, ...]) -> None:
    seen: set[str] = set()
    for port in (*inputs, *outputs):
        if port.name in seen:
            raise ManifestError(path, f"duplicate port name {port.name!r}")
        seen.add(port.name)

    logs = [port for port in outputs if port.name == "log"]
    if len(logs) != 1:
        raise ManifestError(path, "every component must declare exactly one output named 'log'")
    if logs[0].type != "str":
        raise ManifestError(path, "the log output must use type 'str'", field="outputs.log.type")
    if logs[0].access != "item":
        raise ManifestError(path, "the log output must use item access", field="outputs.log.access")


def _required_string(path: Path, data: dict[str, Any], key: str, *, parent: str | None = None) -> str:
    value = data.get(key)
    field = f"{parent}.{key}" if parent else key
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(path, "must be a non-empty string", field=field)
    return _validated_string(path, value.strip(), field=field, max_length=MAX_NAME_LENGTH)


def _optional_string(
    path: Path,
    data: dict[str, Any],
    key: str,
    *,
    default: str,
    parent: str | None = None,
) -> str:
    value = data.get(key, default)
    field = f"{parent}.{key}" if parent else key
    if not isinstance(value, str):
        raise ManifestError(path, "must be a string", field=field)
    max_length = MAX_DESCRIPTION_LENGTH if key == "description" else MAX_NAME_LENGTH
    return _validated_string(path, value.strip(), field=field, max_length=max_length)


def _coordinate(path: Path, value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ManifestError(path, "coordinate must be a number", field=field)
    coordinate = float(value)
    if not math.isfinite(coordinate):
        raise ManifestError(path, "coordinate must be finite", field=field)
    return coordinate


def _schema_version(path: Path, data: dict[str, Any]) -> int:
    value = data.get("schema_version")
    if type(value) is not int:
        raise ManifestError(path, "schema_version must be an integer equal to 1", field="schema_version")
    if value != SCHEMA_VERSION:
        raise ManifestError(
            path,
            f"unsupported schema_version {value!r}; expected {SCHEMA_VERSION}",
            field="schema_version",
        )
    return value


def _reject_unknown_fields(
    path: Path,
    data: dict[str, Any],
    allowed: frozenset[str],
    *,
    parent: str | None = None,
) -> None:
    unexpected = sorted(set(data) - allowed)
    if not unexpected:
        return
    field = f"{parent}.{unexpected[0]}" if parent else unexpected[0]
    names = ", ".join(unexpected)
    raise ManifestError(path, f"unexpected field(s): {names}", field=field)


def _validated_string(path: Path, value: str, *, field: str, max_length: int) -> str:
    if len(value) > max_length:
        raise ManifestError(path, f"must contain at most {max_length} characters", field=field)
    if any(not _is_xml_10_character(character) for character in value):
        raise ManifestError(path, "contains a character forbidden by XML 1.0", field=field)
    if any(ord(character) < 0x20 or 0x7F <= ord(character) < 0xA0 for character in value):
        raise ManifestError(path, "contains a terminal control character", field=field)
    if contains_unsafe_terminal_text(value):
        raise ManifestError(path, "contains an unsafe terminal formatting character", field=field)
    return value


def _relative_path(path: Path, value: object, *, field: str, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(path, f"{label} must be a non-empty relative path", field=field)
    canonical = _validated_string(
        path,
        value.strip(),
        field=field,
        max_length=MAX_RELATIVE_PATH_LENGTH,
    ).replace("\\", "/")
    posix_path = PurePosixPath(canonical)
    windows_path = PureWindowsPath(canonical)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ManifestError(path, f"{label} must be a relative path", field=field)
    if any(segment in {"", "."} for segment in canonical.split("/")):
        raise ManifestError(path, f"{label} must use non-empty path segments", field=field)
    for segment in canonical.split("/"):
        if segment != ".." and segment.endswith((" ", ".")):
            raise ManifestError(
                path,
                f"{label} path segments must not end with a space or dot on Windows",
                field=field,
            )
        if any(character in WINDOWS_INVALID_PATH_CHARACTERS for character in segment):
            raise ManifestError(
                path,
                f"{label} contains an invalid Windows path character",
                field=field,
            )
        device_name = segment.split(".", 1)[0].rstrip(" ").casefold()
        if device_name in WINDOWS_RESERVED_PATH_NAMES:
            raise ManifestError(
                path,
                f"{label} contains the Windows-reserved path segment {segment!r}",
                field=field,
            )
    return Path(canonical)


def _is_xml_10_character(character: str) -> bool:
    codepoint = ord(character)
    return (
        codepoint in (0x09, 0x0A, 0x0D)
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )

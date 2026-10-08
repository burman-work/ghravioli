"""Inspect manifests and generated Grasshopper archives."""

from __future__ import annotations

import base64
import binascii
import hashlib
import keyword
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from ghravioli import constants
from ghravioli.archive_schema import ArchiveSchemaError, validate_generated_archive_schema
from ghravioli.constants import (
    ACCESS_CODES,
    COMPANION_COMPONENT_IDS,
    LOG_PANEL_DESCRIPTION,
    PYTHON3_SCRIPT_COMPONENT_ID,
    SCRIPT_VARIABLE_PARAMETER_ID,
    STANDARD_OUTPUT_PARAMETER_ID,
    VERIFIED_CONVERTERS,
)
from ghravioli.display import contains_unsafe_terminal_text, escape_terminal_label
from ghravioli.manifest import (
    MAX_DESCRIPTION_LENGTH,
    MAX_GRAPH_COMPONENTS,
    MAX_NAME_LENGTH,
    MAX_PORTS,
    load_manifest,
)
from ghravioli.model import ComponentManifest, GraphManifest, Port
from ghravioli.source import SourceValidationError, decode_and_validate_source


_COMPANION_KINDS = {
    "Panel": "panel",
    "Boolean Toggle": "toggle",
    "Number Slider": "slider",
}


@dataclass(frozen=True, slots=True)
class _CompanionRecord:
    kind: str
    name: str
    nickname: str
    description: str
    instance: UUID
    source: UUID | None = None
    interval: int | None = None

    def summary(self) -> dict[str, str]:
        return {"kind": self.kind, "name": self.name, "nickname": self.nickname}


class InspectError(ValueError):
    """An archive could not be inspected safely."""

    def __init__(self, message: str) -> None:
        super().__init__(escape_terminal_label(message))


XML_DECLARATION = re.compile(r"\A<\?xml\b(?P<attributes>.*?)\?>", re.IGNORECASE | re.DOTALL)
XML_ENCODING = re.compile(
    r"\bencoding\s*=\s*(?P<quote>['\"])(?P<encoding>[^'\"]+)(?P=quote)",
    re.IGNORECASE,
)


def inspect_path(path: str | Path) -> dict[str, Any]:
    """Return a portable summary for a manifest or archive."""

    target = Path(path).expanduser().resolve()
    if target.suffix.lower() == ".ghclip":
        return inspect_archive(target)
    return inspect_manifest(target)


def inspect_manifest(path: str | Path) -> dict[str, Any]:
    """Return a summary without leaking machine-specific absolute paths."""

    manifest = load_manifest(path)
    if isinstance(manifest, ComponentManifest):
        source = manifest.source_path.relative_to(manifest.path.parent).as_posix()
        return {
            "kind": "component",
            "schema_version": manifest.schema_version,
            "target": manifest.target,
            "target_python": manifest.target_python,
            "id": manifest.id,
            "name": manifest.name,
            "source": source,
            "source_bytes": len(manifest.source_text.encode("utf-8")),
            "inputs": [_port_summary(port) for port in manifest.inputs],
            "outputs": [_port_summary(port) for port in manifest.outputs],
        }
    if isinstance(manifest, GraphManifest):
        return {
            "kind": "graph",
            "schema_version": manifest.schema_version,
            "id": manifest.id,
            "name": manifest.name,
            "components": [
                {
                    "id": placement.component.id,
                    "name": placement.component.name,
                    "manifest": placement.component.path.relative_to(manifest.path.parent).as_posix(),
                    "x": placement.x,
                    "y": placement.y,
                }
                for placement in manifest.components
            ],
            "automatic_wiring": False,
        }
    raise InspectError(f"unsupported manifest model: {type(manifest).__name__}")


def inspect_archive(path: str | Path) -> dict[str, Any]:
    """Validate and summarize an untrusted `.ghclip` archive."""

    return _inspect_archive(path, include_source=False)


def inspect_archive_bytes(archive_bytes: bytes, *, display_path: str) -> dict[str, Any]:
    """Validate bytes already read from an archive and return a summary."""

    return _inspect_archive(
        Path(display_path),
        include_source=False,
        archive_bytes=archive_bytes,
    )


def archive_sources(path: str | Path) -> list[dict[str, str]]:
    """Return decoded source and hashes after full structural validation."""

    summary = _inspect_archive(path, include_source=True)
    return [
        {
            "name": component["name"],
            "source": component["source"],
            "sha256": component["source_sha256"],
        }
        for component in summary["components"]
    ]


def _inspect_archive(
    path: str | Path,
    *,
    include_source: bool,
    archive_bytes: bytes | None = None,
) -> dict[str, Any]:
    archive_path = Path(path).expanduser().resolve()
    display_path = archive_path.name
    if archive_bytes is None:
        try:
            archive_bytes = archive_path.read_bytes()
        except OSError as error:
            raise InspectError(f"{display_path}: cannot read archive: {error.strerror or error}") from error
    if len(archive_bytes) > constants.MAX_ARCHIVE_BYTES:
        raise InspectError(
            f"{display_path}: archive exceeds {constants.MAX_ARCHIVE_BYTES} bytes; "
            f"actual size is {len(archive_bytes)} bytes"
        )
    if archive_bytes.startswith(b"\xef\xbb\xbf"):
        raise InspectError(f"{display_path}: UTF-8 BOM is forbidden")
    try:
        xml_text = archive_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise InspectError(f"{display_path}: archive XML must be UTF-8") from error
    if "\x00" in xml_text:
        raise InspectError(f"{display_path}: archive XML must be UTF-8")
    declaration = XML_DECLARATION.match(xml_text)
    if declaration is not None:
        encoding = XML_ENCODING.search(declaration.group("attributes"))
        if encoding is not None and encoding.group("encoding").lower() != "utf-8":
            raise InspectError(f"{display_path}: XML declaration encoding must be UTF-8")
    upper_text = xml_text.upper()
    if "<!DOCTYPE" in upper_text or "<!ENTITY" in upper_text:
        raise InspectError(f"{display_path}: DOCTYPE and entity declarations are forbidden")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as error:
        raise InspectError(f"{display_path}: malformed XML: {error}") from error
    if root.tag != "Archive":
        raise InspectError(f"{display_path}: root element must be Archive")
    try:
        validate_generated_archive_schema(root)
    except ArchiveSchemaError as error:
        raise InspectError(f"{display_path}: {error}") from error

    clipboard = _required_chunk(root, "Clipboard", display_path, context="archive")
    definition = _required_chunk(
        clipboard,
        "DefinitionObjects",
        display_path,
        context="Clipboard",
    )

    objects = definition.findall("./chunks/chunk[@name='Object']")
    if not objects:
        raise InspectError(f"{display_path}: archive must contain at least one Python component object")
    declared_count = _required_integer_item(definition, "ObjectCount", display_path)
    max_generated_objects = MAX_GRAPH_COMPONENTS * (MAX_PORTS + 2)
    if declared_count > max_generated_objects:
        raise InspectError(
            f"{display_path}: ObjectCount must contain at most {max_generated_objects} objects"
        )
    if declared_count != len(objects):
        raise InspectError(f"{display_path}: ObjectCount does not match archive objects")
    _validate_declared_counts(root, display_path)
    _validate_indexes(objects, "Object", display_path)

    script_objects = [
        object_chunk
        for object_chunk in objects
        if _required_item_text(object_chunk, "Name", display_path) == "Python 3 Script"
    ]
    if not script_objects:
        raise InspectError(f"{display_path}: archive must contain at least one Python component object")
    if len(script_objects) > MAX_GRAPH_COMPONENTS:
        raise InspectError(
            f"{display_path}: archive must contain at most {MAX_GRAPH_COMPONENTS} components"
        )

    components: list[dict[str, Any]] = []
    companion_records: list[_CompanionRecord] = []
    instance_ids: set[UUID] = set()
    for object_chunk in objects:
        if object_chunk in script_objects:
            continue
        companion_records.append(_validate_companion(object_chunk, display_path, instance_ids))

    for index, object_chunk in enumerate(script_objects):
        _validate_component_guid(object_chunk, display_path, index)
        container = _required_chunk(
            object_chunk,
            "Container",
            display_path,
            context=f"object {index}",
        )
        parameter_data = _required_chunk(
            container,
            "ParameterData",
            display_path,
            context=f"component {index}",
        )
        script = _required_chunk(
            container,
            "Script",
            display_path,
            context=f"component {index}",
        )
        _record_instance_guid(container, instance_ids, display_path, f"component {index}")
        _validate_parameter_data(parameter_data, display_path, index, instance_ids)
        _validate_language(script, display_path, index)

        description = _required_item_text(container, "Description", display_path)
        tooltip = _required_item_text(container, "Tooltip", display_path)
        _validate_manifest_text(
            description,
            "Description",
            display_path,
            max_length=MAX_DESCRIPTION_LENGTH,
            allow_empty=True,
        )
        if description != tooltip:
            raise InspectError(
                f"{display_path}: component {index} Description and Tooltip must match"
            )
        name = _required_item_text(container, "NickName", display_path)
        _validate_manifest_text(
            name,
            "NickName",
            display_path,
            max_length=MAX_NAME_LENGTH,
            allow_empty=False,
        )
        if _required_item_text(script, "Title", display_path) != name:
            raise InspectError(
                f"{display_path}: component {index} Script Title must match component NickName"
            )

        encoded = _required_item_text(script, "Text", display_path)
        try:
            source_bytes = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise InspectError(f"{display_path}: embedded source is not valid Base64") from error
        try:
            source = decode_and_validate_source(source_bytes, filename=f"{display_path}:component-{index + 1}.py")
        except SourceValidationError as error:
            raise InspectError(f"{display_path}: embedded {error}") from error
        _validate_safe_display_text(name, "NickName", display_path)
        component: dict[str, Any] = {
            "name": name,
            "inputs": [
                _archive_port_summary(chunk, display_path)
                for chunk in parameter_data.findall("./chunks/chunk[@name='InputParam']")
            ],
            "outputs": [
                _archive_port_summary(chunk, display_path)
                for chunk in parameter_data.findall("./chunks/chunk[@name='OutputParam']")
            ],
            "source_bytes": len(source_bytes),
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        }
        if include_source:
            component["source"] = source
        components.append(component)

    _validate_wiring(root, companion_records, display_path)
    return {
        "kind": "archive",
        "path": display_path,
        "object_count": len(objects),
        "components": components,
        "companions": [companion.summary() for companion in companion_records],
        "has_source_wiring": bool(root.findall(".//item[@name='Source']")),
    }


def _validate_companion(
    object_chunk: ET.Element,
    display_path: str,
    instance_ids: set[UUID],
) -> _CompanionRecord:
    """Validate one generated canvas companion and summarise it."""

    guid = _required_item_text(object_chunk, "GUID", display_path).lower()
    name = _required_item_text(object_chunk, "Name", display_path)
    expected = COMPANION_COMPONENT_IDS.get(_COMPANION_KINDS.get(name, ""))
    if expected is None or guid != expected:
        raise InspectError(f"{display_path}: companion object {name!r} has an unexpected GUID")
    container = _required_chunk(object_chunk, "Container", display_path, context=name)
    instance = _required_uuid_item(container, "InstanceGuid", display_path)
    if instance in instance_ids:
        raise InspectError(f"{display_path}: {name} has a duplicate InstanceGuid")
    instance_ids.add(instance)
    nickname = _required_item_text(container, "NickName", display_path)
    description = _required_item_text(container, "Description", display_path)
    _validate_manifest_text(
        nickname,
        "NickName",
        display_path,
        max_length=MAX_NAME_LENGTH,
        allow_empty=True,
    )
    _validate_safe_display_text(nickname, "NickName", display_path)
    kind = _COMPANION_KINDS[name]
    source = None
    interval = None
    if kind == "panel":
        source = _required_uuid_item(container, "Source", display_path)
    elif kind == "slider":
        slider = _required_chunk(container, "Slider", display_path, context=name)
        interval = _required_integer_item(slider, "Interval", display_path)
    return _CompanionRecord(
        kind=kind,
        name=name,
        nickname=nickname,
        description=description,
        instance=instance,
        source=source,
        interval=interval,
    )


def _validate_wiring(
    root: ET.Element,
    companions: list[_CompanionRecord],
    display_path: str,
) -> None:
    """Restrict generated wiring to one companion and its intended port."""

    widgets = {
        companion.instance: companion
        for companion in companions
        if companion.kind in {"toggle", "slider"}
    }
    panels = [companion for companion in companions if companion.kind == "panel"]
    used_widgets: set[UUID] = set()
    outputs: dict[UUID, tuple[str, str]] = {}

    for parameter_data in root.findall(".//chunk[@name='ParameterData']"):
        for input_port in parameter_data.findall("./chunks/chunk[@name='InputParam']"):
            source_text = _optional_item_text(input_port, "Source", display_path)
            if source_text is None:
                continue
            try:
                source = UUID(source_text)
            except ValueError as error:  # pragma: no cover - schema validates UUID text
                raise InspectError(f"{display_path}: Source must be a valid UUID") from error
            widget = widgets.get(source)
            if widget is None:
                raise InspectError(
                    f"{display_path}: input source must reference a generated widget"
                )

            hint = _optional_item_text(input_port, "TypeHintID", display_path)
            bool_hint = VERIFIED_CONVERTERS["bool"].type_hint_id.lower()
            float_hint = VERIFIED_CONVERTERS["float"].type_hint_id.lower()
            normalized_hint = hint.lower() if hint is not None else None
            if normalized_hint not in {None, bool_hint, float_hint}:
                raise InspectError(
                    f"{display_path}: input source port is not widget-compatible"
                )
            expected_kind = "toggle" if normalized_hint == bool_hint else "slider"
            if widget.kind != expected_kind:
                raise InspectError(
                    f"{display_path}: input source widget kind does not match its port"
                )
            if widget.kind == "slider":
                expected_interval = 0 if normalized_hint == float_hint else 1
                if widget.interval != expected_interval:
                    raise InspectError(
                        f"{display_path}: Slider Interval does not match its input port"
                    )

            port_name = _required_item_text(input_port, "Name", display_path)
            port_description = _required_item_text(input_port, "Description", display_path)
            if widget.nickname != port_name or widget.description != port_description:
                raise InspectError(
                    f"{display_path}: widget metadata must match its input port"
                )
            if source in used_widgets:
                raise InspectError(
                    f"{display_path}: a generated widget may drive exactly one input"
                )
            used_widgets.add(source)

        for output_port in parameter_data.findall("./chunks/chunk[@name='OutputParam']"):
            name = _item_text(output_port, "Name")
            if not name or name == "out":
                continue
            identity = _required_uuid_item(output_port, "InstanceGuid", display_path)
            outputs[identity] = (
                name,
                _required_item_text(output_port, "Description", display_path),
            )

    if used_widgets != set(widgets):
        raise InspectError(f"{display_path}: every generated widget must drive exactly one input")

    used_outputs: set[UUID] = set()
    for panel in panels:
        target = outputs.get(panel.source)
        if target is None:
            raise InspectError(
                f"{display_path}: panel source must reference a declared output"
            )
        port_name, port_description = target
        expected_description = LOG_PANEL_DESCRIPTION if port_name == "log" else port_description
        if panel.nickname != port_name or panel.description != expected_description:
            raise InspectError(
                f"{display_path}: panel metadata must match its output port"
            )
        if panel.source in used_outputs:
            raise InspectError(
                f"{display_path}: an output may drive at most one generated panel"
            )
        used_outputs.add(panel.source)


def _validate_declared_counts(root: ET.Element, display_path: str) -> None:
    for element in root.iter():
        if element.tag not in {"items", "chunks"}:
            continue
        raw_count = element.get("count")
        try:
            declared = int(raw_count) if raw_count is not None else None
        except ValueError as error:
            raise InspectError(f"{display_path}: {element.tag} declared count must be an integer") from error
        if declared is None:
            raise InspectError(f"{display_path}: {element.tag} is missing its declared count")
        if str(declared) != raw_count:
            raise InspectError(
                f"{display_path}: {element.tag} declared count must use canonical integer text"
            )
        if declared < 0 or declared != len(element):
            raise InspectError(f"{display_path}: {element.tag} declared count does not match its children")


def _validate_component_guid(object_chunk: ET.Element, display_path: str, index: int) -> None:
    guid = _required_item_text(object_chunk, "GUID", display_path)
    if guid.lower() != PYTHON3_SCRIPT_COMPONENT_ID:
        raise InspectError(f"{display_path}: object {index} has an unexpected Python component GUID")


def _validate_parameter_data(
    parameter_data: ET.Element,
    display_path: str,
    index: int,
    instance_ids: set[UUID],
) -> None:
    inputs = parameter_data.findall("./chunks/chunk[@name='InputParam']")
    outputs = parameter_data.findall("./chunks/chunk[@name='OutputParam']")
    input_count = _required_integer_item(parameter_data, "InputCount", display_path)
    output_count = _required_integer_item(parameter_data, "OutputCount", display_path)
    if input_count > MAX_PORTS:
        raise InspectError(
            f"{display_path}: component {index} InputCount must be at most {MAX_PORTS}"
        )
    if output_count > MAX_PORTS + 1:
        raise InspectError(
            f"{display_path}: component {index} user OutputCount must be at most {MAX_PORTS}"
        )
    if input_count != len(inputs):
        raise InspectError(f"{display_path}: component {index} InputCount does not match input chunks")
    if output_count != len(outputs):
        raise InspectError(f"{display_path}: component {index} OutputCount does not match output chunks")
    _validate_indexes(inputs, "InputParam", display_path)
    _validate_indexes(outputs, "OutputParam", display_path)

    input_id_items = parameter_data.findall("./items/item[@name='InputId']")
    output_id_items = parameter_data.findall("./items/item[@name='OutputId']")
    _validate_indexes(input_id_items, "InputId", display_path)
    _validate_indexes(output_id_items, "OutputId", display_path)
    input_ids = [item.text or "" for item in input_id_items]
    output_ids = [item.text or "" for item in output_id_items]
    if len(input_ids) != input_count or any(value.lower() != SCRIPT_VARIABLE_PARAMETER_ID for value in input_ids):
        raise InspectError(f"{display_path}: component {index} InputId declarations are invalid")
    has_standard = bool(outputs) and _item_text(outputs[0], "Name") == "out"
    if has_standard:
        expected_output_ids = [STANDARD_OUTPUT_PARAMETER_ID] + [
            SCRIPT_VARIABLE_PARAMETER_ID
        ] * max(output_count - 1, 0)
    else:
        expected_output_ids = [SCRIPT_VARIABLE_PARAMETER_ID] * output_count
    if [value.lower() for value in output_ids] != expected_output_ids:
        raise InspectError(f"{display_path}: component {index} OutputId declarations are invalid")
    if not outputs:
        raise InspectError(f"{display_path}: component {index} declares no outputs")
    if has_standard:
        _validate_standard_output(outputs[0], display_path, index, instance_ids)

    seen_names: set[str] = set()
    input_summaries = [
        _validate_user_port(port, "input", display_path, index, instance_ids)
        for port in inputs
    ]
    output_summaries = [
        _validate_user_port(port, "output", display_path, index, instance_ids)
        for port in outputs[1 if has_standard else 0 :]
    ]
    for port in (*input_summaries, *output_summaries):
        name = port["name"]
        if name == "out":
            raise InspectError(f"{display_path}: component {index} user port name 'out' is reserved")
        if name in seen_names:
            raise InspectError(f"{display_path}: component {index} has duplicate port name {name!r}")
        seen_names.add(name)

    logs = [port for port in output_summaries if port["name"] == "log"]
    if len(logs) != 1:
        raise InspectError(f"{display_path}: component {index} must have exactly one declared log output")
    log = logs[0]
    expected_hint = VERIFIED_CONVERTERS["str"].type_hint_id.lower()
    if log["access"] != ACCESS_CODES["item"]:
        raise InspectError(f"{display_path}: component {index} log output must use item access")
    if log["type_hint_id"] != expected_hint:
        raise InspectError(f"{display_path}: component {index} log output must use the string TypeHintID")


def _validate_standard_output(
    output: ET.Element,
    display_path: str,
    component_index: int,
    instance_ids: set[UUID],
) -> None:
    out_name = _required_item_text(output, "Name", display_path)
    out_nickname = _required_item_text(output, "NickName", display_path)
    if out_name != "out" or out_nickname != "out":
        raise InspectError(
            f"{display_path}: component {component_index} standard out must occupy index 0"
        )
    if _required_boolean_item(output, "Optional", display_path):
        raise InspectError(f"{display_path}: standard out Optional must be false")
    if _required_integer_item(output, "SourceCount", display_path) != 0:
        raise InspectError(f"{display_path}: standard out SourceCount must be zero")
    _record_instance_guid(output, instance_ids, display_path, "standard out")


def _validate_user_port(
    port: ET.Element,
    direction: str,
    display_path: str,
    component_index: int,
    instance_ids: set[UUID],
) -> dict[str, Any]:
    name = _required_item_text(port, "Name", display_path)
    nickname = _required_item_text(port, "NickName", display_path)
    description = _required_item_text(port, "Description", display_path)
    tooltip = _required_item_text(port, "ToolTip", display_path)
    _validate_manifest_text(
        name,
        "port Name",
        display_path,
        max_length=MAX_NAME_LENGTH,
        allow_empty=False,
    )
    if not name.isidentifier() or keyword.iskeyword(name):
        raise InspectError(f"{display_path}: port Name must be a valid Python identifier")
    _validate_manifest_text(
        nickname,
        "port NickName",
        display_path,
        max_length=MAX_NAME_LENGTH,
        allow_empty=True,
    )
    _validate_manifest_text(
        description,
        "port Description",
        display_path,
        max_length=MAX_DESCRIPTION_LENGTH,
        allow_empty=True,
    )
    if description != tooltip:
        raise InspectError(
            f"{display_path}: component {component_index} port Description and ToolTip must match"
        )
    _validate_safe_display_text(name, "port Name", display_path)
    _validate_safe_display_text(nickname, "port NickName", display_path)
    raw_access = _required_item_text(port, "ScriptParamAccess", display_path)
    valid_access = set(ACCESS_CODES.values())
    try:
        access = int(raw_access)
    except ValueError as error:
        raise InspectError(f"{display_path}: ScriptParamAccess must be a canonical integer") from error
    if str(access) != raw_access or access not in valid_access:
        raise InspectError(f"{display_path}: ScriptParamAccess must be a canonical item or list code")
    optional = _required_boolean_item(port, "Optional", display_path)
    if direction == "output" and optional:
        raise InspectError(f"{display_path}: output Optional must be false")
    source_count = _required_integer_item(port, "SourceCount", display_path)
    if source_count not in (0, 1):
        raise InspectError(
            f"{display_path}: a generated port declares at most one source connection"
        )
    if direction == "output" and source_count:
        raise InspectError(f"{display_path}: an output port cannot declare a source connection")
    if len(port.findall("./items/item[@name='Source']")) != source_count:
        raise InspectError(f"{display_path}: SourceCount does not match the declared Source items")
    _record_instance_guid(port, instance_ids, display_path, f"{direction} port {name!r}")
    type_hint_id = _validate_converter(port, display_path, component_index)
    return {
        "name": name,
        "nickname": nickname,
        "access": access,
        "optional": optional,
        "type_hint_id": type_hint_id,
    }


def _validate_converter(port: ET.Element, display_path: str, component_index: int) -> str | None:
    show_type_hints = _required_boolean_item(port, "ShowTypeHints", display_path)
    hint_text = _optional_item_text(port, "TypeHintID", display_path)
    converter_chunks = port.findall("./chunks/chunk[@name='ConverterData']")
    if hint_text is None:
        if show_type_hints or converter_chunks:
            raise InspectError(
                f"{display_path}: component {component_index} converter metadata requires TypeHintID"
            )
        return None

    try:
        hint_id = str(UUID(hint_text)).lower()
    except ValueError as error:
        raise InspectError(f"{display_path}: TypeHintID must be a valid UUID") from error
    converter = next(
        (candidate for candidate in VERIFIED_CONVERTERS.values() if candidate.type_hint_id.lower() == hint_id),
        None,
    )
    if converter is None:
        raise InspectError(f"{display_path}: TypeHintID is not a verified converter")
    if not show_type_hints or len(converter_chunks) != 1:
        raise InspectError(f"{display_path}: converter metadata must match TypeHintID")
    converter_data = converter_chunks[0]
    assembly = _required_item_text(converter_data, "AssemblyName", display_path)
    type_name = _required_item_text(converter_data, "TypeName", display_path)
    if assembly != converter.assembly_name or type_name != converter.type_name:
        raise InspectError(f"{display_path}: converter AssemblyName and TypeName must match TypeHintID")
    return hint_id


def _validate_language(script: ET.Element, display_path: str, index: int) -> None:
    language = _required_chunk(
        script,
        "LanguageSpec",
        display_path,
        context=f"component {index} Script",
    )
    taxon = _required_item_text(language, "Taxon", display_path)
    version = _required_item_text(language, "Version", display_path)
    if taxon != "*.*.python" or version != "3.*":
        raise InspectError(
            f"{display_path}: component {index} language specification must be Python 3"
        )


def _port_summary(port: Port) -> dict[str, Any]:
    return {
        "name": port.name,
        "nickname": port.nickname,
        "type": port.type,
        "access": port.access,
        "optional": port.optional,
        "description": port.description,
    }


def _archive_port_summary(chunk: ET.Element, display_path: str) -> dict[str, Any]:
    return {
        "name": _required_item_text(chunk, "Name", display_path),
        "nickname": _required_item_text(chunk, "NickName", display_path),
        "access": _item_text(chunk, "ScriptParamAccess") or None,
        "optional": _item_text(chunk, "Optional") == "true",
        "type_hint_id": _item_text(chunk, "TypeHintID") or None,
    }


def _required_integer_item(chunk: ET.Element, name: str, display_path: str) -> int:
    item = _required_item(chunk, name, display_path)
    raw_value = item.text or ""
    try:
        value = int(raw_value)
    except ValueError as error:
        raise InspectError(f"{display_path}: {name} must be an integer") from error
    if str(value) != raw_value:
        raise InspectError(f"{display_path}: {name} must use canonical integer text")
    if value < 0:
        raise InspectError(f"{display_path}: {name} must not be negative")
    return value


def _required_boolean_item(chunk: ET.Element, name: str, display_path: str) -> bool:
    raw_value = _required_item_text(chunk, name, display_path)
    if raw_value not in {"true", "false"}:
        raise InspectError(f"{display_path}: {name} must use canonical Boolean text")
    return raw_value == "true"


def _required_item_text(chunk: ET.Element, name: str, display_path: str) -> str:
    item = _required_item(chunk, name, display_path)
    return item.text or ""


def _required_item(chunk: ET.Element, name: str, display_path: str) -> ET.Element:
    matches = chunk.findall(f"./items/item[@name='{name}']")
    if not matches:
        raise InspectError(f"{display_path}: missing {name}")
    if len(matches) != 1:
        raise InspectError(
            f"{display_path}: {name} must appear exactly one time; found {len(matches)}"
        )
    return matches[0]


def _optional_item_text(chunk: ET.Element, name: str, display_path: str) -> str | None:
    matches = chunk.findall(f"./items/item[@name='{name}']")
    if len(matches) > 1:
        raise InspectError(
            f"{display_path}: {name} must appear at most one time; found {len(matches)}"
        )
    if not matches:
        return None
    return matches[0].text or ""


def _required_chunk(
    parent: ET.Element,
    name: str,
    display_path: str,
    *,
    context: str,
) -> ET.Element:
    matches = parent.findall(f"./chunks/chunk[@name='{name}']")
    if len(matches) != 1:
        raise InspectError(
            f"{display_path}: {context} {name} must appear exactly one time; found {len(matches)}"
        )
    return matches[0]


def _required_uuid_item(chunk: ET.Element, name: str, display_path: str) -> UUID:
    raw_value = _required_item_text(chunk, name, display_path)
    try:
        return UUID(raw_value)
    except ValueError as error:
        raise InspectError(f"{display_path}: {name} must be a valid UUID") from error


def _record_instance_guid(
    chunk: ET.Element,
    instance_ids: set[UUID],
    display_path: str,
    context: str,
) -> None:
    instance_id = _required_uuid_item(chunk, "InstanceGuid", display_path)
    if instance_id in instance_ids:
        raise InspectError(f"{display_path}: {context} has a duplicate InstanceGuid")
    instance_ids.add(instance_id)


def _validate_indexes(elements: list[ET.Element], label: str, display_path: str) -> None:
    indexes: list[int] = []
    for element in elements:
        raw_index = element.get("index")
        if raw_index is None:
            raise InspectError(f"{display_path}: {label} is missing its index")
        try:
            indexes.append(int(raw_index))
        except ValueError as error:
            raise InspectError(f"{display_path}: {label} index must be an integer") from error
    if indexes != list(range(len(elements))):
        raise InspectError(
            f"{display_path}: {label} indexes must be unique and contiguous from zero"
        )


def _validate_safe_display_text(value: str, label: str, display_path: str) -> None:
    if any(ord(character) < 0x20 or 0x7F <= ord(character) < 0xA0 for character in value):
        raise InspectError(f"{display_path}: {label} contains a terminal control character")
    if contains_unsafe_terminal_text(value):
        raise InspectError(f"{display_path}: {label} contains an unsafe terminal formatting character")


def _validate_manifest_text(
    value: str,
    label: str,
    display_path: str,
    *,
    max_length: int,
    allow_empty: bool,
) -> None:
    if not allow_empty and not value:
        raise InspectError(f"{display_path}: {label} must be non-empty")
    if len(value) > max_length:
        raise InspectError(
            f"{display_path}: {label} must contain at most {max_length} characters"
        )
    if value != value.strip():
        raise InspectError(f"{display_path}: {label} must not start or end with whitespace")


def _item_text(chunk: ET.Element, name: str) -> str:
    item = chunk.find(f"./items/item[@name='{name}']")
    return item.text if item is not None and item.text is not None else ""

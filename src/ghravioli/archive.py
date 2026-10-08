"""Construct Grasshopper clipboard archives from validated components."""

from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
from collections.abc import Iterable

from dataclasses import dataclass, field

from ghravioli.constants import (
    ACCESS_CODES,
    BOOLEAN_TOGGLE_COMPONENT_ID,
    COMPONENT_CENTRE_BAND,
    COMPONENT_EDGE_PADDING,
    LABEL_CHARACTER_WIDTH,
    LABEL_PADDING,
    LOG_PANEL_DESCRIPTION,
    MAX_COLUMN_WIDTH,
    MIN_INPUT_WIDTH,
    MIN_OUTPUT_WIDTH,
    MIN_PANEL_HEIGHT,
    NARROW_SLIDER_DIGITS,
    NARROW_SLIDER_RANGE,
    NUMBER_SLIDER_COMPONENT_ID,
    PANEL_COMPONENT_ID,
    PANEL_WIDTH,
    PARAMETER_ROW_HEIGHT,
    PYTHON3_SCRIPT_COMPONENT_ID,
    SCRIPT_VARIABLE_PARAMETER_ID,
    SLIDER_DIGITS,
    SLIDER_TYPES,
    SLIDER_WIDTH,
    STANDARD_OUTPUT_PARAMETER_ID,
    TOGGLE_TYPES,
    TOGGLE_WIDTH,
    VERIFIED_CONVERTERS,
)
from ghravioli.identity import IdentityProvider, UUID4IdentityProvider
from ghravioli.model import ComponentManifest, ComponentPlacement, Port


# A legible archive widens each parameter column to fit the longest label it
# has to show. Grasshopper renders port names in a small proportional face, so
# this is a deliberate over-estimate: a column that is slightly too wide reads
# correctly, whereas one that is too narrow clips the name it exists to reveal.
WIDGET_GAP = 24.0
PANEL_GAP = 24.0


def _column_width(labels: Iterable[str], minimum: float) -> float:
    """Return the column width that fits every label without clipping."""

    longest = max((len(label) for label in labels), default=0)
    measured = longest * LABEL_CHARACTER_WIDTH + LABEL_PADDING
    return min(MAX_COLUMN_WIDTH, max(minimum, measured))


@dataclass(frozen=True)
class _Widget:
    """A stock Grasshopper input object wired into one component port."""

    kind: str
    instance: str
    port: Port
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class _Panel:
    """A Grasshopper panel wired to a component output."""

    instance: str
    source: str
    nickname: str
    description: str
    x: float
    y: float
    width: float
    height: float


@dataclass
class _ComponentPlan:
    """Every identity and coordinate an archive needs, resolved up front.

    Wiring is recorded on the receiving object, so a source identity has to
    exist before the object that references it is written. Planning the whole
    layout first is what makes that ordering possible.
    """

    placement: ComponentPlacement
    instance: str
    input_ids: tuple[str, ...]
    output_ids: tuple[str, ...]
    standard_id: str | None
    input_width: float
    output_width: float
    component_width: float
    component_height: float
    widgets: tuple[_Widget, ...] = ()
    panels: tuple[_Panel, ...] = ()
    sources: dict[int, str] = field(default_factory=dict)

    @property
    def object_count(self) -> int:
        return 1 + len(self.widgets) + len(self.panels)


def build_archive(
    placements: Iterable[ComponentPlacement],
    *,
    document_name: str,
    identities: IdentityProvider | None = None,
) -> bytes:
    """Return a complete UTF-8 `.ghclip` archive without writing it."""

    positioned = tuple(placements)
    if not positioned:
        raise ValueError("an archive requires at least one component")
    if not document_name.strip():
        raise ValueError("document_name must not be empty")
    provider = identities or UUID4IdentityProvider()

    root = ET.Element("Archive", {"name": "Root"})
    root_items = _items(root)
    _version_item(root_items, "ArchiveVersion", major=0, minor=2, revision=2)

    root_chunks = _chunks(root)
    clipboard = _chunk(root_chunks, "Clipboard")
    clipboard_items = _items(clipboard)
    _version_item(clipboard_items, "plugin_version", major=1, minor=0, revision=8)
    clipboard_chunks = _chunks(clipboard)

    _document_header(clipboard_chunks, provider)
    _definition_properties(clipboard_chunks, document_name)
    _rcp_layout(clipboard_chunks)
    _libraries(clipboard_chunks)
    _definition_objects(clipboard_chunks, positioned, provider)

    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="utf-8", short_empty_elements=True)
    declaration = b'<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n'
    return declaration + body + b"\n"


def _document_header(parent: ET.Element, identities: IdentityProvider) -> None:
    chunk = _chunk(parent, "DocumentHeader")
    items = _items(chunk)
    _item(items, "DocumentID", "gh_guid", 9, identities.new())
    _item(items, "Preview", "gh_string", 10, "Shaded")
    _item(items, "PreviewMeshType", "gh_int32", 3, 1)
    _color_item(items, "PreviewNormal", "100;150;0;0")
    _color_item(items, "PreviewSelected", "100;0;150;0")


def _definition_properties(parent: ET.Element, document_name: str) -> None:
    chunk = _chunk(parent, "DefinitionProperties")
    items = _items(chunk)
    _item(items, "Date", "gh_date", 8, 0)
    _item(items, "Description", "gh_string", 10, "")
    _item(items, "KeepOpen", "gh_bool", 1, False)
    _item(items, "Name", "gh_string", 10, document_name)

    chunks = _chunks(chunk)
    revisions = _chunk(chunks, "Revisions")
    revision_items = _items(revisions)
    _item(revision_items, "RevisionCount", "gh_int32", 3, 0)

    projection = _chunk(chunks, "Projection")
    projection_items = _items(projection)
    target = _item(projection_items, "Target", "gh_drawing_point", 30)
    ET.SubElement(target, "X").text = "0"
    ET.SubElement(target, "Y").text = "0"
    _item(projection_items, "Zoom", "gh_single", 5, 1.0)

    views = _chunk(chunks, "Views")
    view_items = _items(views)
    _item(view_items, "ViewCount", "gh_int32", 3, 0)


def _rcp_layout(parent: ET.Element) -> None:
    chunk = _chunk(parent, "RcpLayout")
    items = _items(chunk)
    _item(items, "GroupCount", "gh_int32", 3, 0)


def _libraries(parent: ET.Element) -> None:
    chunk = _chunk(parent, "GHALibraries")
    items = _items(chunk)
    _item(items, "Count", "gh_int32", 3, 1)
    chunks = _chunks(chunk)
    library = _chunk(chunks, "Library", index=0)
    library_items = _items(library)
    _item(library_items, "Author", "gh_string", 10, "Robert McNeel & Associates")
    _item(library_items, "Id", "gh_guid", 9, "00000000-0000-0000-0000-000000000000")
    _item(library_items, "Name", "gh_string", 10, "Grasshopper")
    _item(library_items, "Version", "gh_string", 10, "8.0")


def _plan_component(placement: ComponentPlacement, identities: IdentityProvider) -> _ComponentPlan:
    """Resolve identities, widths and coordinates for one placed component."""

    component = placement.component
    legible = component.legible_names
    input_labels = [port.display_name(legible=legible) for port in component.inputs]
    output_labels = [port.display_name(legible=legible) for port in component.outputs]
    if component.standard_output:
        output_labels.append("out")

    input_width = _column_width(input_labels, MIN_INPUT_WIDTH)
    output_width = _column_width(output_labels, MIN_OUTPUT_WIDTH)
    component_width = (
        2 * COMPONENT_EDGE_PADDING + input_width + COMPONENT_CENTRE_BAND + output_width
    )
    row_count = max(len(component.inputs), len(output_labels), 1)
    component_height = row_count * PARAMETER_ROW_HEIGHT + 2 * COMPONENT_EDGE_PADDING

    instance = identities.new()
    standard_id = identities.new() if component.standard_output else None
    input_ids = tuple(identities.new() for _ in component.inputs)
    output_ids = tuple(identities.new() for _ in component.outputs)

    plan = _ComponentPlan(
        placement=placement,
        instance=instance,
        input_ids=input_ids,
        output_ids=output_ids,
        standard_id=standard_id,
        input_width=input_width,
        output_width=output_width,
        component_width=component_width,
        component_height=component_height,
    )
    if component.input_widgets:
        plan.widgets = _plan_widgets(plan, identities)
    plan.panels = _plan_panels(plan, identities)
    return plan


def _widget_kind(port: Port) -> str | None:
    """Return the widget a port earns, or None when it should stay unwired."""

    if port.access != "item":
        return None
    if port.type in TOGGLE_TYPES:
        return "toggle"
    if port.type in SLIDER_TYPES and port.has_range:
        return "slider"
    return None


def _plan_widgets(plan: _ComponentPlan, identities: IdentityProvider) -> tuple[_Widget, ...]:
    component = plan.placement.component
    widgets: list[_Widget] = []
    for index, port in enumerate(component.inputs):
        kind = _widget_kind(port)
        if kind is None:
            continue
        width = TOGGLE_WIDTH if kind == "toggle" else SLIDER_WIDTH
        instance = identities.new()
        widgets.append(
            _Widget(
                kind=kind,
                instance=instance,
                port=port,
                x=plan.placement.x - WIDGET_GAP - width,
                y=plan.placement.y
                + COMPONENT_EDGE_PADDING
                + index * PARAMETER_ROW_HEIGHT,
                width=width,
                height=PARAMETER_ROW_HEIGHT,
            )
        )
        plan.sources[index] = instance
    return tuple(widgets)


def _plan_panels(plan: _ComponentPlan, identities: IdentityProvider) -> tuple[_Panel, ...]:
    """Place one panel per output that asks for one, stacked down the right.

    A pasted component is only readable if the values it reports are visible
    without wiring anything, so an output that is a diagnostic rather than
    geometry earns a panel of its own.
    """

    component = plan.placement.component
    wanted = [
        (index, port)
        for index, port in enumerate(component.outputs)
        if (component.log_panel if port.name == "log" else port.panel)
    ]
    if not wanted:
        return ()

    height = max(MIN_PANEL_HEIGHT, plan.component_height / len(wanted))
    x = plan.placement.x + plan.component_width + PANEL_GAP
    panels = []
    for row, (index, port) in enumerate(wanted):
        panels.append(
            _Panel(
                instance=identities.new(),
                source=plan.output_ids[index],
                nickname=port.name,
                description=LOG_PANEL_DESCRIPTION if port.name == "log" else port.description,
                x=x,
                y=plan.placement.y + row * (height + PANEL_GAP),
                width=PANEL_WIDTH,
                height=height,
            )
        )
    return tuple(panels)


def _definition_objects(
    parent: ET.Element,
    placements: tuple[ComponentPlacement, ...],
    identities: IdentityProvider,
) -> None:
    plans = [_plan_component(placement, identities) for placement in placements]
    definition = _chunk(parent, "DefinitionObjects")
    items = _items(definition)
    _item(items, "ObjectCount", "gh_int32", 3, sum(plan.object_count for plan in plans))
    chunks = _chunks(definition)

    index = 0
    for plan in plans:
        for widget in plan.widgets:
            _widget_object(chunks, widget, index)
            index += 1
        _component_object(chunks, plan, index)
        index += 1
        for panel in plan.panels:
            _panel_object(chunks, panel, index)
            index += 1


def _component_object(
    parent: ET.Element,
    plan: _ComponentPlan,
    index: int,
) -> None:
    component = plan.placement.component
    object_chunk = _chunk(parent, "Object", index=index)
    object_items = _items(object_chunk)
    _item(object_items, "GUID", "gh_guid", 9, PYTHON3_SCRIPT_COMPONENT_ID)
    _item(object_items, "Name", "gh_string", 10, "Python 3 Script")

    object_chunks = _chunks(object_chunk)
    container = _chunk(object_chunks, "Container")
    container_items = _items(container)
    _item(container_items, "Description", "gh_string", 10, component.description)
    _item(container_items, "GraftStandardOutputLines", "gh_bool", 1, True)
    _item(container_items, "InstanceGuid", "gh_guid", 9, plan.instance)
    _item(container_items, "MarshGuids", "gh_bool", 1, True)
    _item(container_items, "MarshInputs", "gh_bool", 1, True)
    _item(container_items, "MarshOutputs", "gh_bool", 1, True)
    _item(container_items, "Name", "gh_string", 10, "Python 3 Script")
    _item(container_items, "NickName", "gh_string", 10, component.name)
    _item(container_items, "ScriptComponentVersion", "gh_int32", 3, 3)
    _item(container_items, "Tooltip", "gh_string", 10, component.description)
    _item(container_items, "UsingLibraryInputParam", "gh_bool", 1, False)
    _item(container_items, "UsingScriptInputParam", "gh_bool", 1, False)
    _item(container_items, "UsingScriptOutputParam", "gh_bool", 1, False)
    _item(
        container_items,
        "UsingStandardOutputParam",
        "gh_bool",
        1,
        component.standard_output,
    )

    container_chunks = _chunks(container)
    attributes = _chunk(container_chunks, "Attributes")
    _attribute_items(
        attributes,
        plan.placement.x,
        plan.placement.y,
        plan.component_width,
        plan.component_height,
    )
    _parameter_data(container_chunks, plan)
    _script_data(container_chunks, component)
    _script_editor(container_chunks)


def _parameter_data(parent: ET.Element, plan: _ComponentPlan) -> None:
    component = plan.placement.component
    chunk = _chunk(parent, "ParameterData")
    items = _items(chunk)
    _item(items, "InputCount", "gh_int32", 3, len(component.inputs))
    for index, _port in enumerate(component.inputs):
        _item(items, "InputId", "gh_guid", 9, SCRIPT_VARIABLE_PARAMETER_ID, index=index)

    standard = 1 if component.standard_output else 0
    _item(items, "OutputCount", "gh_int32", 3, len(component.outputs) + standard)
    if component.standard_output:
        _item(items, "OutputId", "gh_guid", 9, STANDARD_OUTPUT_PARAMETER_ID, index=0)
    for index, _port in enumerate(component.outputs, start=standard):
        _item(items, "OutputId", "gh_guid", 9, SCRIPT_VARIABLE_PARAMETER_ID, index=index)

    legible = component.legible_names
    chunks = _chunks(chunk)
    for index, port in enumerate(component.inputs):
        _script_parameter(
            chunks,
            "InputParam",
            index,
            port,
            instance=plan.input_ids[index],
            legible=legible,
            x=plan.placement.x + COMPONENT_EDGE_PADDING,
            y=plan.placement.y + COMPONENT_EDGE_PADDING + index * PARAMETER_ROW_HEIGHT,
            width=plan.input_width,
            source=plan.sources.get(index),
        )

    output_x = (
        plan.placement.x + plan.component_width - COMPONENT_EDGE_PADDING - plan.output_width
    )
    if plan.standard_id is not None:
        _standard_output_parameter(
            chunks,
            instance=plan.standard_id,
            x=output_x,
            y=plan.placement.y + COMPONENT_EDGE_PADDING,
            width=plan.output_width,
        )
    for index, port in enumerate(component.outputs, start=standard):
        _script_parameter(
            chunks,
            "OutputParam",
            index,
            port,
            instance=plan.output_ids[index - standard],
            legible=legible,
            x=output_x,
            y=plan.placement.y + COMPONENT_EDGE_PADDING + index * PARAMETER_ROW_HEIGHT,
            width=plan.output_width,
            source=None,
        )


def _script_parameter(
    parent: ET.Element,
    chunk_name: str,
    index: int,
    port: Port,
    *,
    instance: str,
    legible: bool,
    x: float,
    y: float,
    width: float,
    source: str | None,
) -> None:
    chunk = _chunk(parent, chunk_name, index=index)
    items = _items(chunk)
    converter = VERIFIED_CONVERTERS.get(port.type)
    is_input = chunk_name == "InputParam"
    _item(items, "AllowTreeAccess", "gh_bool", 1, is_input)
    _item(items, "Description", "gh_string", 10, port.description)
    _item(items, "InstanceGuid", "gh_guid", 9, instance)
    _item(items, "Name", "gh_string", 10, port.name)
    _item(items, "NickName", "gh_string", 10, port.display_name(legible=legible))
    _item(items, "Optional", "gh_bool", 1, port.optional if is_input else False)
    _item(items, "ScriptParamAccess", "gh_int32", 3, ACCESS_CODES[port.access])
    _item(items, "ScriptParameterVersion", "gh_int32", 3, 2)
    _item(items, "ShowTypeHints", "gh_bool", 1, converter is not None)
    _source_items(items, source)
    _item(items, "ToolTip", "gh_string", 10, port.description)
    if converter is not None:
        _item(items, "TypeHintID", "gh_guid", 9, converter.type_hint_id)

    chunks = _chunks(chunk)
    attributes = _chunk(chunks, "Attributes")
    _attribute_items(attributes, x, y, width, PARAMETER_ROW_HEIGHT)
    if converter is not None:
        converter_data = _chunk(chunks, "ConverterData")
        converter_items = _items(converter_data)
        _item(converter_items, "AssemblyName", "gh_string", 10, converter.assembly_name)
        _item(converter_items, "TypeName", "gh_string", 10, converter.type_name)


def _source_items(parent: ET.Element, source: str | None) -> None:
    """Write the wiring a receiving parameter declares."""

    _item(parent, "SourceCount", "gh_int32", 3, 0 if source is None else 1)
    if source is not None:
        _item(parent, "Source", "gh_guid", 9, source, index=0)


def _standard_output_parameter(
    parent: ET.Element,
    *,
    instance: str,
    x: float,
    y: float,
    width: float,
) -> None:
    chunk = _chunk(parent, "OutputParam", index=0)
    items = _items(chunk)
    _item(
        items,
        "Description",
        "gh_string",
        10,
        "Standard output and errors collected during the script run",
    )
    _item(items, "InstanceGuid", "gh_guid", 9, instance)
    _item(items, "Name", "gh_string", 10, "out")
    _item(items, "NickName", "gh_string", 10, "out")
    _item(items, "Optional", "gh_bool", 1, False)
    _item(items, "SourceCount", "gh_int32", 3, 0)
    chunks = _chunks(chunk)
    attributes = _chunk(chunks, "Attributes")
    _attribute_items(attributes, x, y, width, PARAMETER_ROW_HEIGHT)


def _panel_object(parent: ET.Element, panel: _Panel, index: int) -> None:
    """Write a panel wired to a component output as a live log scratchpad."""

    object_chunk = _chunk(parent, "Object", index=index)
    object_items = _items(object_chunk)
    _item(object_items, "GUID", "gh_guid", 9, PANEL_COMPONENT_ID)
    _item(object_items, "Name", "gh_string", 10, "Panel")

    object_chunks = _chunks(object_chunk)
    container = _chunk(object_chunks, "Container")
    items = _items(container)
    _item(items, "Description", "gh_string", 10, panel.description)
    _item(items, "InstanceGuid", "gh_guid", 9, panel.instance)
    _item(items, "Name", "gh_string", 10, "Panel")
    _item(items, "NickName", "gh_string", 10, panel.nickname)
    _item(items, "Optional", "gh_bool", 1, False)
    _source_items(items, panel.source)
    _item(items, "UserText", "gh_string", 10, "")

    container_chunks = _chunks(container)
    attributes = _chunk(container_chunks, "Attributes")
    _attribute_items(attributes, panel.x, panel.y, panel.width, panel.height)
    properties = _chunk(container_chunks, "Properties")
    property_items = _items(properties)
    _item(property_items, "Alignment", "gh_int32", 3, 0)
    _item(property_items, "DrawIndices", "gh_bool", 1, False)
    _item(property_items, "DrawPaths", "gh_bool", 1, False)
    _item(property_items, "Multiline", "gh_bool", 1, True)
    _item(property_items, "Wrap", "gh_bool", 1, False)


def _widget_object(parent: ET.Element, widget: _Widget, index: int) -> None:
    """Write one stock input object wired into a component port."""

    if widget.kind == "toggle":
        guid, name = BOOLEAN_TOGGLE_COMPONENT_ID, "Boolean Toggle"
    else:
        guid, name = NUMBER_SLIDER_COMPONENT_ID, "Number Slider"

    object_chunk = _chunk(parent, "Object", index=index)
    object_items = _items(object_chunk)
    _item(object_items, "GUID", "gh_guid", 9, guid)
    _item(object_items, "Name", "gh_string", 10, name)

    object_chunks = _chunks(object_chunk)
    container = _chunk(object_chunks, "Container")
    items = _items(container)
    _item(items, "Description", "gh_string", 10, widget.port.description)
    _item(items, "InstanceGuid", "gh_guid", 9, widget.instance)
    _item(items, "Name", "gh_string", 10, name)
    _item(items, "NickName", "gh_string", 10, widget.port.name)
    _item(items, "Optional", "gh_bool", 1, False)
    _item(items, "SourceCount", "gh_int32", 3, 0)
    if widget.kind == "toggle":
        _item(items, "Boolean", "gh_bool", 1, bool(widget.port.default))

    container_chunks = _chunks(container)
    attributes = _chunk(container_chunks, "Attributes")
    _attribute_items(attributes, widget.x, widget.y, widget.width, widget.height)
    if widget.kind == "slider":
        _slider_chunk(container_chunks, widget.port)


def _slider_chunk(parent: ET.Element, port: Port) -> None:
    minimum = float(port.minimum or 0.0)
    maximum = float(port.maximum or 0.0)
    default = port.default
    value = float(default) if isinstance(default, (int, float)) else minimum
    digits = (
        NARROW_SLIDER_DIGITS
        if (maximum - minimum) < NARROW_SLIDER_RANGE
        else SLIDER_DIGITS
    )
    slider = _chunk(parent, "Slider")
    items = _items(slider)
    _item(items, "GripDisplay", "gh_int32", 3, 0)
    _item(items, "Interval", "gh_int32", 3, 0 if port.type == "float" else 1)
    _item(items, "Max", "gh_decimal", 7, maximum)
    _item(items, "Min", "gh_decimal", 7, minimum)
    _item(items, "Digits", "gh_int32", 3, digits)
    _item(items, "Value", "gh_decimal", 7, value)


def _script_data(parent: ET.Element, component: ComponentManifest) -> None:
    chunk = _chunk(parent, "Script")
    items = _items(chunk)
    encoded = base64.b64encode(component.source_text.encode("utf-8")).decode("ascii")
    _item(items, "MarshGuids", "gh_bool", 1, True)
    _item(items, "MarshInputs", "gh_bool", 1, True)
    _item(items, "MarshOutputs", "gh_bool", 1, True)
    _item(items, "Text", "gh_string", 10, encoded)
    _item(items, "Title", "gh_string", 10, component.name)

    chunks = _chunks(chunk)
    language = _chunk(chunks, "LanguageSpec")
    language_items = _items(language)
    _item(language_items, "Taxon", "gh_string", 10, "*.*.python")
    _item(language_items, "Version", "gh_string", 10, "3.*")


def _script_editor(parent: ET.Element) -> None:
    chunk = _chunk(parent, "ScriptEditor")
    items = _items(chunk)
    bounds = _item(items, "StartBounds", "gh_drawing_rectangle", 34)
    for key, value in (("X", 100), ("Y", 100), ("W", 700), ("H", 700)):
        ET.SubElement(bounds, key).text = str(value)


def _attribute_items(parent: ET.Element, x: float, y: float, width: float, height: float) -> None:
    items = _items(parent)
    bounds = _item(items, "Bounds", "gh_drawing_rectanglef", 35)
    for key, value in (("X", x), ("Y", y), ("W", width), ("H", height)):
        ET.SubElement(bounds, key).text = _text(value)

    pivot = _item(items, "Pivot", "gh_drawing_pointf", 31)
    ET.SubElement(pivot, "X").text = _text(x + width / 2.0)
    ET.SubElement(pivot, "Y").text = _text(y + height / 2.0)
    _item(items, "Selected", "gh_bool", 1, True)


def _color_item(parent: ET.Element, name: str, argb: str) -> None:
    color = _item(parent, name, "gh_drawing_color", 36)
    ET.SubElement(color, "ARGB").text = argb


def _version_item(parent: ET.Element, name: str, *, major: int, minor: int, revision: int) -> None:
    version = _item(parent, name, "gh_version", 80)
    ET.SubElement(version, "Major").text = str(major)
    ET.SubElement(version, "Minor").text = str(minor)
    ET.SubElement(version, "Revision").text = str(revision)


def _items(parent: ET.Element) -> ET.Element:
    return ET.SubElement(parent, "items", {"count": "0"})


def _chunks(parent: ET.Element) -> ET.Element:
    return ET.SubElement(parent, "chunks", {"count": "0"})


def _item(
    parent: ET.Element,
    name: str,
    type_name: str,
    type_code: int,
    value: object | None = None,
    *,
    index: int | None = None,
) -> ET.Element:
    attributes = {"name": name, "type_name": type_name, "type_code": str(type_code)}
    if index is not None:
        attributes["index"] = str(index)
    element = ET.SubElement(parent, "item", attributes)
    if value is not None:
        element.text = _text(value)
    parent.set("count", str(len(parent)))
    return element


def _chunk(parent: ET.Element, name: str, *, index: int | None = None) -> ET.Element:
    attributes = {"name": name}
    if index is not None:
        attributes["index"] = str(index)
    element = ET.SubElement(parent, "chunk", attributes)
    parent.set("count", str(len(parent)))
    return element


def _text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(value, ".15g")
    return str(value)

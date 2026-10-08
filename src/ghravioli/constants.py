"""Functional identifiers used by the Grasshopper clipboard format."""

from __future__ import annotations

from dataclasses import dataclass


# These values identify external Grasshopper object and parameter types. They
# are interoperability data; no Rhino or Grasshopper binary code is bundled.
PYTHON3_SCRIPT_COMPONENT_ID = "719467e6-7cf5-4848-99b0-c5dd57e5442c"
SCRIPT_VARIABLE_PARAMETER_ID = "08908df5-fa14-4982-9ab2-1aa0927566aa"
STANDARD_OUTPUT_PARAMETER_ID = "3ede854e-c753-40eb-84cb-b48008f14fd4"
MAX_ARCHIVE_BYTES = 10 * 1024 * 1024

# Companion canvas objects. These identify stock Grasshopper parameters that a
# generated archive can place beside a component so a pasted definition is
# immediately readable and drivable. They are interoperability identifiers in
# exactly the same sense as the component identifier above; no Grasshopper
# binary code is bundled. Rhino accepts the object shapes on the recorded
# Windows release; per-object configuration remains under manual acceptance.
PANEL_COMPONENT_ID = "59e0b89a-e487-49f8-bab8-b5bab16be14c"
BOOLEAN_TOGGLE_COMPONENT_ID = "2e78987b-9dfb-42a2-8b76-3923ac8bd91a"
NUMBER_SLIDER_COMPONENT_ID = "57da07bd-ecab-415d-9d86-af36d7073abc"

COMPANION_COMPONENT_IDS = {
    "panel": PANEL_COMPONENT_ID,
    "toggle": BOOLEAN_TOGGLE_COMPONENT_ID,
    "slider": NUMBER_SLIDER_COMPONENT_ID,
}

# Widget selection by declared port type. A boolean always earns a toggle; a
# number only earns a slider when the manifest supplies a range, because a
# slider with an invented domain is worse than no slider at all.
TOGGLE_TYPES = frozenset({"bool"})
SLIDER_TYPES = frozenset({"float", "int"})

# Canvas values shared by the writer and the strict generated-archive grammar.
# Keeping these in one place prevents inspection from accepting layouts or
# slider metadata that the writer cannot produce.
PARAMETER_ROW_HEIGHT = 20.0
COMPONENT_CENTRE_BAND = 30.0
COMPONENT_EDGE_PADDING = 2.0
MIN_INPUT_WIDTH = 42.0
MIN_OUTPUT_WIDTH = 37.0
LABEL_CHARACTER_WIDTH = 7.0
LABEL_PADDING = 10.0
MAX_COLUMN_WIDTH = 240.0
TOGGLE_WIDTH = 60.0
SLIDER_WIDTH = 130.0
PANEL_WIDTH = 240.0
MIN_PANEL_HEIGHT = 80.0
LOG_PANEL_DESCRIPTION = "Live view of the component log output"
SLIDER_DIGITS = 3
NARROW_SLIDER_RANGE = 1.0
NARROW_SLIDER_DIGITS = 4


@dataclass(frozen=True, slots=True)
class Converter:
    """Verified converter metadata for a Grasshopper Python port hint."""

    type_hint_id: str
    assembly_name: str
    type_name: str


VERIFIED_CONVERTERS = {
    "str": Converter(
        "3aceb454-6dbd-4c5b-9b6b-e71f8c1cdf88",
        "System.Private.CoreLib",
        "System.String",
    ),
    "float": Converter(
        "9d51e32e-c038-4352-9554-f4137ca91b9a",
        "System.Private.CoreLib",
        "System.Double",
    ),
    "bool": Converter(
        "d60527f5-b5af-4ef6-8970-5f96fe412559",
        "System.Private.CoreLib",
        "System.Boolean",
    ),
    "point": Converter(
        "e1937b56-b1da-4c12-8bd8-e34ee81746ef",
        "RhinoCommon",
        "Rhino.Geometry.Point3d",
    ),
    "brep": Converter(
        "2ceb0405-fdfe-403d-a4d6-8786da45fb9d",
        "RhinoCommon",
        "Rhino.Geometry.Brep",
    ),
}

ACCESS_CODES = {"item": 0, "list": 1}

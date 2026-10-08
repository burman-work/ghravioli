"""Canvas presentation: legible names, wired companions and the standard output."""

from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

from ghravioli.archive import build_archive
from ghravioli.build import build_bytes
from ghravioli.errors import ManifestError
from ghravioli.identity import SequenceIdentityProvider
from ghravioli.inspect import InspectError, inspect_archive_bytes
from ghravioli.manifest import load_manifest
from ghravioli.model import ComponentManifest, ComponentPlacement


SOURCE = "log = 'ready'\n"

BASE_PORTS = """
[[inputs]]
name = "curves"
nickname = "C"
type = "curve"
access = "list"

[[inputs]]
name = "step_size"
nickname = "S"
type = "float"
access = "item"
min = 0.0
max = 0.5
default = 0.06

[[inputs]]
name = "reverse"
nickname = "Rev"
type = "bool"
access = "item"
default = true

[[inputs]]
name = "tolerance"
nickname = "Tol"
type = "float"
access = "item"

[[outputs]]
name = "log"
type = "str"
access = "item"
"""


class CanvasTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "component.py").write_text(SOURCE, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_manifest(self, flags: str = "", ports: str = BASE_PORTS) -> Path:
        path = self.root / "component.toml"
        path.write_text(
            "kind = \"component\"\n"
            "schema_version = 1\n"
            "target = \"rhino8-python3\"\n"
            "target_python = \"3.9\"\n"
            "id = \"canvas-demo\"\n"
            "name = \"Canvas Demo\"\n"
            "source = \"component.py\"\n"
            f"{flags}{ports}",
            encoding="utf-8",
        )
        return path

    def build(self, flags: str = "", ports: str = BASE_PORTS) -> ET.Element:
        archive = build_bytes(self.write_manifest(flags, ports))
        # Every generated archive must survive the strict grammar unchanged.
        inspect_archive_bytes(archive, display_path="canvas.ghclip")
        return ET.fromstring(archive)

    @staticmethod
    def objects(root: ET.Element, name: str) -> list[ET.Element]:
        return [
            chunk
            for chunk in root.findall(
                ".//chunk[@name='DefinitionObjects']/chunks/chunk[@name='Object']"
            )
            if chunk.findtext("./items/item[@name='Name']") == name
        ]

    @staticmethod
    def port_nicknames(root: ET.Element, chunk_name: str) -> list[str]:
        return [
            chunk.findtext("./items/item[@name='NickName']") or ""
            for chunk in root.findall(f".//chunk[@name='ParameterData']/chunks/chunk[@name='{chunk_name}']")
        ]

    @staticmethod
    def archive_bytes(root: ET.Element) -> bytes:
        return ET.tostring(root, encoding="utf-8")

    @staticmethod
    def resize_attributes(
        attributes: ET.Element,
        *,
        width: float | None = None,
        height: float | None = None,
    ) -> None:
        bounds = attributes.find("./items/item[@name='Bounds']")
        pivot = attributes.find("./items/item[@name='Pivot']")
        assert bounds is not None and pivot is not None
        width_item = bounds.find("W")
        height_item = bounds.find("H")
        pivot_x = pivot.find("X")
        pivot_y = pivot.find("Y")
        assert width_item is not None and height_item is not None
        assert pivot_x is not None and pivot_y is not None
        if width is not None:
            x = float(bounds.findtext("X") or "0")
            width_item.text = format(width, ".15g")
            pivot_x.text = format(x + width / 2.0, ".15g")
        if height is not None:
            y = float(bounds.findtext("Y") or "0")
            height_item.text = format(height, ".15g")
            pivot_y.text = format(y + height / 2.0, ".15g")

    # --- legible names ----------------------------------------------------

    def test_legible_names_show_the_full_port_name_by_default(self) -> None:
        root = self.build()
        nicknames = self.port_nicknames(root, "InputParam")
        self.assertEqual(nicknames, ["curves", "step_size", "reverse", "tolerance"])
        self.assertEqual(self.port_nicknames(root, "OutputParam"), ["out", "log"])

    def test_legible_names_can_be_turned_off_for_the_declared_nickname(self) -> None:
        root = self.build(flags="legible_names = false\n")
        self.assertEqual(
            self.port_nicknames(root, "InputParam"),
            ["C", "S", "Rev", "Tol"],
        )

    def test_legible_columns_widen_to_fit_the_longest_label(self) -> None:
        legible = self.build()
        terse = self.build(flags="legible_names = false\n")

        def input_width(root: ET.Element) -> float:
            bounds = root.find(
                ".//chunk[@name='InputParam']/chunks/chunk[@name='Attributes']"
                "/items/item[@name='Bounds']"
            )
            assert bounds is not None
            return float(bounds.findtext("W") or "0")

        self.assertGreater(input_width(legible), input_width(terse))
        # A terse archive keeps the historical minimum column width.
        self.assertEqual(input_width(terse), 42.0)

    def test_component_width_matches_the_sum_of_its_columns(self) -> None:
        root = self.build()
        component = self.objects(root, "Python 3 Script")[0]
        bounds = component.find(
            "./chunks/chunk[@name='Container']/chunks/chunk[@name='Attributes']"
            "/items/item[@name='Bounds']"
        )
        assert bounds is not None
        widths = {
            chunk_name: float(
                root.find(
                    f".//chunk[@name='{chunk_name}']/chunks/chunk[@name='Attributes']"
                    "/items/item[@name='Bounds']"
                ).findtext("W")
                or "0"
            )
            for chunk_name in ("InputParam", "OutputParam")
        }
        self.assertEqual(
            float(bounds.findtext("W") or "0"),
            4 + widths["InputParam"] + 30 + widths["OutputParam"],
        )

    # --- log panel --------------------------------------------------------

    def test_log_panel_is_placed_and_wired_to_the_log_output_by_default(self) -> None:
        root = self.build()
        panels = self.objects(root, "Panel")
        self.assertEqual(len(panels), 1)
        container = panels[0].find("./chunks/chunk[@name='Container']")
        assert container is not None
        self.assertEqual(container.findtext("./items/item[@name='NickName']"), "log")
        source = container.findtext("./items/item[@name='Source']")

        log_output = [
            chunk
            for chunk in root.findall(".//chunk[@name='ParameterData']/chunks/chunk[@name='OutputParam']")
            if chunk.findtext("./items/item[@name='Name']") == "log"
        ][0]
        self.assertEqual(source, log_output.findtext("./items/item[@name='InstanceGuid']"))

    def test_log_panel_can_be_turned_off(self) -> None:
        root = self.build(flags="log_panel = false\n")
        self.assertEqual(self.objects(root, "Panel"), [])

    def test_historical_log_panel_description_remains_inspectable(self) -> None:
        root = self.build()
        description = self.objects(root, "Panel")[0].find(
            "./chunks/chunk[@name='Container']/items/item[@name='Description']"
        )
        assert description is not None
        description.text = "Live view of the component log output"
        inspect_archive_bytes(self.archive_bytes(root), display_path="historical.ghclip")

    def test_requested_output_panel_survives_disabled_log_panel(self) -> None:
        ports = BASE_PORTS + '''
[[outputs]]
name = "valid"
description = "Whether the result is valid."
type = "bool"
access = "item"
panel = true
'''
        root = self.build(flags="log_panel = false\n", ports=ports)
        panels = self.objects(root, "Panel")
        self.assertEqual(len(panels), 1)
        self.assertEqual(
            panels[0].findtext("./chunks/chunk[@name='Container']/items/item[@name='NickName']"),
            "valid",
        )

    def test_historical_log_description_is_rejected_on_another_output(self) -> None:
        ports = BASE_PORTS + '''
[[outputs]]
name = "valid"
description = "Whether the result is valid."
type = "bool"
access = "item"
panel = true
'''
        root = self.build(ports=ports)
        panel = next(
            obj for obj in self.objects(root, "Panel")
            if obj.findtext("./chunks/chunk[@name='Container']/items/item[@name='NickName']") == "valid"
        )
        description = panel.find("./chunks/chunk[@name='Container']/items/item[@name='Description']")
        assert description is not None
        description.text = "Live view of the component log output"
        with self.assertRaisesRegex(InspectError, "panel metadata"):
            inspect_archive_bytes(self.archive_bytes(root), display_path="mismatched.ghclip")

    def test_log_panel_sits_clear_of_the_component_it_reports_on(self) -> None:
        root = self.build()
        component = self.objects(root, "Python 3 Script")[0].find(
            "./chunks/chunk[@name='Container']/chunks/chunk[@name='Attributes']"
            "/items/item[@name='Bounds']"
        )
        panel = self.objects(root, "Panel")[0].find(
            "./chunks/chunk[@name='Container']/chunks/chunk[@name='Attributes']"
            "/items/item[@name='Bounds']"
        )
        assert component is not None and panel is not None
        component_right = float(component.findtext("X") or "0") + float(component.findtext("W") or "0")
        self.assertGreater(float(panel.findtext("X") or "0"), component_right)

    # --- input widgets ----------------------------------------------------

    def test_boolean_input_earns_a_wired_toggle_carrying_its_default(self) -> None:
        root = self.build()
        toggles = self.objects(root, "Boolean Toggle")
        self.assertEqual(len(toggles), 1)
        container = toggles[0].find("./chunks/chunk[@name='Container']")
        assert container is not None
        self.assertEqual(container.findtext("./items/item[@name='NickName']"), "reverse")
        self.assertEqual(container.findtext("./items/item[@name='Boolean']"), "true")

        wired = [
            chunk
            for chunk in root.findall(".//chunk[@name='ParameterData']/chunks/chunk[@name='InputParam']")
            if chunk.findtext("./items/item[@name='Name']") == "reverse"
        ][0]
        self.assertEqual(
            wired.findtext("./items/item[@name='Source']"),
            container.findtext("./items/item[@name='InstanceGuid']"),
        )

    def test_only_a_numeric_input_with_a_declared_range_earns_a_slider(self) -> None:
        root = self.build()
        sliders = self.objects(root, "Number Slider")
        self.assertEqual(len(sliders), 1)
        container = sliders[0].find("./chunks/chunk[@name='Container']")
        assert container is not None
        # step_size declares min/max; tolerance does not, so it stays bare.
        self.assertEqual(container.findtext("./items/item[@name='NickName']"), "step_size")
        slider = container.find("./chunks/chunk[@name='Slider']")
        assert slider is not None
        self.assertEqual(slider.findtext("./items/item[@name='Min']"), "0")
        self.assertEqual(slider.findtext("./items/item[@name='Max']"), "0.5")
        self.assertEqual(slider.findtext("./items/item[@name='Value']"), "0.06")

    def test_widgets_can_be_turned_off(self) -> None:
        root = self.build(flags="input_widgets = false\n")
        self.assertEqual(self.objects(root, "Boolean Toggle"), [])
        self.assertEqual(self.objects(root, "Number Slider"), [])
        # The log panel is a separate decision and stays.
        self.assertEqual(len(self.objects(root, "Panel")), 1)

    def test_list_access_ports_never_earn_a_single_value_widget(self) -> None:
        ports = """
[[inputs]]
name = "flags"
type = "bool"
access = "list"

[[outputs]]
name = "log"
type = "str"
access = "item"
"""
        root = self.build(ports=ports)
        self.assertEqual(self.objects(root, "Boolean Toggle"), [])

    # --- standard output --------------------------------------------------

    def test_standard_output_is_present_by_default(self) -> None:
        root = self.build()
        container = self.objects(root, "Python 3 Script")[0].find("./chunks/chunk[@name='Container']")
        assert container is not None
        self.assertEqual(
            container.findtext("./items/item[@name='UsingStandardOutputParam']"),
            "true",
        )
        self.assertIn("out", self.port_nicknames(root, "OutputParam"))

    def test_standard_output_can_be_removed(self) -> None:
        root = self.build(flags="standard_output = false\n")
        container = self.objects(root, "Python 3 Script")[0].find("./chunks/chunk[@name='Container']")
        assert container is not None
        self.assertEqual(
            container.findtext("./items/item[@name='UsingStandardOutputParam']"),
            "false",
        )
        self.assertEqual(self.port_nicknames(root, "OutputParam"), ["log"])

    # --- manifest validation ---------------------------------------------

    def test_manifest_rejects_incoherent_widget_declarations(self) -> None:
        cases = {
            "min without max": ('name = "v"\ntype = "float"\naccess = "item"\nmin = 0.0\n', "together"),
            "default outside range": (
                'name = "v"\ntype = "float"\naccess = "item"\nmin = 0.0\nmax = 1.0\ndefault = 2.0\n',
                "between min and max",
            ),
            "inverted range": (
                'name = "v"\ntype = "float"\naccess = "item"\nmin = 1.0\nmax = 0.0\n',
                "smaller than max",
            ),
            "range on a bool": (
                'name = "v"\ntype = "bool"\naccess = "item"\nmin = 0.0\nmax = 1.0\n',
                "does not apply to a bool",
            ),
            "range on a curve": (
                'name = "v"\ntype = "curve"\naccess = "item"\nmin = 0.0\nmax = 1.0\n',
                "do not apply",
            ),
            "widget on a list port": (
                'name = "v"\ntype = "float"\naccess = "list"\nmin = 0.0\nmax = 1.0\n',
                "item access",
            ),
            "numeric default without a range": (
                'name = "v"\ntype = "float"\naccess = "item"\ndefault = 0.5\n',
                "requires min and max",
            ),
            "fractional integer range": (
                'name = "v"\ntype = "int"\naccess = "item"\nmin = 0.5\nmax = 2.5\n',
                "whole number",
            ),
        }
        for label, (port, message) in cases.items():
            with self.subTest(label=label):
                ports = f"\n[[inputs]]\n{port}\n[[outputs]]\nname = \"log\"\ntype = \"str\"\naccess = \"item\"\n"
                path = self.write_manifest(ports=ports)
                with self.assertRaisesRegex(ManifestError, message):
                    load_manifest(path)

    def test_canvas_flags_must_be_booleans(self) -> None:
        path = self.write_manifest(flags='log_panel = "yes"\n')
        with self.assertRaisesRegex(ManifestError, "must be a boolean"):
            load_manifest(path)

    def test_a_widget_may_not_itself_be_driven(self) -> None:
        """A widget drives a component; nothing may drive a widget."""

        archive = build_bytes(self.write_manifest())
        root = ET.fromstring(archive)
        toggle = [
            chunk
            for chunk in root.findall(
                ".//chunk[@name='DefinitionObjects']/chunks/chunk[@name='Object']"
            )
            if chunk.findtext("./items/item[@name='Name']") == "Boolean Toggle"
        ][0]
        items = toggle.find("./chunks/chunk[@name='Container']/items")
        assert items is not None
        source = ET.SubElement(
            items,
            "item",
            {"name": "Source", "type_name": "gh_guid", "type_code": "9", "index": "0"},
        )
        source.text = "00000000-0000-0000-0000-000000000000"
        items.set("count", str(len(items)))

        with self.assertRaises(Exception) as caught:
            inspect_archive_bytes(ET.tostring(root, encoding="utf-8"), display_path="w.ghclip")
        self.assertRegex(str(caught.exception), "source connection|unexpected item")

    def test_inspection_rejects_input_wiring_from_a_non_widget_object(self) -> None:
        root = self.build()
        panel = self.objects(root, "Panel")[0]
        panel_instance = panel.findtext(
            "./chunks/chunk[@name='Container']/items/item[@name='InstanceGuid']"
        )
        source = root.find(
            ".//chunk[@name='InputParam']/items/item[@name='Source']"
        )
        assert panel_instance is not None and source is not None
        source.text = panel_instance

        with self.assertRaisesRegex(InspectError, "input source.*widget"):
            inspect_archive_bytes(self.archive_bytes(root), display_path="w.ghclip")

    def test_inspection_rejects_the_wrong_widget_kind_for_an_input(self) -> None:
        root = self.build()
        slider = self.objects(root, "Number Slider")[0]
        slider_instance = slider.findtext(
            "./chunks/chunk[@name='Container']/items/item[@name='InstanceGuid']"
        )
        bool_input = [
            chunk
            for chunk in root.findall(".//chunk[@name='InputParam']")
            if chunk.findtext("./items/item[@name='Name']") == "reverse"
        ][0]
        source = bool_input.find("./items/item[@name='Source']")
        assert slider_instance is not None and source is not None
        source.text = slider_instance

        with self.assertRaisesRegex(InspectError, "widget kind"):
            inspect_archive_bytes(self.archive_bytes(root), display_path="w.ghclip")

    def test_inspection_rejects_a_widget_on_a_non_numeric_non_boolean_input(self) -> None:
        ports = """
[[inputs]]
name = "step_size"
type = "float"
access = "item"
min = 0.0
max = 1.0

[[inputs]]
name = "message"
type = "str"
access = "item"

[[outputs]]
name = "log"
type = "str"
access = "item"
"""
        root = self.build(ports=ports)
        inputs = {
            chunk.findtext("./items/item[@name='Name']"): chunk
            for chunk in root.findall(".//chunk[@name='InputParam']")
        }
        float_items = inputs["step_size"].find("./items")
        string_items = inputs["message"].find("./items")
        assert float_items is not None and string_items is not None
        source = float_items.find("./item[@name='Source']")
        float_count = float_items.find("./item[@name='SourceCount']")
        string_count = string_items.find("./item[@name='SourceCount']")
        assert source is not None and float_count is not None and string_count is not None
        float_items.remove(source)
        float_count.text = "0"
        float_items.set("count", str(len(float_items)))
        string_count.text = "1"
        string_items.insert(list(string_items).index(string_count) + 1, source)
        string_items.set("count", str(len(string_items)))

        slider = self.objects(root, "Number Slider")[0]
        slider_nickname = slider.find(
            "./chunks/chunk[@name='Container']/items/item[@name='NickName']"
        )
        interval = slider.find(
            "./chunks/chunk[@name='Container']/chunks/chunk[@name='Slider']"
            "/items/item[@name='Interval']"
        )
        assert slider_nickname is not None and interval is not None
        slider_nickname.text = "message"
        interval.text = "1"

        with self.assertRaisesRegex(InspectError, "widget-compatible"):
            inspect_archive_bytes(self.archive_bytes(root), display_path="w.ghclip")

    def test_inspection_rejects_panel_wiring_to_something_that_is_not_an_output(self) -> None:
        root = self.build()
        toggle = self.objects(root, "Boolean Toggle")[0]
        toggle_instance = toggle.findtext(
            "./chunks/chunk[@name='Container']/items/item[@name='InstanceGuid']"
        )
        panel_source = self.objects(root, "Panel")[0].find(
            "./chunks/chunk[@name='Container']/items/item[@name='Source']"
        )
        assert toggle_instance is not None and panel_source is not None
        panel_source.text = toggle_instance

        with self.assertRaisesRegex(InspectError, "panel source.*declared output"):
            inspect_archive_bytes(self.archive_bytes(root), display_path="w.ghclip")

    def test_inspection_rejects_an_unwired_panel(self) -> None:
        root = self.build()
        panel_items = self.objects(root, "Panel")[0].find(
            "./chunks/chunk[@name='Container']/items"
        )
        assert panel_items is not None
        source = panel_items.find("./item[@name='Source']")
        source_count = panel_items.find("./item[@name='SourceCount']")
        assert source is not None and source_count is not None
        panel_items.remove(source)
        source_count.text = "0"
        panel_items.set("count", str(len(panel_items)))

        with self.assertRaisesRegex(InspectError, "Panel.*Source|panel source"):
            inspect_archive_bytes(self.archive_bytes(root), display_path="w.ghclip")

    def test_inspection_rejects_noncanonical_companion_metadata(self) -> None:
        cases = (
            ("Description", "not generated", "panel metadata"),
            ("NickName", "not-log", "panel metadata"),
            ("UserText", "hidden payload", "UserText"),
        )
        for item_name, replacement, message in cases:
            with self.subTest(item=item_name):
                root = self.build()
                item = self.objects(root, "Panel")[0].find(
                    f"./chunks/chunk[@name='Container']/items/item[@name='{item_name}']"
                )
                assert item is not None
                item.text = replacement
                with self.assertRaisesRegex(InspectError, message):
                    inspect_archive_bytes(self.archive_bytes(root), display_path="w.ghclip")

    def test_inspection_rejects_noncanonical_slider_values(self) -> None:
        cases = (
            ("Interval", "7"),
            ("Max", "-1"),
            ("Digits", "2"),
            ("Value", "2"),
        )
        for item_name, replacement in cases:
            with self.subTest(item=item_name):
                root = self.build()
                item = self.objects(root, "Number Slider")[0].find(
                    f"./chunks/chunk[@name='Container']/chunks/chunk[@name='Slider']"
                    f"/items/item[@name='{item_name}']"
                )
                assert item is not None
                item.text = replacement
                with self.assertRaisesRegex(InspectError, item_name):
                    inspect_archive_bytes(self.archive_bytes(root), display_path="w.ghclip")

    def test_inspection_rejects_noncanonical_companion_widths(self) -> None:
        cases = (
            ("Panel", 241.0),
            ("Boolean Toggle", 61.0),
            ("Number Slider", 131.0),
        )
        for object_name, width in cases:
            with self.subTest(object=object_name):
                root = self.build()
                attributes = self.objects(root, object_name)[0].find(
                    "./chunks/chunk[@name='Container']/chunks/chunk[@name='Attributes']"
                )
                assert attributes is not None
                self.resize_attributes(attributes, width=width)
                with self.assertRaisesRegex(InspectError, "Bounds|width"):
                    inspect_archive_bytes(self.archive_bytes(root), display_path="w.ghclip")

    def test_inspection_rejects_a_panel_shorter_than_the_generated_minimum(self) -> None:
        root = self.build()
        attributes = self.objects(root, "Panel")[0].find(
            "./chunks/chunk[@name='Container']/chunks/chunk[@name='Attributes']"
        )
        assert attributes is not None
        self.resize_attributes(attributes, height=79.0)

        with self.assertRaisesRegex(InspectError, "Panel.*height"):
            inspect_archive_bytes(self.archive_bytes(root), display_path="w.ghclip")

    def test_inspection_rejects_standard_output_flag_mismatch(self) -> None:
        root = self.build()
        flag = self.objects(root, "Python 3 Script")[0].find(
            "./chunks/chunk[@name='Container']/items/item[@name='UsingStandardOutputParam']"
        )
        assert flag is not None
        flag.text = "false"

        with self.assertRaisesRegex(InspectError, "UsingStandardOutputParam"):
            inspect_archive_bytes(self.archive_bytes(root), display_path="w.ghclip")

    def test_inspection_rejects_column_width_not_generated_from_labels(self) -> None:
        root = self.build()
        input_attributes = root.findall(
            ".//chunk[@name='InputParam']/chunks/chunk[@name='Attributes']"
        )
        assert input_attributes
        current_width = float(
            input_attributes[0].findtext("./items/item[@name='Bounds']/W") or "0"
        )
        for attributes in input_attributes:
            self.resize_attributes(attributes, width=current_width + 1.0)

        component_attributes = self.objects(root, "Python 3 Script")[0].find(
            "./chunks/chunk[@name='Container']/chunks/chunk[@name='Attributes']"
        )
        assert component_attributes is not None
        component_width = float(
            component_attributes.findtext("./items/item[@name='Bounds']/W") or "0"
        )
        self.resize_attributes(component_attributes, width=component_width + 1.0)

        with self.assertRaisesRegex(InspectError, "column width"):
            inspect_archive_bytes(self.archive_bytes(root), display_path="w.ghclip")

    def test_object_limit_allows_the_companions_of_valid_components(self) -> None:
        ports = "".join(
            f'\n[[inputs]]\nname = "flag_{index}"\ntype = "bool"\naccess = "item"\n'
            for index in range(128)
        )
        ports += '\n[[outputs]]\nname = "log"\ntype = "str"\naccess = "item"\n'
        manifest = load_manifest(self.write_manifest(ports=ports))
        assert isinstance(manifest, ComponentManifest)
        second = replace(manifest, id="canvas-demo-2", name="Canvas Demo 2")
        archive = build_archive(
            (
                ComponentPlacement(manifest, x=0.0, y=0.0),
                ComponentPlacement(second, x=500.0, y=0.0),
            ),
            document_name="many-companions",
            identities=SequenceIdentityProvider(),
        )

        try:
            summary = inspect_archive_bytes(archive, display_path="many.ghclip")
        except InspectError as error:
            self.fail(f"valid generated companions were rejected: {error}")
        self.assertEqual(len(summary["components"]), 2)
        self.assertEqual(summary["object_count"], 260)

    # --- output panels ----------------------------------------------------

    def test_an_output_can_request_its_own_panel(self) -> None:
        """A diagnostic output is only useful if it is visible without wiring."""

        ports = BASE_PORTS.replace(
            '''
[[outputs]]
name = "log"
type = "str"
access = "item"
''',
            '''
[[outputs]]
name = "all_closed"
description = "True only if every output curve is closed."
type = "bool"
access = "item"
panel = true

[[outputs]]
name = "log"
type = "str"
access = "item"
''',
        )
        root = self.build(ports=ports)
        panels = self.objects(root, "Panel")
        nicknames = sorted(
            panel.findtext("./chunks/chunk[@name='Container']/items/item[@name='NickName']") or ""
            for panel in panels
        )
        self.assertEqual(nicknames, ["all_closed", "log"])

        # Each panel reads the output it names, and no output feeds two panels.
        outputs = {
            chunk.findtext("./items/item[@name='Name']"):
                chunk.findtext("./items/item[@name='InstanceGuid']")
            for chunk in root.findall(
                ".//chunk[@name='ParameterData']/chunks/chunk[@name='OutputParam']"
            )
        }
        for panel in panels:
            container = panel.find("./chunks/chunk[@name='Container']")
            assert container is not None
            nickname = container.findtext("./items/item[@name='NickName']")
            self.assertEqual(
                container.findtext("./items/item[@name='Source']"),
                outputs[nickname],
            )

    def test_output_panels_do_not_overlap_each_other(self) -> None:
        ports = BASE_PORTS.replace(
            '''
[[outputs]]
name = "log"
type = "str"
access = "item"
''',
            '''
[[outputs]]
name = "all_closed"
type = "bool"
access = "item"
panel = true

[[outputs]]
name = "log"
type = "str"
access = "item"
''',
        )
        root = self.build(ports=ports)
        boxes = []
        for panel in self.objects(root, "Panel"):
            bounds = panel.find(
                "./chunks/chunk[@name='Container']/chunks/chunk[@name='Attributes']"
                "/items/item[@name='Bounds']"
            )
            assert bounds is not None
            boxes.append(
                (float(bounds.findtext("Y") or "0"), float(bounds.findtext("H") or "0"))
            )
        boxes.sort()
        for (top, height), (next_top, _) in zip(boxes, boxes[1:]):
            self.assertLessEqual(top + height, next_top)

    def test_panel_is_rejected_on_an_input_port(self) -> None:
        ports = """
[[inputs]]
name = "v"
type = "float"
access = "item"
panel = true

[[outputs]]
name = "log"
type = "str"
access = "item"
"""
        path = self.write_manifest(ports=ports)
        with self.assertRaisesRegex(ManifestError, "only to an output|unexpected field"):
            load_manifest(path)

    def test_log_still_earns_a_panel_without_declaring_one(self) -> None:
        manifest = load_manifest(self.write_manifest())
        log = [port for port in manifest.outputs if port.name == "log"][0]
        self.assertTrue(log.panel)

    def test_canvas_flags_default_to_enabled(self) -> None:
        manifest = load_manifest(self.write_manifest())
        self.assertTrue(manifest.legible_names)
        self.assertTrue(manifest.log_panel)
        self.assertTrue(manifest.input_widgets)
        self.assertTrue(manifest.standard_output)


if __name__ == "__main__":
    unittest.main()

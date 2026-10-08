from __future__ import annotations

import base64
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from ghravioli.archive import build_archive
from ghravioli.constants import PYTHON3_SCRIPT_COMPONENT_ID, VERIFIED_CONVERTERS
from ghravioli.identity import SequenceIdentityProvider
from ghravioli.manifest import load_manifest
from ghravioli.model import ComponentPlacement


class ArchiveTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        source = "# UTF-8: café / 東京\nresult = values\nlog = 'ready'\n"
        (self.root / "component.py").write_text(source, encoding="utf-8")
        (self.root / "component.toml").write_text(
            textwrap.dedent(
                """
                kind = "component"
                schema_version = 1
                target = "rhino8-python3"
                target_python = "3.9"
                id = "archive-example"
                name = "Archive & <Example>"
                source = "component.py"
                description = "Quotes, ampersands & angle brackets <round-trip>."

                [[inputs]]
                name = "values"
                type = "generic"
                access = "list"
                optional = true

                [[inputs]]
                name = "factor"
                type = "float"
                access = "item"
                optional = false

                [[outputs]]
                name = "points"
                type = "point"
                access = "list"

                [[outputs]]
                name = "log"
                type = "str"
                access = "item"
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        self.manifest = load_manifest(self.root / "component.toml")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def build(self, *, x: float = 200.0, y: float = 200.0) -> bytes:
        return build_archive(
            (ComponentPlacement(self.manifest, x=x, y=y),),
            document_name="Archive Test",
            identities=SequenceIdentityProvider(),
        )

    @staticmethod
    def parse(archive: bytes) -> ET.Element:
        return ET.fromstring(archive)

    @staticmethod
    def script_objects(root: ET.Element) -> list[ET.Element]:
        """Return only the Python component objects in a generated archive."""

        return [
            chunk
            for chunk in root.findall(
                ".//chunk[@name='DefinitionObjects']/chunks/chunk[@name='Object']"
            )
            if (chunk.findtext("./items/item[@name='GUID']") or "").lower()
            == PYTHON3_SCRIPT_COMPONENT_ID
        ]

    @staticmethod
    def item_text(element: ET.Element, name: str) -> str:
        item = element.find(f"./items/item[@name='{name}']")
        if item is None or item.text is None:
            raise AssertionError(f"missing item {name!r}")
        return item.text

    def test_emits_clipboard_hierarchy_and_python_component(self) -> None:
        root = self.parse(self.build())

        self.assertEqual(root.tag, "Archive")
        self.assertEqual(root.attrib["name"], "Root")
        self.assertIsNotNone(root.find("./items/item[@name='ArchiveVersion']"))
        clipboard = root.find("./chunks/chunk[@name='Clipboard']")
        self.assertIsNotNone(clipboard)
        definition_objects = root.find(
            "./chunks/chunk[@name='Clipboard']/chunks/chunk[@name='DefinitionObjects']"
        )
        self.assertIsNotNone(definition_objects)
        assert definition_objects is not None
        objects = definition_objects.findall("./chunks/chunk[@name='Object']")
        self.assertEqual(self.item_text(definition_objects, "ObjectCount"), str(len(objects)))
        # One script component plus the log panel this component earns by default.
        self.assertEqual(len(objects), 2)
        self.assertEqual(
            self.item_text(self.script_objects(root)[0], "GUID"),
            PYTHON3_SCRIPT_COMPONENT_ID,
        )

    def test_embeds_exact_utf8_source_and_escapes_metadata(self) -> None:
        root = self.parse(self.build())
        component = root.find(".//chunk[@name='Object']/chunks/chunk[@name='Container']")
        assert component is not None
        self.assertEqual(self.item_text(component, "NickName"), "Archive & <Example>")
        self.assertEqual(
            self.item_text(component, "Description"),
            "Quotes, ampersands & angle brackets <round-trip>.",
        )
        encoded = root.find(".//chunk[@name='Script']/items/item[@name='Text']")
        assert encoded is not None and encoded.text is not None
        self.assertEqual(base64.b64decode(encoded.text).decode("utf-8"), self.manifest.source_text)

    def test_prepends_standard_out_and_keeps_log_separate(self) -> None:
        root = self.parse(self.build())
        parameter_data = root.find(".//chunk[@name='ParameterData']")
        assert parameter_data is not None
        self.assertEqual(self.item_text(parameter_data, "InputCount"), "2")
        self.assertEqual(self.item_text(parameter_data, "OutputCount"), "3")
        output_names = [
            self.item_text(chunk, "Name")
            for chunk in parameter_data.findall("./chunks/chunk[@name='OutputParam']")
        ]
        self.assertEqual(output_names, ["out", "points", "log"])

    def test_emits_access_optionality_and_only_verified_converters(self) -> None:
        root = self.parse(self.build())
        parameter_data = root.find(".//chunk[@name='ParameterData']")
        assert parameter_data is not None
        inputs = parameter_data.findall("./chunks/chunk[@name='InputParam']")
        outputs = parameter_data.findall("./chunks/chunk[@name='OutputParam']")

        self.assertEqual(self.item_text(inputs[0], "ScriptParamAccess"), "1")
        self.assertEqual(self.item_text(inputs[0], "Optional"), "true")
        self.assertEqual(self.item_text(inputs[0], "ShowTypeHints"), "false")
        self.assertIsNone(inputs[0].find("./chunks/chunk[@name='ConverterData']"))

        self.assertEqual(self.item_text(inputs[1], "ScriptParamAccess"), "0")
        self.assertEqual(self.item_text(inputs[1], "Optional"), "false")
        self.assertEqual(
            self.item_text(inputs[1], "TypeHintID"),
            VERIFIED_CONVERTERS["float"].type_hint_id,
        )
        self.assertIsNotNone(inputs[1].find("./chunks/chunk[@name='ConverterData']"))

        self.assertEqual(self.item_text(outputs[1], "ScriptParamAccess"), "1")
        self.assertEqual(
            self.item_text(outputs[1], "TypeHintID"),
            VERIFIED_CONVERTERS["point"].type_hint_id,
        )
        self.assertEqual(self.item_text(outputs[2], "ScriptParamAccess"), "0")
        self.assertEqual(
            self.item_text(outputs[2], "TypeHintID"),
            VERIFIED_CONVERTERS["str"].type_hint_id,
        )

    def test_generates_unique_instance_ids_and_only_resolvable_wiring(self) -> None:
        root = self.parse(self.build())
        ids = [
            item.text
            for item in root.findall(".//item[@name='InstanceGuid']")
            if item.text is not None
        ]
        self.assertGreater(len(ids), 1)
        self.assertEqual(len(ids), len(set(ids)))

        sources = [item.text for item in root.findall(".//item[@name='Source']")]
        self.assertTrue(sources)
        # A wire may only ever reference an object this archive also carries.
        self.assertTrue(set(sources).issubset(set(ids)))

    def test_sequence_identity_provider_makes_output_byte_stable(self) -> None:
        placement = (ComponentPlacement(self.manifest, x=10.0, y=20.0),)
        first = build_archive(
            placement,
            document_name="Deterministic",
            identities=SequenceIdentityProvider(),
        )
        second = build_archive(
            placement,
            document_name="Deterministic",
            identities=SequenceIdentityProvider(),
        )

        self.assertEqual(first, second)

    def test_positions_multiple_components_at_their_declared_origins(self) -> None:
        archive = build_archive(
            (
                ComponentPlacement(self.manifest, x=100.0, y=200.0),
                ComponentPlacement(self.manifest, x=500.0, y=300.0),
            ),
            document_name="Placed Components",
            identities=SequenceIdentityProvider(),
        )
        root = self.parse(archive)
        objects = self.script_objects(root)
        self.assertEqual(len(objects), 2)
        bounds = [obj.find(".//chunk[@name='Attributes']/items/item[@name='Bounds']") for obj in objects]
        self.assertEqual([(item.findtext("X"), item.findtext("Y")) for item in bounds], [("100", "200"), ("500", "300")])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import base64
import copy
import hashlib
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from ghravioli.build import build_file
from ghravioli.inspect import (
    InspectError,
    archive_sources,
    inspect_archive,
    inspect_archive_bytes,
    inspect_manifest,
)


class InspectTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source_text = "# café / 東京\nresult = value\nlog = 'ready'\n"
        (self.root / "component.py").write_text(
            self.source_text,
            encoding="utf-8",
            newline="",
        )
        self.manifest = self.root / "component.toml"
        self.manifest.write_text(
            textwrap.dedent(
                """
                kind = "component"
                schema_version = 1
                target = "rhino8-python3"
                target_python = "3.9"
                id = "inspect-example"
                name = "Inspect Example"
                source = "component.py"

                [[inputs]]
                name = "value"
                type = "generic"
                access = "item"
                optional = true

                [[outputs]]
                name = "result"
                type = "generic"
                access = "item"

                [[outputs]]
                name = "log"
                type = "str"
                access = "item"
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        self.archive = self.root / "component.ghclip"
        build_file(self.manifest, self.archive)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def archive_root(self) -> ET.Element:
        return ET.fromstring(self.archive.read_bytes())

    def write_root(self, root: ET.Element) -> None:
        self.archive.write_bytes(ET.tostring(root, encoding="utf-8"))

    def test_summaries_use_portable_paths_and_source_hashes(self) -> None:
        manifest = inspect_manifest(self.manifest)
        archive = inspect_archive(self.archive)

        self.assertEqual(manifest["source"], "component.py")
        self.assertNotIn(str(self.root), str(manifest))
        self.assertEqual(archive["path"], "component.ghclip")
        self.assertNotIn(str(self.root), str(archive))
        self.assertNotIn("source", archive["components"][0])
        self.assertEqual(
            archive["components"][0]["source_sha256"],
            hashlib.sha256(self.source_text.encode("utf-8")).hexdigest(),
        )

    def test_archive_sources_returns_reviewable_utf8_source(self) -> None:
        sources = archive_sources(self.archive)

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["name"], "Inspect Example")
        self.assertEqual(sources[0]["source"], self.source_text)
        self.assertEqual(
            sources[0]["sha256"],
            hashlib.sha256(self.source_text.encode("utf-8")).hexdigest(),
        )

    def test_rejects_missing_and_non_integer_object_count(self) -> None:
        root = self.archive_root()
        count = root.find(".//chunk[@name='DefinitionObjects']/items/item[@name='ObjectCount']")
        assert count is not None
        count.text = "many"
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "ObjectCount.*integer"):
            inspect_archive(self.archive)

        root = self.archive_root()
        count = root.find(".//chunk[@name='DefinitionObjects']/items/item[@name='ObjectCount']")
        assert count is not None
        parent = root.find(".//chunk[@name='DefinitionObjects']/items")
        assert parent is not None
        parent.remove(count)
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "missing ObjectCount"):
            inspect_archive(self.archive)

    def test_rejects_invalid_counts_component_guid_and_parameter_counts(self) -> None:
        root = self.archive_root()
        root.find("./items").set("count", "99")  # type: ignore[union-attr]
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "declared count"):
            inspect_archive(self.archive)

        build_file(self.manifest, self.archive)
        root = self.archive_root()
        guid = root.find(".//chunk[@name='Object']/items/item[@name='GUID']")
        assert guid is not None
        guid.text = "00000000-0000-0000-0000-000000000000"
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "component GUID"):
            inspect_archive(self.archive)

        build_file(self.manifest, self.archive)
        root = self.archive_root()
        count = root.find(".//chunk[@name='ParameterData']/items/item[@name='InputCount']")
        assert count is not None
        count.text = "7"
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "InputCount"):
            inspect_archive(self.archive)

    def test_requires_unique_canonical_port_scalar_fields(self) -> None:
        mutations = (
            ("duplicate access", "InputParam", "ScriptParamAccess", None),
            ("invalid access", "InputParam", "ScriptParamAccess", "7"),
            ("invalid optional", "InputParam", "Optional", "True"),
            ("optional output", "OutputParam", "Optional", "true"),
        )

        for label, chunk_name, item_name, replacement in mutations:
            with self.subTest(label=label):
                build_file(self.manifest, self.archive)
                root = self.archive_root()
                chunks = root.findall(f".//chunk[@name='{chunk_name}']")
                target = chunks[0] if chunk_name == "InputParam" else chunks[1]
                item = target.find(f"./items/item[@name='{item_name}']")
                items = target.find("./items")
                assert item is not None and items is not None
                if replacement is None:
                    items.append(copy.deepcopy(item))
                    items.set("count", str(len(items)))
                else:
                    item.text = replacement
                self.write_root(root)
                with self.assertRaisesRegex(InspectError, "ScriptParamAccess|Optional|canonical"):
                    inspect_archive(self.archive)

    def test_enforces_generated_port_names_log_and_converter_contract(self) -> None:
        mutations = {
            "duplicate name": ("InputParam", 0, "Name", "result"),
            "reserved out": ("InputParam", 0, "Name", "out"),
            "missing log": ("OutputParam", 2, "Name", "messages"),
            "list log": ("OutputParam", 2, "ScriptParamAccess", "1"),
            "wrong log hint": (
                "OutputParam",
                2,
                "TypeHintID",
                "9d51e32e-c038-4352-9554-f4137ca91b9a",
            ),
        }

        for label, (chunk_name, index, item_name, value) in mutations.items():
            with self.subTest(label=label):
                build_file(self.manifest, self.archive)
                root = self.archive_root()
                chunk = root.findall(f".//chunk[@name='{chunk_name}']")[index]
                item = chunk.find(f"./items/item[@name='{item_name}']")
                assert item is not None
                item.text = value
                self.write_root(root)
                with self.assertRaisesRegex(InspectError, "duplicate|reserved|log|converter|TypeHint"):
                    inspect_archive(self.archive)

    def test_requires_matching_converter_metadata_and_unique_parameter_ids(self) -> None:
        build_file(self.manifest, self.archive)
        root = self.archive_root()
        log_output = root.findall(".//chunk[@name='OutputParam']")[2]
        assembly = log_output.find("./chunks/chunk[@name='ConverterData']/items/item[@name='AssemblyName']")
        assert assembly is not None
        assembly.text = "Unexpected.Assembly"
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "converter|AssemblyName"):
            inspect_archive(self.archive)

        build_file(self.manifest, self.archive)
        root = self.archive_root()
        parameters = root.findall(".//chunk[@name='InputParam']") + root.findall(".//chunk[@name='OutputParam']")
        first_id = parameters[0].find("./items/item[@name='InstanceGuid']")
        second_id = parameters[1].find("./items/item[@name='InstanceGuid']")
        assert first_id is not None and second_id is not None
        second_id.text = first_id.text
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "duplicate.*InstanceGuid|InstanceGuid.*duplicate"):
            inspect_archive(self.archive)

    def test_rejects_source_connections_outside_generated_subset(self) -> None:
        """Wiring is allowed, but only in canonical position and only if it resolves."""

        # A Source appended outside its generated position is not canonical.
        root = self.archive_root()
        input_param = root.find(".//chunk[@name='InputParam']")
        items = input_param.find("./items") if input_param is not None else None
        source_count = input_param.find("./items/item[@name='SourceCount']") if input_param is not None else None
        assert items is not None and source_count is not None
        source_count.text = "1"
        source = ET.Element(
            "item",
            {"name": "Source", "type_name": "gh_guid", "type_code": "9", "index": "0"},
        )
        source.text = "00000000-0000-0000-0000-000000000000"
        items.append(source)
        items.set("count", str(len(items)))
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "canonical generated order"):
            inspect_archive(self.archive)

        # A canonically placed Source that references nothing is a dangling wire.
        build_file(self.manifest, self.archive)
        root = self.archive_root()
        dangling = root.find(".//item[@name='Source']")
        assert dangling is not None
        dangling.text = "00000000-0000-0000-0000-000000000000"
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "source must reference"):
            inspect_archive(self.archive)

    def test_rejects_non_utf8_source_doctype_and_oversized_archive(self) -> None:
        root = self.archive_root()
        encoded = root.find(".//chunk[@name='Script']/items/item[@name='Text']")
        assert encoded is not None
        encoded.text = base64.b64encode(b"\xff").decode("ascii")
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "UTF-8"):
            inspect_archive(self.archive)

        build_file(self.manifest, self.archive)
        content = self.archive.read_bytes().replace(
            b"<Archive",
            b"<!DOCTYPE Archive [<!ENTITY x 'unsafe'>]><Archive",
            1,
        )
        self.archive.write_bytes(content)
        with self.assertRaisesRegex(InspectError, "DOCTYPE"):
            inspect_archive(self.archive)

        self.archive.write_bytes(b" " * (10 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(InspectError, "archive exceeds"):
            inspect_archive(self.archive)

    def test_rejects_non_utf8_archive_encodings_before_xml_parsing(self) -> None:
        xml_text = self.archive.read_text(encoding="utf-8").replace(
            '<?xml version="1.0" encoding="utf-8" standalone="yes"?>',
            '<?xml version="1.0" encoding="UTF-16"?>',
            1,
        )
        xml_text = xml_text.replace(
            "<Archive",
            '<!DOCTYPE Archive [<!ENTITY payload "expanded">]><Archive',
            1,
        )

        for encoding in ("utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"):
            with self.subTest(encoding=encoding):
                self.archive.write_bytes(xml_text.encode(encoding))
                with self.assertRaisesRegex(InspectError, "archive XML must be UTF-8"):
                    inspect_archive(self.archive)

        build_file(self.manifest, self.archive)
        self.archive.write_bytes(b"\xef\xbb\xbf" + self.archive.read_bytes())
        with self.assertRaisesRegex(InspectError, "UTF-8 BOM"):
            inspect_archive(self.archive)

        build_file(self.manifest, self.archive)
        claimed_latin_1 = self.archive.read_bytes().replace(
            b'encoding="utf-8"',
            b'encoding="iso-8859-1"',
            1,
        )
        self.archive.write_bytes(claimed_latin_1)
        with self.assertRaisesRegex(InspectError, "declaration.*UTF-8|UTF-8.*declaration"):
            inspect_archive(self.archive)

    def test_embedded_source_uses_manifest_size_null_and_compilation_rules(self) -> None:
        invalid_sources = {
            "null": b"log = 'bad'\x00\n",
            "compile": b"return\n",
            "size": b"#" * (1024 * 1024 + 1),
        }

        for label, source_bytes in invalid_sources.items():
            with self.subTest(label=label):
                build_file(self.manifest, self.archive)
                root = self.archive_root()
                encoded = root.find(".//chunk[@name='Script']/items/item[@name='Text']")
                assert encoded is not None
                encoded.text = base64.b64encode(source_bytes).decode("ascii")
                self.write_root(root)
                expected = "null byte" if label == "null" else "invalid Python 3.9|1048576"
                with self.assertRaisesRegex(InspectError, expected):
                    inspect_archive(self.archive)

    def test_rejects_duplicate_critical_items_and_chunks(self) -> None:
        root = self.archive_root()
        script = root.find(".//chunk[@name='Script']")
        assert script is not None
        script_items = script.find("./items")
        text = script.find("./items/item[@name='Text']")
        assert script_items is not None and text is not None
        script_items.append(copy.deepcopy(text))
        script_items.set("count", str(len(script_items)))
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "Text.*exactly one|exactly one.*Text"):
            inspect_archive(self.archive)

        build_file(self.manifest, self.archive)
        root = self.archive_root()
        container = root.find(".//chunk[@name='Container']")
        assert container is not None
        container_chunks = container.find("./chunks")
        script = container.find("./chunks/chunk[@name='Script']")
        assert container_chunks is not None and script is not None
        container_chunks.append(copy.deepcopy(script))
        container_chunks.set("count", str(len(container_chunks)))
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "Script.*exactly one|exactly one.*Script"):
            inspect_archive(self.archive)

        build_file(self.manifest, self.archive)
        root = self.archive_root()
        object_chunk = root.find(".//chunk[@name='Object']")
        assert object_chunk is not None
        object_chunks = object_chunk.find("./chunks")
        container = object_chunk.find("./chunks/chunk[@name='Container']")
        assert object_chunks is not None and container is not None
        object_chunks.append(copy.deepcopy(container))
        object_chunks.set("count", str(len(object_chunks)))
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "Container.*exactly one|exactly one.*Container"):
            inspect_archive(self.archive)

    def test_rejects_every_structure_outside_the_generated_archive_schema(self) -> None:
        mutations = (
            (
                "unexpected item",
                ".//chunk[@name='Container']/items",
                ET.Element(
                    "item",
                    {
                        "name": "UnexpectedExecutionMetadata",
                        "type_name": "gh_string",
                        "type_code": "10",
                    },
                ),
            ),
            (
                "known item in wrong chunk",
                ".//chunk[@name='Container']/items",
                ET.Element(
                    "item",
                    {"name": "Author", "type_name": "gh_string", "type_code": "10"},
                ),
            ),
            (
                "unexpected chunk",
                ".//chunk[@name='Container']/chunks",
                ET.Element("chunk", {"name": "ExecutionMetadata"}),
            ),
            (
                "unexpected tag",
                ".//chunk[@name='Container']",
                ET.Element("execution-metadata"),
            ),
        )

        for label, parent_query, injected in mutations:
            with self.subTest(label=label):
                build_file(self.manifest, self.archive)
                root = self.archive_root()
                parent = root.find(parent_query)
                assert parent is not None
                parent.append(injected)
                if parent.tag in {"items", "chunks"}:
                    parent.set("count", str(len(parent)))
                self.write_root(root)

                with self.assertRaisesRegex(InspectError, "canonical|unexpected|generated"):
                    inspect_archive(self.archive)

    def test_rejects_noncanonical_attributes_item_types_and_fixed_metadata(self) -> None:
        mutations = (
            ("root attribute", ".", "attribute", "unexpected", "true"),
            (
                "item attribute",
                ".//chunk[@name='Container']/items/item[@name='Description']",
                "attribute",
                "unexpected",
                "true",
            ),
            (
                "item type",
                ".//chunk[@name='Container']/items/item[@name='Description']",
                "attribute",
                "type_name",
                "gh_int32",
            ),
            (
                "fixed value",
                ".//chunk[@name='Container']/items/item[@name='MarshInputs']",
                "text",
                "",
                "false",
            ),
        )

        for label, query, mutation_kind, key, value in mutations:
            with self.subTest(label=label):
                build_file(self.manifest, self.archive)
                root = self.archive_root()
                target = root if query == "." else root.find(query)
                assert target is not None
                if mutation_kind == "attribute":
                    target.set(key, value)
                else:
                    target.text = value
                self.write_root(root)

                with self.assertRaisesRegex(InspectError, "canonical|attribute|type|MarshInputs"):
                    inspect_archive(self.archive)

    def test_rejects_unsafe_text_in_all_display_metadata(self) -> None:
        root = self.archive_root()
        description = root.find(
            ".//chunk[@name='OutputParam']/items/item[@name='Description']"
        )
        assert description is not None
        description.text = "spoof\u202erecord"
        self.write_root(root)

        with self.assertRaisesRegex(InspectError, "Description.*unsafe|Description.*format"):
            inspect_archive(self.archive)

    def test_rejects_invalid_dynamic_metadata_and_cross_field_mismatches(self) -> None:
        mutations = (
            (
                "document UUID",
                ".//chunk[@name='DocumentHeader']/items/item[@name='DocumentID']",
                "not-a-uuid",
                "DocumentID.*UUID|UUID.*DocumentID",
            ),
            (
                "canonical document UUID",
                ".//chunk[@name='DocumentHeader']/items/item[@name='DocumentID']",
                "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA",
                "DocumentID.*canonical UUID|canonical UUID.*DocumentID",
            ),
            (
                "canonical object count",
                ".//chunk[@name='DefinitionObjects']/items/item[@name='ObjectCount']",
                "01",
                "ObjectCount.*canonical integer|canonical integer.*ObjectCount",
            ),
            (
                "attribute coordinate",
                ".//chunk[@name='Container']/chunk-does-not-exist",
                "unused",
                "Attributes.*numeric|Bounds.*numeric|coordinate",
            ),
            (
                "fixed component width",
                ".//chunk[@name='Container']/chunk-does-not-exist",
                "unused",
                "Bounds W.*canonical|component width",
            ),
            (
                "derived component height",
                ".//chunk[@name='Container']/chunk-does-not-exist",
                "unused",
                "Bounds H.*canonical|component height",
            ),
            (
                "attribute pivot",
                ".//chunk[@name='Container']/chunk-does-not-exist",
                "unused",
                "Pivot.*Bounds|Bounds.*Pivot",
            ),
            (
                "component tooltip",
                ".//chunk[@name='Container']/items/item[@name='Tooltip']",
                "does not match",
                "Description.*Tooltip|Tooltip.*Description",
            ),
            (
                "script title",
                ".//chunk[@name='Script']/items/item[@name='Title']",
                "does not match",
                "Title.*NickName|NickName.*Title",
            ),
            (
                "port tooltip",
                ".//chunk[@name='InputParam']/items/item[@name='ToolTip']",
                "does not match",
                "Description.*ToolTip|ToolTip.*Description",
            ),
        )

        for label, query, value, expected in mutations:
            with self.subTest(label=label):
                build_file(self.manifest, self.archive)
                root = self.archive_root()
                if label in {
                    "attribute coordinate",
                    "fixed component width",
                    "derived component height",
                    "attribute pivot",
                }:
                    if label == "attribute pivot":
                        target = root.find(
                            ".//chunk[@name='Container']/chunks/chunk[@name='Attributes']"
                            "/items/item[@name='Pivot']/X"
                        )
                    else:
                        coordinate = {
                            "attribute coordinate": "X",
                            "fixed component width": "W",
                            "derived component height": "H",
                        }[label]
                        target = root.find(
                            ".//chunk[@name='Container']/chunks/chunk[@name='Attributes']"
                            f"/items/item[@name='Bounds']/{coordinate}"
                        )
                else:
                    target = root.find(query)
                assert target is not None
                if label == "attribute coordinate":
                    target.text = "not-a-number"
                elif label == "fixed component width":
                    target.text = "999"
                elif label == "derived component height":
                    target.text = "999"
                elif label == "attribute pivot":
                    target.text = "999"
                else:
                    target.text = value
                self.write_root(root)

                with self.assertRaisesRegex(InspectError, expected):
                    inspect_archive(self.archive)

    def test_rejects_non_whitespace_text_between_structural_elements(self) -> None:
        queries = (
            ".//chunk[@name='Container']",
            ".//chunk[@name='Container']/chunks/chunk[@name='Attributes']"
            "/items/item[@name='Bounds']",
        )

        for query in queries:
            with self.subTest(query=query):
                build_file(self.manifest, self.archive)
                root = self.archive_root()
                target = root.find(query)
                assert target is not None
                target.text = "unexpected structural text"
                self.write_root(root)

                with self.assertRaisesRegex(InspectError, "structural text|canonical generated"):
                    inspect_archive(self.archive)

    def test_rejects_noncanonical_declared_wrapper_count(self) -> None:
        root = self.archive_root()
        items = root.find("./items")
        assert items is not None
        items.set("count", "01")
        self.write_root(root)

        with self.assertRaisesRegex(InspectError, "declared count.*canonical|canonical.*count"):
            inspect_archive(self.archive)

    def test_enforces_manifest_contract_limits_in_untrusted_archives(self) -> None:
        cases = (
            ("invalid port name", "port-name", "valid Python identifier"),
            ("empty document name", "document-name", "non-empty"),
            ("empty component name", "component-name", "non-empty"),
            ("long component description", "description", "at most 4000"),
            ("too many components", "component-count", "at most 256 components"),
            ("too many inputs", "input-count", "at most 128"),
        )

        for label, mutation, expected in cases:
            with self.subTest(label=label):
                build_file(self.manifest, self.archive)
                root = self.archive_root()
                if mutation == "port-name":
                    target = root.find(
                        ".//chunk[@name='InputParam']/items/item[@name='Name']"
                    )
                    assert target is not None
                    target.text = "not-valid"
                elif mutation == "document-name":
                    target = root.find(
                        ".//chunk[@name='DefinitionProperties']/items/item[@name='Name']"
                    )
                    assert target is not None
                    target.text = ""
                elif mutation == "component-name":
                    nickname = root.find(
                        ".//chunk[@name='Container']/items/item[@name='NickName']"
                    )
                    title = root.find(".//chunk[@name='Script']/items/item[@name='Title']")
                    assert nickname is not None and title is not None
                    nickname.text = ""
                    title.text = ""
                elif mutation == "description":
                    description = root.find(
                        ".//chunk[@name='Container']/items/item[@name='Description']"
                    )
                    tooltip = root.find(
                        ".//chunk[@name='Container']/items/item[@name='Tooltip']"
                    )
                    assert description is not None and tooltip is not None
                    description.text = "x" * 4001
                    tooltip.text = "x" * 4001
                elif mutation == "component-count":
                    definition = root.find(".//chunk[@name='DefinitionObjects']")
                    target = definition.find(
                        "./items/item[@name='ObjectCount']"
                    ) if definition is not None else None
                    objects = definition.find("./chunks") if definition is not None else None
                    original = next(
                        (
                            item
                            for item in definition.findall("./chunks/chunk[@name='Object']")
                            if item.findtext("./items/item[@name='Name']") == "Python 3 Script"
                        ),
                        None,
                    ) if definition is not None else None
                    assert definition is not None and target is not None and objects is not None and original is not None
                    for _index in range(256):
                        duplicate = copy.deepcopy(original)
                        duplicate.set("index", str(len(objects)))
                        objects.append(duplicate)
                    objects.set("count", str(len(objects)))
                    target.text = str(len(objects))
                else:
                    target = root.find(
                        ".//chunk[@name='ParameterData']/items/item[@name='InputCount']"
                    )
                    assert target is not None
                    target.text = "129"
                self.write_root(root)

                with self.assertRaisesRegex(InspectError, expected):
                    inspect_archive(self.archive)

    def test_archive_error_paths_are_terminal_safe(self) -> None:
        unsafe_name = "bad\x1b[31m\n\u202e-name.ghclip"

        with self.assertRaises(InspectError) as caught:
            inspect_archive_bytes(b"not xml", display_path=unsafe_name)

        rendered = str(caught.exception)
        self.assertNotIn("\x1b", rendered)
        self.assertNotIn("\n", rendered)
        self.assertNotIn("\u202e", rendered)
        self.assertIn(r"\u001b", rendered)
        self.assertIn(r"\n", rendered)
        self.assertIn(r"\u202e", rendered)

    def test_rejects_invalid_indexes_instance_ids_language_and_names(self) -> None:
        root = self.archive_root()
        output_ids = root.findall(".//chunk[@name='ParameterData']/items/item[@name='OutputId']")
        self.assertGreaterEqual(len(output_ids), 2)
        output_ids[1].set("index", "0")
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "OutputId.*index|index.*OutputId"):
            inspect_archive(self.archive)

        build_file(self.manifest, self.archive)
        root = self.archive_root()
        instance = root.find(".//chunk[@name='Container']/items/item[@name='InstanceGuid']")
        assert instance is not None
        instance.text = "not-a-uuid"
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "InstanceGuid.*UUID|UUID.*InstanceGuid"):
            inspect_archive(self.archive)

        build_file(self.manifest, self.archive)
        root = self.archive_root()
        language_version = root.find(".//chunk[@name='LanguageSpec']/items/item[@name='Version']")
        assert language_version is not None
        language_version.text = "2.*"
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "language|Python 3"):
            inspect_archive(self.archive)

        build_file(self.manifest, self.archive)
        root = self.archive_root()
        nickname = root.find(".//chunk[@name='Container']/items/item[@name='NickName']")
        assert nickname is not None
        nickname.text = "safe\nforged-record"
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "NickName.*control|control.*NickName"):
            inspect_archive(self.archive)

        build_file(self.manifest, self.archive)
        root = self.archive_root()
        nickname = root.find(".//chunk[@name='Container']/items/item[@name='NickName']")
        assert nickname is not None
        nickname.text = "spoof\u202erecord"
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "NickName.*format|format.*NickName"):
            inspect_archive(self.archive)

    def test_rejects_zero_objects_and_duplicate_component_instance_ids(self) -> None:
        root = self.archive_root()
        definition = root.find(".//chunk[@name='DefinitionObjects']")
        assert definition is not None
        objects = definition.find("./chunks")
        object_count = definition.find("./items/item[@name='ObjectCount']")
        assert objects is not None and object_count is not None
        for child in list(objects):
            objects.remove(child)
        objects.set("count", "0")
        object_count.text = "0"
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "at least one"):
            inspect_archive(self.archive)

        build_file(self.manifest, self.archive)
        root = self.archive_root()
        definition = root.find(".//chunk[@name='DefinitionObjects']")
        assert definition is not None
        objects = definition.find("./chunks")
        object_count = definition.find("./items/item[@name='ObjectCount']")
        existing = definition.findall("./chunks/chunk[@name='Object']")
        assert objects is not None and object_count is not None and existing
        duplicate = copy.deepcopy(existing[0])
        duplicate.set("index", str(len(existing)))
        objects.append(duplicate)
        objects.set("count", str(len(existing) + 1))
        object_count.text = str(len(existing) + 1)
        self.write_root(root)
        with self.assertRaisesRegex(InspectError, "duplicate.*InstanceGuid|InstanceGuid.*duplicate"):
            inspect_archive(self.archive)


if __name__ == "__main__":
    unittest.main()

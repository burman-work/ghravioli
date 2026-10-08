from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from ghravioli.errors import ManifestError
from ghravioli.manifest import load_manifest
from ghravioli.model import ComponentManifest


VALID_MANIFEST = """
kind = "component"
schema_version = 1
target = "rhino8-python3"
target_python = "3.9"
id = "example-scale-points"
name = "Scale Points"
source = "component.py"
description = "Scales points away from the origin."

[[inputs]]
name = "points"
nickname = "P"
description = "Points to scale."
type = "point"
access = "list"
optional = false

[[inputs]]
name = "factor"
type = "float"
access = "item"
optional = true

[[outputs]]
name = "scaled_points"
type = "point"
access = "list"

[[outputs]]
name = "log"
type = "str"
access = "item"
"""


class ManifestTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "component.py"
        self.source.write_text(
            "scaled_points = []\nlog = 'ready'\n",
            encoding="utf-8",
            newline="",
        )
        self.path = self.root / "component.toml"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_manifest(self, body: str = VALID_MANIFEST) -> Path:
        self.path.write_text(textwrap.dedent(body).strip() + "\n", encoding="utf-8")
        return self.path

    def assert_manifest_error(self, body: str, message: str) -> None:
        self.write_manifest(body)
        with self.assertRaisesRegex(ManifestError, message):
            load_manifest(self.path)

    def test_loads_valid_component_relative_to_manifest(self) -> None:
        manifest = load_manifest(self.write_manifest())

        self.assertIsInstance(manifest, ComponentManifest)
        self.assertEqual(manifest.id, "example-scale-points")
        self.assertEqual(manifest.name, "Scale Points")
        self.assertEqual(manifest.source_path, self.source.resolve())
        self.assertEqual(manifest.source_text, "scaled_points = []\nlog = 'ready'\n")
        self.assertEqual(manifest.inputs[0].name, "points")
        self.assertEqual(manifest.inputs[0].nickname, "P")
        self.assertEqual(manifest.inputs[0].access, "list")
        self.assertFalse(manifest.inputs[0].optional)
        self.assertEqual(manifest.inputs[1].type, "float")
        self.assertTrue(manifest.inputs[1].optional)
        self.assertEqual([port.name for port in manifest.outputs], ["scaled_points", "log"])

    def test_accepts_verified_and_unhinted_type_tokens(self) -> None:
        types = [
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
        ]
        inputs = "\n\n".join(
            f'[[inputs]]\nname = "value_{index}"\ntype = "{token}"\naccess = "item"'
            for index, token in enumerate(types)
        )
        body = f"""
        kind = "component"
        schema_version = 1
        target = "rhino8-python3"
        target_python = "3.9"
        id = "all-types"
        name = "All Types"
        source = "component.py"

        {inputs}

        [[outputs]]
        name = "log"
        type = "str"
        access = "item"
        """

        manifest = load_manifest(self.write_manifest(body))

        self.assertEqual([port.type for port in manifest.inputs], types)

    def test_requires_supported_kind_and_schema(self) -> None:
        self.assert_manifest_error(
            VALID_MANIFEST.replace('kind = "component"', 'kind = "other"'),
            "unsupported manifest kind",
        )
        self.assert_manifest_error(
            VALID_MANIFEST.replace("schema_version = 1", "schema_version = 2"),
            "unsupported schema_version",
        )
        self.assert_manifest_error(
            VALID_MANIFEST.replace("schema_version = 1", "schema_version = true"),
            "schema_version.*integer",
        )

    def test_requires_explicit_supported_target(self) -> None:
        self.assert_manifest_error(
            VALID_MANIFEST.replace('target = "rhino8-python3"\n', ""),
            "target",
        )
        self.assert_manifest_error(
            VALID_MANIFEST.replace('target = "rhino8-python3"', 'target = "other"'),
            "target",
        )
        self.assert_manifest_error(
            VALID_MANIFEST.replace('target_python = "3.9"', 'target_python = "3.11"'),
            "target_python",
        )

    def test_requires_valid_component_identity_and_port_names(self) -> None:
        self.assert_manifest_error(
            VALID_MANIFEST.replace('id = "example-scale-points"', 'id = "Bad ID"'),
            "invalid component id",
        )
        self.assert_manifest_error(
            VALID_MANIFEST.replace('name = "points"', 'name = "not-valid"', 1),
            "valid Python identifier",
        )
        self.assert_manifest_error(
            VALID_MANIFEST.replace('name = "points"', 'name = "class"', 1),
            "valid Python identifier",
        )

    def test_rejects_duplicate_or_reserved_ports(self) -> None:
        self.assert_manifest_error(
            VALID_MANIFEST.replace('name = "scaled_points"', 'name = "points"'),
            "duplicate port name",
        )
        self.assert_manifest_error(
            VALID_MANIFEST.replace('name = "scaled_points"', 'name = "out"'),
            "reserved",
        )

    def test_requires_log_string_item_output(self) -> None:
        self.assert_manifest_error(VALID_MANIFEST.replace('name = "log"', 'name = "messages"'), "log")
        self.assert_manifest_error(
            VALID_MANIFEST.replace('name = "log"\ntype = "str"', 'name = "log"\ntype = "generic"'),
            "log.*str",
        )
        self.assert_manifest_error(
            VALID_MANIFEST.replace('name = "log"\ntype = "str"\naccess = "item"', 'name = "log"\ntype = "str"\naccess = "list"'),
            "log.*item",
        )

    def test_rejects_invalid_access_type_and_optional_values(self) -> None:
        self.assert_manifest_error(VALID_MANIFEST.replace('access = "list"', 'access = "tree"', 1), "access")
        self.assert_manifest_error(VALID_MANIFEST.replace('type = "point"', 'type = "dictionary"', 1), "type")
        self.assert_manifest_error(VALID_MANIFEST.replace("optional = false", 'optional = "no"', 1), "optional")
        self.assert_manifest_error(
            VALID_MANIFEST.replace(
                'name = "scaled_points"\ntype = "point"\naccess = "list"',
                'name = "scaled_points"\ntype = "point"\naccess = "list"\noptional = false',
            ),
            "unexpected field.*optional",
        )

    def test_rejects_unknown_component_and_port_fields(self) -> None:
        self.assert_manifest_error(
            VALID_MANIFEST.replace('description = "Scales points away from the origin."', 'descripton = "typo"'),
            "unexpected field.*descripton",
        )
        self.assert_manifest_error(
            VALID_MANIFEST.replace('name = "points"', 'name = "points"\nflatten = true', 1),
            "unexpected field.*flatten",
        )

    def test_rejects_xml_invalid_metadata_and_excessive_sizes(self) -> None:
        self.assert_manifest_error(
            VALID_MANIFEST.replace('name = "Scale Points"', 'name = "Scale\\u0001Points"'),
            "XML 1.0",
        )
        self.assert_manifest_error(
            VALID_MANIFEST.replace('name = "Scale Points"', 'name = "' + ("x" * 201) + '"'),
            "at most 200",
        )

        self.source.write_text("#" * (1024 * 1024 + 1), encoding="utf-8")
        self.assert_manifest_error(VALID_MANIFEST, "source.*1048576")

    def test_rejects_terminal_controls_in_display_metadata(self) -> None:
        self.assert_manifest_error(
            VALID_MANIFEST.replace('name = "Scale Points"', 'name = "Scale\\nPoints"'),
            "terminal control",
        )
        self.assert_manifest_error(
            VALID_MANIFEST.replace('nickname = "P"', 'nickname = "P\\tvalue"'),
            "terminal control",
        )
        self.assert_manifest_error(
            VALID_MANIFEST.replace('name = "Scale Points"', 'name = "Scale\\u202ePoints"'),
            "unsafe terminal formatting",
        )

    def test_validates_source_with_python_39_grammar(self) -> None:
        self.source.write_text("if True print('broken')\n", encoding="utf-8")
        self.assert_manifest_error(VALID_MANIFEST, "invalid Python 3.9 syntax")

        self.source.write_text(
            "match value:\n    case 1:\n        scaled_points = []\nlog = 'ready'\n",
            encoding="utf-8",
        )
        self.assert_manifest_error(VALID_MANIFEST, "Python 3.9")

    def test_rejects_source_that_parses_but_cannot_compile(self) -> None:
        invalid_sources = {
            "return": "return\n",
            "break": "break\n",
            "continue": "continue\n",
            "nonlocal": "nonlocal value\n",
            "duplicate arguments": "def example(value, value):\n    pass\n",
        }

        for label, source in invalid_sources.items():
            with self.subTest(label=label):
                self.source.write_text(source, encoding="utf-8")
                self.assert_manifest_error(VALID_MANIFEST, "invalid Python 3.9 syntax")

    def test_rejects_missing_absolute_and_escaping_source_paths(self) -> None:
        self.source.unlink()
        self.assert_manifest_error(VALID_MANIFEST, "does not exist")

        self.source.write_text("log = 'ready'\n", encoding="utf-8")
        absolute_source = self.source.resolve().as_posix()
        self.assert_manifest_error(
            VALID_MANIFEST.replace(
                'source = "component.py"',
                f'source = "{absolute_source}"',
            ),
            "relative path",
        )

        outside = self.root.parent / "outside_component.py"
        outside.write_text("log = 'outside'\n", encoding="utf-8")
        try:
            self.assert_manifest_error(
                VALID_MANIFEST.replace('source = "component.py"', 'source = "../outside_component.py"'),
                "inside the manifest directory",
            )
        finally:
            outside.unlink()

    def test_validates_source_paths_portably_before_using_them(self) -> None:
        unsafe_values = {
            "newline": 'source = "component\\nforged.py"',
            "bidi": 'source = "component\\u202efile.py"',
        }
        for label, declaration in unsafe_values.items():
            with self.subTest(label=label):
                self.assert_manifest_error(
                    VALID_MANIFEST.replace('source = "component.py"', declaration),
                    "source.*unsafe|source.*terminal|source.*format",
                )

        non_relative_values = (
            r"source = 'C:\temp\component.py'",
            r"source = '\\server\share\component.py'",
        )
        for declaration in non_relative_values:
            with self.subTest(declaration=declaration):
                self.assert_manifest_error(
                    VALID_MANIFEST.replace('source = "component.py"', declaration),
                    "relative path",
                )

        self.assert_manifest_error(
            VALID_MANIFEST.replace(
                'source = "component.py"',
                'source = "' + ("a" * 1001) + '"',
            ),
            "at most 1000",
        )

        nested = self.root / "nested"
        nested.mkdir()
        nested_source = nested / "component.py"
        nested_source.write_text("log = 'portable'\n", encoding="utf-8")
        portable = load_manifest(
            self.write_manifest(
                VALID_MANIFEST.replace(
                    'source = "component.py"',
                    r"source = 'nested\component.py'",
                )
            )
        )
        self.assertEqual(portable.source_path, nested_source.resolve())

    def test_rejects_windows_reserved_and_invalid_relative_path_segments(self) -> None:
        invalid_paths = (
            "CON.py",
            "dir/NUL.toml",
            "aux",
            "COM9.txt",
            "LPT1.py",
            "COM¹.txt",
            "LPT².py",
            "CON .txt",
            "CONIN$",
            "CONOUT$.txt",
            "bad<name.py",
            "bad>name.py",
            'bad"name.py',
            "bad:name.py",
            "bad|name.py",
            "bad?name.py",
            "bad*name.py",
            "trailing./component.py",
            "trailing /component.py",
        )

        for unsafe_path in invalid_paths:
            with self.subTest(path=unsafe_path):
                declaration = f"source = {unsafe_path!r}"
                self.assert_manifest_error(
                    VALID_MANIFEST.replace('source = "component.py"', declaration),
                    "portable|Windows|reserved|invalid|end with",
                )

    def test_accepts_portable_unicode_relative_path_segments(self) -> None:
        unicode_directory = self.root / "東京"
        unicode_directory.mkdir()
        unicode_source = unicode_directory / "café.py"
        unicode_source.write_text("log = 'portable Unicode'\n", encoding="utf-8")

        manifest = load_manifest(
            self.write_manifest(
                VALID_MANIFEST.replace(
                    'source = "component.py"',
                    'source = "東京/café.py"',
                )
            )
        )

        self.assertEqual(manifest.source_path, unicode_source.resolve())

    def test_manifest_errors_escape_untrusted_keys_and_path_labels(self) -> None:
        self.path.write_text(
            textwrap.dedent(VALID_MANIFEST).strip()
            + '\n"forged\\u202e" = true\n',
            encoding="utf-8",
        )

        with self.assertRaises(ManifestError) as caught:
            load_manifest(self.path)

        rendered_key_error = str(caught.exception)
        self.assertNotIn("\u202e", rendered_key_error)
        self.assertIn(r"\u202e", rendered_key_error)

        unsafe_path = self.root / "manifest\x1b[31m\n.toml"
        rendered = str(
            ManifestError(
                unsafe_path,
                "unsafe\nmessage",
                field="forged\u202e",
            )
        )

        self.assertNotIn("\x1b", rendered)
        self.assertNotIn("\n", rendered)
        self.assertNotIn("\u202e", rendered)
        self.assertIn(r"\u001b", rendered)
        self.assertIn(r"\n", rendered)
        self.assertIn(r"\u202e", rendered)

    def test_rejects_null_bytes_in_source(self) -> None:
        self.source.write_bytes(b"log = 'bad'\x00\n")
        self.assert_manifest_error(VALID_MANIFEST, "null byte")


if __name__ == "__main__":
    unittest.main()

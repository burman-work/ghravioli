from __future__ import annotations

import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from ghravioli import constants
from ghravioli.build import build_bytes, build_file, default_output_path
from ghravioli.errors import BuildError, ManifestError
from ghravioli.identity import SequenceIdentityProvider
from ghravioli.inspect import inspect_archive
from ghravioli.manifest import load_manifest
from ghravioli.model import GraphManifest


COMPONENT_TEMPLATE = """
kind = "component"
schema_version = 1
target = "rhino8-python3"
target_python = "3.9"
id = "{component_id}"
name = "{name}"
source = "component.py"

[[outputs]]
name = "log"
type = "str"
access = "item"
"""


class BuildTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.component_a = self.create_component("a", "component-a", "Component A")
        self.component_b = self.create_component("b", "component-b", "Component B")
        self.graph_path = self.root / "graph.toml"
        self.graph_path.write_text(
            textwrap.dedent(
                """
                kind = "graph"
                schema_version = 1
                id = "example-graph"
                name = "Example Graph"

                [[components]]
                manifest = "a/component.toml"
                x = 100.0
                y = 200.0

                [[components]]
                manifest = "b/component.toml"
                x = 500.0
                y = 300.0
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def create_component(self, folder: str, component_id: str, name: str) -> Path:
        component_dir = self.root / folder
        component_dir.mkdir()
        (component_dir / "component.py").write_text("log = 'ready'\n", encoding="utf-8")
        manifest_path = component_dir / "component.toml"
        manifest_path.write_text(
            textwrap.dedent(COMPONENT_TEMPLATE).format(component_id=component_id, name=name).strip()
            + "\n",
            encoding="utf-8",
        )
        return manifest_path

    def test_loads_positioned_graph_components(self) -> None:
        graph = load_manifest(self.graph_path)

        self.assertIsInstance(graph, GraphManifest)
        assert isinstance(graph, GraphManifest)
        self.assertEqual(graph.id, "example-graph")
        self.assertEqual([placement.component.id for placement in graph.components], ["component-a", "component-b"])
        self.assertEqual([(placement.x, placement.y) for placement in graph.components], [(100.0, 200.0), (500.0, 300.0)])

    def test_rejects_invalid_graph_references_and_wiring(self) -> None:
        outside_dir = self.root.parent / "outside-graph-component"
        outside_dir.mkdir()
        outside_manifest = outside_dir / "component.toml"
        (outside_dir / "component.py").write_text("log = 'outside'\n", encoding="utf-8")
        outside_manifest.write_text(
            textwrap.dedent(COMPONENT_TEMPLATE).format(component_id="outside", name="Outside").strip() + "\n",
            encoding="utf-8",
        )
        try:
            escaping = self.graph_path.read_text(encoding="utf-8").replace(
                'manifest = "a/component.toml"',
                'manifest = "../outside-graph-component/component.toml"',
            )
            self.graph_path.write_text(escaping, encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "inside the graph directory"):
                load_manifest(self.graph_path)
        finally:
            outside_manifest.unlink()
            (outside_dir / "component.py").unlink()
            outside_dir.rmdir()

        absolute_component = self.component_a.resolve().as_posix()
        self.graph_path.write_text(
            self.graph_path.read_text(encoding="utf-8").replace(
                'manifest = "../outside-graph-component/component.toml"',
                f'manifest = "{absolute_component}"',
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ManifestError, "relative path"):
            load_manifest(self.graph_path)

        graph_with_connections = self.graph_path.read_text(encoding="utf-8").replace(
            f'manifest = "{absolute_component}"',
            'manifest = "a/component.toml"',
        ) + "\n[[connections]]\nfrom = \"a.output\"\nto = \"b.input\"\n"
        self.graph_path.write_text(graph_with_connections, encoding="utf-8")
        with self.assertRaisesRegex(ManifestError, "automatic wiring"):
            load_manifest(self.graph_path)

    def test_validates_graph_manifest_paths_portably_before_using_them(self) -> None:
        original = self.graph_path.read_text(encoding="utf-8")
        unsafe = original.replace(
            'manifest = "a/component.toml"',
            'manifest = "a/component\\nforged.toml"',
        )
        self.graph_path.write_text(unsafe, encoding="utf-8")
        with self.assertRaisesRegex(ManifestError, "manifest.*unsafe|manifest.*terminal|manifest.*format"):
            load_manifest(self.graph_path)

        windows_absolute = original.replace(
            'manifest = "a/component.toml"',
            r"manifest = 'C:\project\component.toml'",
        )
        self.graph_path.write_text(windows_absolute, encoding="utf-8")
        with self.assertRaisesRegex(ManifestError, "relative path"):
            load_manifest(self.graph_path)

        windows_separators = original.replace(
            'manifest = "a/component.toml"',
            r"manifest = 'a\component.toml'",
        )
        self.graph_path.write_text(windows_separators, encoding="utf-8")
        graph = load_manifest(self.graph_path)
        self.assertIsInstance(graph, GraphManifest)

    def test_rejects_duplicate_component_ids_and_invalid_coordinates(self) -> None:
        duplicate = self.graph_path.read_text(encoding="utf-8").replace(
            'manifest = "b/component.toml"',
            'manifest = "a/component.toml"',
        )
        self.graph_path.write_text(duplicate, encoding="utf-8")
        with self.assertRaisesRegex(ManifestError, "duplicate component id"):
            load_manifest(self.graph_path)

        invalid_coordinate = self.graph_path.read_text(encoding="utf-8").replace(
            'manifest = "a/component.toml"',
            'manifest = "b/component.toml"',
            1,
        ).replace("x = 500.0", 'x = "right"')
        self.graph_path.write_text(invalid_coordinate, encoding="utf-8")
        with self.assertRaisesRegex(ManifestError, "coordinate"):
            load_manifest(self.graph_path)

        for invalid in ("nan", "+inf", "-inf"):
            with self.subTest(invalid=invalid):
                body = self.graph_path.read_text(encoding="utf-8").replace(
                    'x = "right"',
                    f"x = {invalid}",
                )
                self.graph_path.write_text(body, encoding="utf-8")
                with self.assertRaisesRegex(ManifestError, "finite"):
                    load_manifest(self.graph_path)
                self.graph_path.write_text(invalid_coordinate, encoding="utf-8")

    def test_rejects_unknown_graph_and_placement_fields(self) -> None:
        unknown_graph = self.graph_path.read_text(encoding="utf-8").replace(
            'name = "Example Graph"',
            'name = "Example Graph"\ndescripton = "typo"',
        )
        self.graph_path.write_text(unknown_graph, encoding="utf-8")
        with self.assertRaisesRegex(ManifestError, "unexpected field.*descripton"):
            load_manifest(self.graph_path)

        unknown_placement = unknown_graph.replace('descripton = "typo"\n', "").replace(
            'x = 100.0',
            'x = 100.0\nwire = "no"',
        )
        self.graph_path.write_text(unknown_placement, encoding="utf-8")
        with self.assertRaisesRegex(ManifestError, "unexpected field.*wire"):
            load_manifest(self.graph_path)

    def test_builds_component_and_graph_bytes(self) -> None:
        component_archive = build_bytes(self.component_a, identities=SequenceIdentityProvider())
        graph_archive = build_bytes(self.graph_path, identities=SequenceIdentityProvider())

        component_root = ET.fromstring(component_archive)
        graph_root = ET.fromstring(graph_archive)
        # Each component also carries the log panel it earns by default.
        self.assertEqual(component_root.findtext(".//chunk[@name='DefinitionObjects']/items/item[@name='ObjectCount']"), "2")
        self.assertEqual(graph_root.findtext(".//chunk[@name='DefinitionObjects']/items/item[@name='ObjectCount']"), "4")
        self.assertEqual(default_output_path(self.component_a), self.component_a.with_suffix(".ghclip"))
        self.assertEqual(default_output_path(self.graph_path), self.graph_path.with_suffix(".ghclip"))

    @staticmethod
    def _component_bounds(archive: bytes) -> tuple[float, float]:
        root = ET.fromstring(archive)
        for obj in root.iter("chunk"):
            if obj.get("name") != "Object":
                continue
            if obj.findtext("./items/item[@name='Name']") != "Python 3 Script":
                continue
            bounds = obj.find(".//chunk[@name='Attributes']/items/item[@name='Bounds']")
            assert bounds is not None
            return float(bounds.findtext("X") or "nan"), float(bounds.findtext("Y") or "nan")
        raise AssertionError("archive has no Python 3 Script component")

    def test_position_overrides_default_component_placement(self) -> None:
        default_archive = build_bytes(self.component_a, identities=SequenceIdentityProvider())
        self.assertEqual(self._component_bounds(default_archive), (200.0, 200.0))

        moved = build_bytes(
            self.component_a,
            identities=SequenceIdentityProvider(),
            position=(1234.0, 567.0),
        )
        self.assertEqual(self._component_bounds(moved), (1234.0, 567.0))

    def test_position_is_rejected_for_a_graph(self) -> None:
        with self.assertRaisesRegex(BuildError, "single-component"):
            build_bytes(
                self.graph_path,
                identities=SequenceIdentityProvider(),
                position=(0.0, 0.0),
            )

    def test_build_api_rejects_invalid_positions_without_replacing_output(self) -> None:
        destination = self.root / "existing.ghclip"
        destination.write_bytes(b"keep the existing archive")
        invalid_positions = (
            (float("nan"), 0.0),
            (0.0, float("inf")),
            (float("-inf"), 0.0),
            (True, 0.0),
            (0.0, False),
            ("1", 0.0),
            (10**400, 0.0),
            (0.0,),
            (0.0, 0.0, 0.0),
        )
        for position in invalid_positions:
            with self.subTest(position=position, operation="bytes"):
                with self.assertRaisesRegex(BuildError, "position"):
                    build_bytes(self.component_a, position=position)
            with self.subTest(position=position, operation="file"):
                with self.assertRaisesRegex(BuildError, "position"):
                    build_file(self.component_a, destination, position=position)
                self.assertEqual(destination.read_bytes(), b"keep the existing archive")

    def test_integer_positions_generate_inspectable_archives(self) -> None:
        destination = build_file(self.component_a, position=(-12, 34))
        inspect_archive(destination)
        self.assertEqual(self._component_bounds(destination.read_bytes()), (-12.0, 34.0))

    def test_every_successful_generated_archive_passes_strict_inspection(self) -> None:
        for manifest in (self.component_a, self.graph_path):
            with self.subTest(manifest=manifest.name):
                output = manifest.with_name(f"{manifest.stem}-inspected.ghclip")
                build_file(manifest, output, identities=SequenceIdentityProvider())
                summary = inspect_archive(output)
                expected_components = 1 if manifest == self.component_a else 2
                self.assertEqual(len(summary["components"]), expected_components)
                self.assertEqual(summary["object_count"], expected_components * 2)

    def test_invalid_build_preserves_existing_output(self) -> None:
        output = self.root / "existing.ghclip"
        output.write_bytes(b"keep me")
        self.component_a.write_text("kind = 'component'\nschema_version = 99\n", encoding="utf-8")

        with self.assertRaises(ManifestError):
            build_file(self.component_a, output)

        self.assertEqual(output.read_bytes(), b"keep me")

    def test_successful_build_replaces_output_without_temp_files(self) -> None:
        output = self.root / "result.ghclip"
        output.write_bytes(b"old")

        result = build_file(self.component_a, output, identities=SequenceIdentityProvider())

        self.assertEqual(result, output.resolve())
        self.assertTrue(output.read_bytes().startswith(b"<?xml"))
        self.assertEqual(list(self.root.glob(".result.ghclip.*.tmp")), [])

    def test_archive_size_limit_applies_before_return_or_output_replacement(self) -> None:
        output = self.root / "limited.ghclip"
        output.write_bytes(b"keep me")

        with patch.object(constants, "MAX_ARCHIVE_BYTES", 128, create=True):
            with self.assertRaisesRegex(BuildError, r"128.*actual|actual.*128"):
                build_bytes(self.graph_path, identities=SequenceIdentityProvider())
            with self.assertRaisesRegex(BuildError, r"128.*actual|actual.*128"):
                build_file(
                    self.graph_path,
                    output,
                    identities=SequenceIdentityProvider(),
                )

        self.assertEqual(output.read_bytes(), b"keep me")
        self.assertEqual(list(self.root.glob(".limited.ghclip.*.tmp")), [])

    def test_graph_child_errors_keep_safe_relative_context(self) -> None:
        invalid = self.component_b.read_text(encoding="utf-8").replace(
            'type = "str"',
            'type = "unsupported"',
        )
        self.component_b.write_text(invalid, encoding="utf-8", newline="")

        with self.assertRaises(ManifestError) as raised:
            load_manifest(self.graph_path)

        message = str(raised.exception)
        self.assertIn("b/component.toml", message)
        self.assertIn("outputs[0].type", message)
        self.assertNotIn(str(self.root), message)

    def test_output_parent_must_exist(self) -> None:
        output = self.root / "missing" / "result.ghclip"
        with self.assertRaisesRegex(BuildError, "output directory"):
            build_file(self.component_a, output)

    def test_output_requires_ghclip_and_cannot_replace_build_inputs(self) -> None:
        source = self.component_a.parent / "component.py"
        protected_paths = (
            self.component_a,
            source,
            self.graph_path,
            self.component_b,
            self.component_b.parent / "component.py",
        )
        originals = {path: path.read_bytes() for path in protected_paths}

        with self.assertRaisesRegex(BuildError, r"\.ghclip"):
            build_file(self.component_a, self.root / "result.xml")
        with self.assertRaisesRegex(BuildError, "build input"):
            build_file(self.component_a, self.component_a)
        with self.assertRaisesRegex(BuildError, "build input"):
            build_file(self.component_a, source)
        with self.assertRaisesRegex(BuildError, "build input"):
            build_file(self.graph_path, self.component_b)

        self.assertEqual({path: path.read_bytes() for path in protected_paths}, originals)

        symlink_target = self.root / "symlink-target.ghclip"
        symlink_target.write_bytes(b"keep target")
        symlink_output = self.root / "symlink-output.ghclip"
        try:
            symlink_output.symlink_to(symlink_target)
        except OSError as error:  # pragma: no cover - platform policy
            self.skipTest(f"symbolic links unavailable: {error}")
        with self.assertRaisesRegex(BuildError, "symbolic link"):
            build_file(self.component_a, symlink_output)
        self.assertEqual(symlink_target.read_bytes(), b"keep target")


if __name__ == "__main__":
    unittest.main()

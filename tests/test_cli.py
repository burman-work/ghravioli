from __future__ import annotations

import argparse
import hashlib
import io
import json
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from ghravioli import constants
from ghravioli.cli import _position, main
from ghravioli.clipboard import ClipboardUnavailable


class TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


class CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source_text = "result = value\nlog = 'ready'\n"
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
                id = "cli-example"
                name = "CLI Example"
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

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_cli(self, *arguments: str, clipboard_writer=None) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        status = main(
            list(arguments),
            stdout=stdout,
            stderr=stderr,
            clipboard_writer=clipboard_writer,
        )
        return status, stdout.getvalue(), stderr.getvalue()

    def test_validate_and_code_commands(self) -> None:
        status, stdout, stderr = self.run_cli("validate", str(self.manifest))
        self.assertEqual(status, 0)
        self.assertIn("valid component", stdout)
        self.assertEqual(stderr, "")

        status, stdout, stderr = self.run_cli("code", str(self.manifest))
        self.assertEqual(status, 0)
        self.assertEqual(stdout, self.source_text)
        self.assertEqual(stderr, "")

    def test_build_places_component_at_requested_position(self) -> None:
        output = self.root / "placed.ghclip"
        status, stdout, stderr = self.run_cli(
            "build", str(self.manifest), "-o", str(output), "--at", "1000,250"
        )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")

        root = ET.fromstring(output.read_bytes())
        bounds = None
        for obj in root.iter("chunk"):
            if obj.get("name") == "Object" and obj.findtext("./items/item[@name='Name']") == "Python 3 Script":
                bounds = obj.find(".//chunk[@name='Attributes']/items/item[@name='Bounds']")
                break
        self.assertIsNotNone(bounds)
        assert bounds is not None
        self.assertEqual(
            (float(bounds.findtext("X") or "nan"), float(bounds.findtext("Y") or "nan")),
            (1000.0, 250.0),
        )

    def test_position_argument_parses_and_validates(self) -> None:
        self.assertEqual(_position("0,0"), (0.0, 0.0))
        self.assertEqual(_position("12.5,-3"), (12.5, -3.0))
        for invalid in ("nope", "1", "1,2,3", "nan,0", "1,inf"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(argparse.ArgumentTypeError):
                    _position(invalid)

    def test_build_and_inspect_json_commands(self) -> None:
        output = self.root / "custom.ghclip"
        status, stdout, stderr = self.run_cli("build", str(self.manifest), "-o", str(output))
        self.assertEqual(status, 0)
        self.assertEqual(stdout.strip(), output.name)
        self.assertEqual(stderr, "")
        self.assertTrue(output.is_file())

        status, stdout, stderr = self.run_cli("inspect", str(output), "--json")
        self.assertEqual(status, 0)
        summary = json.loads(stdout)
        self.assertEqual(summary["kind"], "archive")
        self.assertEqual(len(summary["components"]), 1)
        self.assertEqual(summary["components"][0]["name"], "CLI Example")
        self.assertGreater(summary["components"][0]["source_bytes"], 0)
        self.assertEqual(
            summary["components"][0]["source_sha256"],
            hashlib.sha256(self.source_text.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(summary["path"], output.name)
        self.assertNotIn(str(self.root), json.dumps(summary))
        self.assertTrue(summary["has_source_wiring"])
        self.assertEqual(stderr, "")

        status, stdout, stderr = self.run_cli("inspect", str(self.manifest), "--json")
        self.assertEqual(status, 0)
        summary = json.loads(stdout)
        self.assertEqual(summary["kind"], "component")
        self.assertEqual(summary["outputs"][-1]["name"], "log")
        self.assertEqual(summary["source"], "component.py")
        self.assertNotIn(str(self.root), json.dumps(summary))
        self.assertEqual(stderr, "")

    def test_inspect_source_hash_code_archive_and_extract_commands(self) -> None:
        output = self.root / "review.ghclip"
        self.run_cli("build", str(self.manifest), "-o", str(output))

        status, stdout, stderr = self.run_cli("inspect", str(output), "--source")
        self.assertEqual(status, 0)
        self.assertIn('embedded source: "CLI Example"', stdout)
        self.assertIn(self.source_text, stdout)
        self.assertEqual(stderr, "")

        status, stdout, stderr = self.run_cli("inspect", str(output), "--sha256")
        self.assertEqual(status, 0)
        self.assertIn(hashlib.sha256(self.source_text.encode("utf-8")).hexdigest(), stdout)
        self.assertEqual(stderr, "")

        status, stdout, stderr = self.run_cli("code", str(output))
        self.assertEqual(status, 0)
        self.assertEqual(stdout, self.source_text)
        self.assertEqual(stderr, "")

        extracted = self.root / "extracted"
        status, stdout, stderr = self.run_cli("extract", str(output), "--output", str(extracted))
        self.assertEqual(status, 0)
        files = list(extracted.glob("*.py"))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_text(encoding="utf-8"), self.source_text)
        self.assertNotIn(str(self.root), stdout)
        self.assertEqual(stderr, "")

    def test_source_review_escapes_terminal_controls_but_exact_streams_remain_exact(self) -> None:
        unsafe_source = (
            "# controls \x1b]52;c;YQ==\x07 \u0085 and Unicode \u2028 \u2029 \u202e \u2066\n"
            "result = value\nlog = 'ready'\n"
        )
        (self.root / "component.py").write_text(unsafe_source, encoding="utf-8", newline="")
        archive = self.root / "unsafe.ghclip"
        status, _, stderr = self.run_cli("build", str(self.manifest), "-o", str(archive))
        self.assertEqual((status, stderr), (0, ""))

        status, stdout, stderr = self.run_cli("inspect", str(archive), "--source")
        self.assertEqual(status, 0)
        self.assertNotIn("\x1b", stdout)
        self.assertNotIn("\x07", stdout)
        self.assertNotIn("\u0085", stdout)
        self.assertNotIn("\u2028", stdout)
        self.assertNotIn("\u2029", stdout)
        self.assertNotIn("\u202e", stdout)
        self.assertNotIn("\u2066", stdout)
        self.assertIn(r"\u001b", stdout)
        self.assertIn(r"\u0007", stdout)
        self.assertIn(r"\u0085", stdout)
        self.assertIn(r"\u2028", stdout)
        self.assertIn(r"\u2029", stdout)
        self.assertIn(r"\u202e", stdout)
        self.assertIn(r"\u2066", stdout)
        self.assertEqual(stderr, "")

        status, stdout, stderr = self.run_cli("code", str(archive))
        self.assertEqual((status, stdout, stderr), (0, unsafe_source, ""))

        tty_stdout = TtyBuffer()
        tty_stderr = io.StringIO()
        status = main(
            ["code", str(archive)],
            stdout=tty_stdout,
            stderr=tty_stderr,
        )
        self.assertEqual(status, 1)
        self.assertEqual(tty_stdout.getvalue(), "")
        self.assertIn("unsafe terminal", tty_stderr.getvalue())

        tty_stdout = TtyBuffer()
        tty_stderr = io.StringIO()
        status = main(
            ["code", str(archive), "--unsafe-terminal"],
            stdout=tty_stdout,
            stderr=tty_stderr,
        )
        self.assertEqual((status, tty_stdout.getvalue(), tty_stderr.getvalue()), (0, unsafe_source, ""))

    def test_hash_output_json_quotes_component_names(self) -> None:
        body = self.manifest.read_text(encoding="utf-8").replace(
            'name = "CLI Example"',
            'name = "CLI \\"Example\\""',
        )
        self.manifest.write_text(body, encoding="utf-8")
        archive = self.root / "quoted.ghclip"
        self.run_cli("build", str(self.manifest), "-o", str(archive))

        status, stdout, stderr = self.run_cli("inspect", str(archive), "--sha256")

        self.assertEqual(status, 0)
        self.assertTrue(stdout.endswith('  "CLI \\"Example\\""\n'))
        self.assertEqual(stderr, "")

    def test_multi_component_code_requires_an_explicit_selection(self) -> None:
        second_dir = self.root / "second"
        second_dir.mkdir()
        second_source = "value = 2\nlog = 'second'\n"
        (second_dir / "component.py").write_text(
            second_source,
            encoding="utf-8",
            newline="",
        )
        (second_dir / "component.toml").write_text(
            textwrap.dedent(
                """
                kind = "component"
                schema_version = 1
                target = "rhino8-python3"
                target_python = "3.9"
                id = "second-component"
                name = "Second Component"
                source = "component.py"

                [[outputs]]
                name = "log"
                type = "str"
                access = "item"
                """
            ).strip()
            + "\n",
            encoding="utf-8",
            newline="",
        )
        graph = self.root / "graph.toml"
        graph.write_text(
            textwrap.dedent(
                """
                kind = "graph"
                schema_version = 1
                id = "cli-graph"
                name = "CLI Graph"

                [[components]]
                manifest = "component.toml"
                x = 100
                y = 100

                [[components]]
                manifest = "second/component.toml"
                x = 400
                y = 100
                """
            ).strip()
            + "\n",
            encoding="utf-8",
            newline="",
        )
        archive = self.root / "graph.ghclip"
        self.run_cli("build", str(graph), "--output", str(archive))

        status, stdout, stderr = self.run_cli("code", str(archive))

        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertIn("--component", stderr)
        self.assertIn("extract", stderr)

        try:
            status, stdout, stderr = self.run_cli(
                "code",
                str(archive),
                "--component",
                "2",
            )
        except SystemExit as error:
            self.fail(f"code --component is not implemented: {error}")
        self.assertEqual(status, 0)
        self.assertEqual(stdout, second_source)
        self.assertEqual(stderr, "")

        try:
            status, stdout, stderr = self.run_cli(
                "code",
                str(archive),
                "--component",
                "3",
            )
        except IndexError as error:
            self.fail(f"out-of-range component selection escaped the CLI: {error}")
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertIn("between 1 and 2", stderr)

    def test_copy_manifest_builds_fallback_before_using_clipboard(self) -> None:
        copied: list[bytes] = []

        def writer(data: bytes) -> str:
            copied.append(data)
            return "test-clipboard"

        status, stdout, stderr = self.run_cli("copy", str(self.manifest), clipboard_writer=writer)

        fallback = self.manifest.with_suffix(".ghclip")
        self.assertEqual(status, 0)
        self.assertIn("test-clipboard", stdout)
        self.assertIn(fallback.name, stdout)
        self.assertNotIn(str(self.root), stdout)
        self.assertEqual(copied, [fallback.read_bytes()])
        self.assertEqual(stderr, "")

    def test_copy_inspects_and_copies_the_same_archive_read(self) -> None:
        archive = self.root / "copy-once.ghclip"
        self.run_cli("build", str(self.manifest), "-o", str(archive))
        reviewed_bytes = archive.read_bytes()
        copied: list[bytes] = []
        archive_reads = 0
        real_read_bytes = Path.read_bytes

        def changing_read(path: Path) -> bytes:
            nonlocal archive_reads
            if path.name == archive.name:
                archive_reads += 1
                return reviewed_bytes if archive_reads == 1 else b"changed after inspection"
            return real_read_bytes(path)

        with patch.object(Path, "read_bytes", autospec=True, side_effect=changing_read):
            status, _, stderr = self.run_cli(
                "copy",
                str(archive),
                clipboard_writer=lambda data: copied.append(data) or "test-clipboard",
            )

        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(archive_reads, 1)
        self.assertEqual(copied, [reviewed_bytes])

    def test_extract_rejects_nonempty_and_symlink_directories(self) -> None:
        archive = self.root / "review.ghclip"
        self.run_cli("build", str(self.manifest), "-o", str(archive))

        nonempty = self.root / "nonempty"
        nonempty.mkdir()
        marker = nonempty / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        status, stdout, stderr = self.run_cli(
            "extract", str(archive), "--output", str(nonempty)
        )
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertIn("must be empty", stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

        target = self.root / "target"
        target.mkdir()
        link = self.root / "linked-output"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as error:  # pragma: no cover - platform policy
            self.skipTest(f"symbolic links unavailable: {error}")
        status, stdout, stderr = self.run_cli(
            "extract", str(archive), "--output", str(link)
        )
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertIn("symbolic link", stderr)
        self.assertEqual(list(target.iterdir()), [])

    def test_copy_returns_generated_file_when_clipboard_is_unavailable(self) -> None:
        def unavailable(_data: bytes) -> str:
            raise ClipboardUnavailable("no clipboard here")

        status, stdout, stderr = self.run_cli("copy", str(self.manifest), clipboard_writer=unavailable)

        fallback = self.manifest.with_suffix(".ghclip")
        self.assertEqual(status, 0)
        self.assertEqual(stdout.strip(), fallback.name)
        self.assertIn("clipboard unavailable", stderr)
        self.assertTrue(fallback.is_file())

    def test_success_output_escapes_unsafe_filesystem_labels(self) -> None:
        unsafe_archive = self.root / "built\x1b[31m\n\u202e.ghclip"

        with patch("ghravioli.cli.build_file", return_value=unsafe_archive):
            status, stdout, stderr = self.run_cli(
                "build",
                str(self.manifest),
                "--output",
                str(unsafe_archive),
            )

        self.assertEqual((status, stderr), (0, ""))
        self.assertNotIn("\x1b", stdout)
        self.assertNotIn("\u202e", stdout)
        self.assertEqual(stdout.count("\n"), 1)
        self.assertIn(r"\u001b", stdout)
        self.assertIn(r"\n", stdout)
        self.assertIn(r"\u202e", stdout)

        normal_archive = self.root / "normal.ghclip"
        self.run_cli("build", str(self.manifest), "--output", str(normal_archive))
        archive_bytes = normal_archive.read_bytes()
        with (
            patch("ghravioli.cli.build_file", return_value=unsafe_archive),
            patch.object(Path, "read_bytes", autospec=True, return_value=archive_bytes),
        ):
            status, stdout, stderr = self.run_cli(
                "copy",
                str(self.manifest),
                clipboard_writer=lambda _data: "test-clipboard",
            )

        self.assertEqual((status, stderr), (0, ""))
        self.assertNotIn("\x1b", stdout)
        self.assertNotIn("\u202e", stdout)
        self.assertEqual(stdout.count("\n"), 1)
        self.assertIn(r"\u001b", stdout)
        self.assertIn(r"\n", stdout)
        self.assertIn(r"\u202e", stdout)

    def test_copy_oversize_failure_preserves_fallback_and_skips_clipboard(self) -> None:
        fallback = self.manifest.with_suffix(".ghclip")
        fallback.write_bytes(b"keep me")
        writes: list[bytes] = []

        with patch.object(constants, "MAX_ARCHIVE_BYTES", 128):
            status, stdout, stderr = self.run_cli(
                "copy",
                str(self.manifest),
                clipboard_writer=lambda data: writes.append(data) or "test",
            )

        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertIn("archive exceeds maximum 128 bytes", stderr)
        self.assertEqual(fallback.read_bytes(), b"keep me")
        self.assertEqual(writes, [])
        self.assertEqual(list(self.root.glob(".component.ghclip.*.tmp")), [])

    def test_expected_errors_are_concise_and_have_no_traceback(self) -> None:
        self.manifest.write_text("kind = 'component'\nschema_version = 9\n", encoding="utf-8")

        status, stdout, stderr = self.run_cli("validate", str(self.manifest))

        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertIn("error:", stderr)
        self.assertNotIn("Traceback", stderr)
        self.assertNotIn(str(self.root), stderr)


if __name__ == "__main__":
    unittest.main()

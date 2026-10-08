from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ghravioli import __version__
from ghravioli.inspect import inspect_archive


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prepare_rhino_acceptance.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AcceptancePreparationTestCase(unittest.TestCase):
    def run_generator(
        self,
        output: Path,
        *,
        commit: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(SCRIPT), "--output", str(output)]
        if commit is not None:
            command.extend(["--commit", commit])
        elif not (ROOT / ".git").exists():
            command.extend(["--commit", "0" * 40])
        return subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_generator_creates_deterministic_reviewable_pending_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first"
            second = root / "second"

            first_result = self.run_generator(first)
            second_result = self.run_generator(second)

            self.assertEqual(first_result.returncode, 0, first_result.stderr)
            self.assertEqual(second_result.returncode, 0, second_result.stderr)
            manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["format_version"], 1)
            self.assertEqual(manifest["candidate"]["version"], __version__)
            self.assertRegex(manifest["candidate"]["commit"], r"^[0-9a-f]{40}$")
            self.assertEqual(manifest["manual_status"], "pending")
            self.assertEqual(
                [fixture["id"] for fixture in manifest["fixtures"]],
                ["scale-points", "json-config", "pipeline"],
            )

            for fixture in manifest["fixtures"]:
                archive = first / fixture["archive"]["path"]
                self.assertEqual(fixture["archive"]["sha256"], sha256(archive))
                self.assertGreater(inspect_archive(archive)["object_count"], 0)
                for item in (*fixture["manifests"], *fixture["sources"], *fixture["extracted"]):
                    path = first / item["path"] if item["kind"] == "extracted" else ROOT / item["path"]
                    self.assertEqual(item["sha256"], sha256(path))
                mirrored = second / fixture["archive"]["path"]
                self.assertEqual(archive.read_bytes(), mirrored.read_bytes())

            checklist = (first / "CHECKLIST.md").read_text(encoding="utf-8")
            self.assertIn("MANUAL STATUS: PENDING", checklist)
            self.assertNotIn("[x]", checklist.lower())
            self.assertNotIn(str(ROOT), (first / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                (first / "manifest.json").read_bytes(),
                (second / "manifest.json").read_bytes(),
            )

    def test_generator_refuses_existing_or_symbolic_link_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "existing"
            output.mkdir()
            marker = output / "keep.txt"
            marker.write_text("keep", encoding="utf-8")

            existing = self.run_generator(output)

            self.assertNotEqual(existing.returncode, 0)
            self.assertIn("already exists", existing.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

            target = root / "target"
            target.mkdir()
            link = root / "link"
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError as error:  # pragma: no cover - platform policy
                self.skipTest(f"symbolic links unavailable: {error}")
            linked = self.run_generator(link)
            self.assertNotEqual(linked.returncode, 0)
            self.assertIn("symbolic link", linked.stderr)
            self.assertEqual(list(target.iterdir()), [])

    def test_generator_accepts_only_a_full_explicit_origin_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit = "a" * 40

            valid = self.run_generator(root / "valid", commit=commit)
            invalid = self.run_generator(root / "invalid", commit="abc")

            self.assertEqual(valid.returncode, 0, valid.stderr)
            manifest = json.loads((root / "valid" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["candidate"]["commit"], commit)
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn("40-character", invalid.stderr)

    def test_acceptance_docs_cover_platform_clipboard_and_behavior_matrix(self) -> None:
        acceptance = (ROOT / "docs" / "RHINO_ACCEPTANCE.md").read_text(encoding="utf-8")
        checklist = (ROOT / "docs" / "RELEASE_CHECKLIST.md").read_text(encoding="utf-8")

        for required in (
            "Unicode",
            "pbcopy",
            "PowerShell",
            "clipboard hash",
            "str, float, bool, point, and brep",
            "required and optional",
            "item and list",
            "valid, null, malformed, and empty-list",
            "save, close, reopen",
            "exact Rhino",
        ):
            self.assertIn(required.lower(), acceptance.lower())
        self.assertIn("reusable template", checklist.lower())
        self.assertNotIn("[x]", checklist.lower())

    def test_private_acceptance_output_is_ignored(self) -> None:
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".audit/", gitignore)


if __name__ == "__main__":
    unittest.main()

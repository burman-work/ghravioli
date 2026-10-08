from __future__ import annotations

import json
import importlib.util
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CrossAgentSkillTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.skill_locations = (
            cls.root / "skills" / "grasshopper-python-components",
            cls.root / ".agents" / "skills" / "grasshopper-python-components",
            cls.root / ".claude" / "skills" / "grasshopper-python-components",
        )

    def load_sync_module(self):
        script = self.root / "scripts" / "sync_agent_skills.py"
        spec = importlib.util.spec_from_file_location("sync_agent_skills", script)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_codex_claude_and_distribution_copies_are_identical(self) -> None:
        module = self.load_sync_module()
        snapshots: list[dict[str, bytes]] = []
        for location in self.skill_locations:
            self.assertTrue(location.is_dir(), location)
            snapshots.append(module.snapshot(location))
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(snapshots[0], snapshots[2])

    def test_skill_has_portable_frontmatter_and_no_scaffold_placeholders(self) -> None:
        text = (self.skill_locations[0] / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = re.match(r"\A---\n(.*?)\n---\n", text, flags=re.DOTALL)
        self.assertIsNotNone(frontmatter)
        assert frontmatter is not None
        keys = [line.split(":", 1)[0] for line in frontmatter.group(1).splitlines() if ":" in line]
        self.assertEqual(keys, ["name", "description"])
        self.assertIn("name: grasshopper-python-components", frontmatter.group(1))
        self.assertIn("Use when", frontmatter.group(1))
        self.assertNotRegex(text, r"\bTODO\b|\[TODO")
        self.assertLess(len(text.splitlines()), 500)

    def test_skill_routes_directly_to_each_required_reference(self) -> None:
        skill = (self.skill_locations[0] / "SKILL.md").read_text(encoding="utf-8")
        references = {"authoring.md", "data-flow.md", "workflows.md", "compatibility.md"}
        for filename in references:
            self.assertIn(f"references/{filename}", skill)
            self.assertTrue((self.skill_locations[0] / "references" / filename).is_file())

    def test_skill_covers_observed_cross_component_failures(self) -> None:
        skill_dir = self.skill_locations[0]
        corpus = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (skill_dir / "SKILL.md", *sorted((skill_dir / "references").glob("*.md")))
        ).lower()
        decisions = {
            "mandatory logs": ("log", "string"),
            "no dictionaries on wires": ("dictionary", "wire"),
            "native geometry": ("native", "geometry"),
            "versioned JSON": ("json", "schema", "version"),
            "safe source paths": ("absolute path", "project"),
            "embedded default": ("embedded", "default"),
            "live link experimental": ("live-linked", "experimental"),
            "no automatic wiring claim": ("automatic wiring", "unsupported"),
            "target runtime": ("python 3.9", "target"),
            "experimental compatibility": ("experimental", "rhino"),
            "reuse rights": ("rights", "re-implement"),
            "edit files, not the canvas": ("rebuild", "script editor"),
            "canvas placement": ("--at", "graph manifest"),
            "sliders need a range": ("min", "max", "slider"),
        }
        for decision, terms in decisions.items():
            with self.subTest(decision=decision):
                for term in terms:
                    self.assertIn(term, corpus)

        self.assertIn("ghravioli", corpus)

    def test_skill_distinguishes_safe_review_from_exact_terminal_output(self) -> None:
        workflows = (
            self.skill_locations[0] / "references" / "workflows.md"
        ).read_text(encoding="utf-8").lower()

        for required in (
            "safe terminal",
            "exact machine stream",
            "--unsafe-terminal",
            "redirect",
            "extract",
        ):
            with self.subTest(required=required):
                self.assertIn(required, workflows)

    def test_openai_metadata_invokes_the_skill_by_name(self) -> None:
        metadata = (self.skill_locations[0] / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn('$grasshopper-python-components', metadata)
        self.assertIn('display_name: "Grasshopper Python Components"', metadata)

    def test_evaluation_suite_records_realistic_expected_behavior(self) -> None:
        evaluations = json.loads(
            (self.root / "tests" / "fixtures" / "skill_evaluations.json").read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(len(evaluations), 5)
        for evaluation in evaluations:
            self.assertTrue(evaluation["query"])
            self.assertGreaterEqual(len(evaluation["expected_behavior"]), 3)

    def test_sync_helper_confirms_discovery_copies_are_current(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/sync_agent_skills.py", "--check"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_sync_snapshot_ignores_incidental_operating_system_files(self) -> None:
        module = self.load_sync_module()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SKILL.md").write_text(
                "skill\n",
                encoding="utf-8",
                newline="",
            )
            (root / ".DS_Store").write_bytes(b"metadata")
            (root / "._SKILL.md").write_bytes(b"metadata")

            self.assertEqual(module.snapshot(root), {"SKILL.md": b"skill\n"})


if __name__ == "__main__":
    unittest.main()

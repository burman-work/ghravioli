from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DocumentationTestCase(unittest.TestCase):
    def test_readme_explains_installation_and_every_cli_workflow(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        for required in (
            "python3 -m venv .venv",
            "python -m pip install -e .",
            "ghravioli validate",
            "ghravioli build",
            "ghravioli inspect",
            "ghravioli copy",
            "ghravioli code",
            "examples/scale_points/component.toml",
            "examples/json_config/component.toml",
            "examples/pipeline.toml",
        ):
            with self.subTest(required=required):
                self.assertIn(required, readme)

    def test_readme_explains_cross_agent_skill_discovery(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        for required in (
            "skills/grasshopper-python-components",
            ".agents/skills/grasshopper-python-components",
            ".claude/skills/grasshopper-python-components",
            "python3 scripts/sync_agent_skills.py --check",
        ):
            with self.subTest(required=required):
                self.assertIn(required, readme)

    def test_repository_instructions_are_present_and_aligned(self) -> None:
        codex = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        normalized = " ".join(codex.split())

        self.assertEqual(codex, claude)
        for required in (
            "PYTHONPATH=src python3 -m unittest discover -s tests -v",
            "python3 scripts/sync_agent_skills.py --check",
            "test-first",
            "manual Rhino 8",
            "Do not add project-specific component code",
            "Python 3.9",
        ):
            with self.subTest(required=required):
                self.assertIn(required, normalized)

    def test_readme_links_complete_supporting_documentation(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        documents = sorted(path.name for path in (ROOT / "docs").glob("*.md"))

        self.assertGreaterEqual(len(documents), 10)
        for name in documents:
            with self.subTest(name=name):
                self.assertIn(f"docs/{name}", readme)

    def test_status_does_not_overstate_rhino_verification(self) -> None:
        compatibility = (ROOT / "docs" / "COMPATIBILITY.md").read_text(
            encoding="utf-8"
        )
        roadmap = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")

        self.assertIn("Pending manual verification", compatibility)
        self.assertIn("automatic wiring", compatibility.lower())
        self.assertIn("live-linked", roadmap.lower())
        self.assertIn("experimental", roadmap.lower())

    def test_readme_states_alpha_target_security_and_distribution_boundaries(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        normalized = " ".join(readme.split())

        for required in (
            "experimental",
            "0.1.0a2",
            "Python 3.9",
            "not affiliated with or endorsed",
            "PyPI",
            "fallback",
            "Base64 is encoding, not encryption",
            "CI runs the test suite",
            "manual Rhino",
            "macOS",
        ):
            with self.subTest(required=required):
                self.assertIn(required, normalized)
        self.assertNotIn("paste-ready", readme.lower())

    def test_release_checklist_preserves_external_acceptance_gates(self) -> None:
        acceptance = (ROOT / "docs" / "RHINO_ACCEPTANCE.md").read_text(
            encoding="utf-8"
        ).lower()
        checklist = (ROOT / "docs" / "RELEASE_CHECKLIST.md").read_text(
            encoding="utf-8"
        ).lower()

        for required in (
            "rhino 8.14",
            "paste the same archive twice",
            "point3d",
            "save, close, reopen",
            "neutral rhino-generated",
        ):
            self.assertIn(required, acceptance)
        for required in (
            "history-aware",
            "wheel",
            "source distribution",
            "licensed for redistribution",
            "rhino_acceptance.md",
        ):
            self.assertIn(required, checklist)

    def test_security_docs_distinguish_safe_review_from_exact_machine_output(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        security = (ROOT / "docs" / "SECURITY.md").read_text(encoding="utf-8")
        combined = " ".join((readme + "\n" + security).split()).lower()

        for required in (
            "safe terminal",
            "exact machine stream",
            "--unsafe-terminal",
            "redirect",
            "bidirectional",
            "utf-8-only",
        ):
            with self.subTest(required=required):
                self.assertIn(required, combined)

    def test_contract_and_windows_acceptance_commands_match_implementation(self) -> None:
        contract = (ROOT / "docs" / "COMPONENT_CONTRACT.md").read_text(encoding="utf-8")
        acceptance = (ROOT / "docs" / "RHINO_ACCEPTANCE.md").read_text(encoding="utf-8")
        normalized_contract = " ".join(contract.split())

        self.assertIn("inputs may be omitted", normalized_contract)
        self.assertIn("outputs is required", normalized_contract)
        self.assertIn("compiled", normalized_contract)
        self.assertIn("UTF8Encoding($false)", acceptance)
        self.assertIn("WriteAllText", acceptance)
        self.assertNotIn("Get-Clipboard -Raw | Set-Content", acceptance)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

import ghravioli


ROOT = Path(__file__).resolve().parents[1]


class PackagingTestCase(unittest.TestCase):
    def test_metadata_marks_an_alpha_and_uses_current_license_fields(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = metadata["project"]

        self.assertEqual(project["version"], "0.1.0a2")
        self.assertEqual(ghravioli.__version__, project["version"])
        self.assertIn("experimental", project["description"].lower())
        self.assertEqual(project["license"], "MIT")
        self.assertEqual(project["license-files"], ["LICENSE"])
        self.assertIn("setuptools>=77.0.3", metadata["build-system"]["requires"])
        self.assertNotIn("License :: OSI Approved :: MIT License", project["classifiers"])
        for version in ("3.11", "3.12", "3.13", "3.14"):
            self.assertIn(f"Programming Language :: Python :: {version}", project["classifiers"])

    def test_source_manifest_includes_repository_level_distribution_files(self) -> None:
        manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

        for required in (
            "include README.md AGENTS.md CLAUDE.md LICENSE",
            "graft docs",
            "graft examples",
            "graft templates",
            "graft skills",
            "graft .agents",
            "graft .claude",
            "graft .github",
            "graft scripts",
            "graft tests",
            "prune docs/plans",
            "global-exclude .DS_Store",
        ):
            with self.subTest(required=required):
                self.assertIn(required, manifest)

    def test_internal_agent_plans_are_not_tracked_for_distribution(self) -> None:
        plans = ROOT / "docs" / "plans"
        self.assertEqual(list(plans.rglob("*")) if plans.exists() else [], [])
        if not (ROOT / ".git").exists():
            return

        result = subprocess.run(
            ["git", "ls-files", "docs/plans"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_local_secret_and_operating_system_files_are_ignored(self) -> None:
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        for required in (".DS_Store", ".env", ".env.*", "!.env.example", "!*.env.example"):
            self.assertIn(required, gitignore)

    def test_public_python_api_is_small_and_explicit(self) -> None:
        for name in (
            "ComponentManifest",
            "GraphManifest",
            "build_bytes",
            "build_file",
            "inspect_archive",
            "load_manifest",
        ):
            with self.subTest(name=name):
                self.assertIn(name, ghravioli.__all__)
                self.assertTrue(hasattr(ghravioli, name))

    def test_ci_covers_claimed_python_and_operating_system_matrix(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )

        self.assertRegex(workflow, r"actions/checkout@[0-9a-f]{40}  # v7")
        self.assertRegex(workflow, r"actions/setup-python@[0-9a-f]{40}  # v7")
        self.assertNotRegex(workflow, r"uses:\s+actions/[^@]+@v\d+")
        for operating_system in ("ubuntu-latest", "macos-latest", "windows-latest"):
            self.assertIn(operating_system, workflow)
        for version in ('"3.11"', '"3.12"', '"3.13"', '"3.14"'):
            self.assertIn(version, workflow)
        for command in (
            "python -m unittest discover -s tests -v",
            "python -m compileall -q src scripts tests examples",
            "python scripts/sync_agent_skills.py --check",
            "python -m build",
            "python scripts/verify_sdist.py",
            "python scripts/discover_artifacts.py",
            "git diff --check",
            "ghravioli --help",
        ):
            self.assertIn(command, workflow)

    def test_ci_has_bounded_read_only_runs_and_cancels_superseded_work(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("concurrency:", workflow)
        self.assertIn("cancel-in-progress: true", workflow)
        self.assertEqual(workflow.count("timeout-minutes:"), 2)
        self.assertNotRegex(workflow, r"dist/ghravioli-[^\s]+\.(?:whl|tar\.gz)")

    def test_publish_workflow_uses_pinned_trusted_publishing_from_releases(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("release:\n    types: [published]", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertNotRegex(workflow, r"uses:\s+[^@\s]+@(?![0-9a-f]{40}\b)")
        self.assertEqual(workflow.count("id-token: write"), 1)
        self.assertIn("name: pypi\n      url: https://pypi.org/p/ghravioli", workflow)
        self.assertIn("pypa/gh-action-pypi-publish@", workflow)
        self.assertIn("TAG: ${{ github.event.release.tag_name }}", workflow)
        self.assertNotIn("password:", workflow)
        self.assertNotIn("secrets.", workflow)

    def test_dependabot_and_security_policy_are_ready_for_public_review(self) -> None:
        dependabot = (ROOT / ".github" / "dependabot.yml").read_text(
            encoding="utf-8"
        )
        security = (ROOT / ".github" / "SECURITY.md").read_text(encoding="utf-8")

        for required in (
            'package-ecosystem: "github-actions"',
            'package-ecosystem: "pip"',
            'directory: "/"',
            'interval: "weekly"',
        ):
            self.assertIn(required, dependabot)
        for required in (
            "0.1.0a2",
            "experimental alpha",
            "executable Python",
            "private vulnerability reporting",
            "not affiliated",
        ):
            self.assertIn(required, security)

    def test_artifact_discovery_requires_exactly_one_wheel_and_sdist(self) -> None:
        script = ROOT / "scripts" / "discover_artifacts.py"
        self.assertTrue(script.is_file())
        with tempfile.TemporaryDirectory() as directory:
            dist = Path(directory)
            wheel = dist / "ghravioli-0.1.0a2-py3-none-any.whl"
            sdist = dist / "ghravioli-0.1.0a2.tar.gz"
            wheel.write_bytes(b"wheel")
            sdist.write_bytes(b"sdist")

            result = subprocess.run(
                [sys.executable, str(script), "--dist", str(dist), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload, {"sdist": str(sdist.resolve()), "wheel": str(wheel.resolve())})

            (dist / "duplicate.whl").write_bytes(b"extra")
            duplicate = subprocess.run(
                [sys.executable, str(script), "--dist", str(dist), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertIn("exactly one wheel", duplicate.stderr)


if __name__ == "__main__":
    unittest.main()

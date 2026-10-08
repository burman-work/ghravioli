from __future__ import annotations

import importlib
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublicIdentityTestCase(unittest.TestCase):
    def test_package_repository_cli_and_version_use_ghravioli(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = metadata["project"]

        self.assertEqual(project["name"], "ghravioli")
        self.assertEqual(project["version"], "0.1.0a2")
        self.assertEqual(project["scripts"], {"ghravioli": "ghravioli.cli:main"})
        self.assertEqual(
            project["urls"]["Repository"],
            "https://github.com/burman-work/ghravioli",
        )
        self.assertTrue((ROOT / "src" / "ghravioli").is_dir())

        package = importlib.import_module("ghravioli")
        self.assertEqual(package.__version__, "0.1.0a2")

    def test_readme_uses_display_name_and_machine_identifier(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        normalized = " ".join(readme.split())

        self.assertTrue(readme.startswith("# ghRavioli\n"))
        self.assertIn(
            "An agent skill and command-line tool for writing Grasshopper Python "
            "components that are easy to modify and arrange.",
            normalized,
        )
        self.assertIn("`ghravioli` 0.1.0a2", readme)
        self.assertIn("github.com/burman-work/ghravioli", readme)
        self.assertIn("ghravioli --help", readme)


if __name__ == "__main__":
    unittest.main()

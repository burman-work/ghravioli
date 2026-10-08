from __future__ import annotations

import re
import tempfile
import tomllib
import unittest
from pathlib import Path

from ghravioli.manifest import load_manifest


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    ROOT / "docs" / "COMPONENT_CONTRACT.md",
    ROOT / "skills" / "grasshopper-python-components" / "references" / "authoring.md",
    ROOT / "skills" / "grasshopper-python-components" / "references" / "workflows.md",
)


class DocumentationExamplesTestCase(unittest.TestCase):
    def test_every_toml_manifest_example_validates(self) -> None:
        examples: list[tuple[Path, str]] = []
        for document in DOCUMENTS:
            text = document.read_text(encoding="utf-8")
            examples.extend(
                (document, match.group(1).strip() + "\n")
                for match in re.finditer(r"```toml\n(.*?)```", text, flags=re.DOTALL)
            )
        self.assertGreaterEqual(len(examples), 4)

        for index, (document, example) in enumerate(examples):
            with self.subTest(document=document.name, index=index):
                data = tomllib.loads(example)
                self.assertIn(data.get("kind"), {"component", "graph"})
                self.assertIn("id", data)
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    manifest_path = root / "example.toml"
                    manifest_path.write_text(example, encoding="utf-8")
                    if data["kind"] == "component":
                        source = root / data["source"]
                        source.parent.mkdir(parents=True, exist_ok=True)
                        source.write_text("result = []\nlog = 'ready'\n", encoding="utf-8")
                    else:
                        for child_index, placement in enumerate(data["components"]):
                            self.write_child_component(
                                root / placement["manifest"],
                                f"documented-child-{child_index}",
                            )
                    load_manifest(manifest_path)

    def test_skill_commands_and_contract_wording_match_behavior(self) -> None:
        authoring = (DOCUMENTS[1]).read_text(encoding="utf-8")
        workflows = (DOCUMENTS[2]).read_text(encoding="utf-8")

        self.assertIn("unique across inputs and outputs", authoring)
        self.assertNotIn("dist/component.ghclip", workflows)
        self.assertIn("inspect component.ghclip --source", workflows)

    @staticmethod
    def write_child_component(path: Path, component_id: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        (path.parent / "component.py").write_text("log = 'ready'\n", encoding="utf-8")
        path.write_text(
            "\n".join(
                (
                    'kind = "component"',
                    "schema_version = 1",
                    'target = "rhino8-python3"',
                    'target_python = "3.9"',
                    f'id = "{component_id}"',
                    f'name = "{component_id}"',
                    'source = "component.py"',
                    "",
                    "[[outputs]]",
                    'name = "log"',
                    'type = "str"',
                    'access = "item"',
                    "",
                )
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()

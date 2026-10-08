from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


class RepositoryPolicyTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]

    def repository_files(self) -> list[Path]:
        """Return files that Git can distribute, plus non-ignored candidates."""

        if (self.root / ".git").exists():
            result = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                cwd=self.root,
                check=True,
                capture_output=True,
            )
            return [
                self.root / Path(value.decode("utf-8", errors="surrogateescape"))
                for value in result.stdout.split(b"\x00")
                if value
            ]
        return [path for path in self.root.rglob("*") if path.is_file()]

    def distributable_text_files(self) -> list[Path]:
        ignored_directories = {".git", ".venv", "build", "dist", "__pycache__"}
        text_names = {".gitignore", "LICENSE", "MANIFEST.in"}
        text_suffixes = {".json", ".md", ".py", ".toml", ".yaml", ".yml"}
        return sorted(
            path
            for path in self.repository_files()
            if path.is_file()
            and path.resolve() != Path(__file__).resolve()
            and not ignored_directories.intersection(path.relative_to(self.root).parts)
            and (path.name in text_names or path.suffix in text_suffixes)
        )

    def test_distributable_files_contain_no_user_absolute_paths_or_secret_shapes(self) -> None:
        forbidden = (
            re.compile("/" + r"Users/[^/\s]+/"),
            re.compile(r"[A-Za-z]:\\Users\\"),
            re.compile(r"\bgh[opurs]_[A-Za-z0-9]{20,}\b"),
            re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
            re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
            re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
            re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
            re.compile(r"(?i)(?:password|secret|token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"),
        )
        violations: list[str] = []
        for path in self.distributable_text_files():
            text = path.read_text(encoding="utf-8")
            for pattern in forbidden:
                if pattern.search(text):
                    violations.append(f"{path.relative_to(self.root)}: {pattern.pattern}")
        self.assertEqual(violations, [])

    def test_public_tree_contains_no_overstated_compatibility_claim(self) -> None:
        violations = []
        for path in self.distributable_text_files():
            if "tests" in path.relative_to(self.root).parts:
                continue
            if "paste-ready" in path.read_text(encoding="utf-8").lower():
                violations.append(str(path.relative_to(self.root)))
        self.assertEqual(violations, [])

    def test_distributable_tree_contains_no_binary_or_os_metadata(self) -> None:
        violations: list[str] = []
        ignored_directories = {".git", ".venv", "build", "dist", "__pycache__"}
        for path in self.repository_files():
            if (
                not path.is_file()
                or ignored_directories.intersection(path.relative_to(self.root).parts)
            ):
                continue
            if path.name in {".DS_Store", "Thumbs.db"} or path.name.startswith("._"):
                violations.append(str(path.relative_to(self.root)))
            elif b"\x00" in path.read_bytes():
                violations.append(str(path.relative_to(self.root)))
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()

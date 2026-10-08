"""User-facing errors raised by ghravioli."""

from __future__ import annotations

from pathlib import Path

from ghravioli.display import escape_terminal_label


class ManifestError(ValueError):
    """A manifest could not be parsed or violated the component contract."""

    def __init__(
        self,
        path: Path,
        message: str,
        *,
        field: str | None = None,
        display_path: str | None = None,
    ) -> None:
        self.path = Path(path)
        self.field = field
        self.message = message
        self.display_path = display_path or self.path.name
        safe_display_path = escape_terminal_label(self.display_path)
        safe_field = escape_terminal_label(field) if field else None
        safe_message = escape_terminal_label(message)
        context = f" ({safe_field})" if safe_field else ""
        super().__init__(f"{safe_display_path}{context}: {safe_message}")


class BuildError(RuntimeError):
    """An archive could not be written safely."""

    def __init__(self, path: Path, message: str) -> None:
        self.path = Path(path)
        self.message = message
        safe_path = escape_terminal_label(self.path.name)
        safe_message = escape_terminal_label(message)
        super().__init__(f"{safe_path}: {safe_message}")

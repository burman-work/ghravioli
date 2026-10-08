"""Terminal-display safety helpers shared by manifests and archive inspection."""

from __future__ import annotations

import json
import unicodedata


def is_unsafe_terminal_character(character: str, *, allow_layout: bool = False) -> bool:
    """Return whether one character can alter or spoof terminal output."""

    if allow_layout and character in {"\t", "\n"}:
        return False
    codepoint = ord(character)
    return (
        codepoint < 0x20
        or 0x7F <= codepoint < 0xA0
        or character in {"\u2028", "\u2029"}
        or unicodedata.category(character) == "Cf"
    )


def contains_unsafe_terminal_text(value: str, *, allow_layout: bool = False) -> bool:
    """Return whether text contains terminal controls or spoofing characters."""

    return any(
        is_unsafe_terminal_character(character, allow_layout=allow_layout)
        for character in value
    )


def escape_terminal_text(value: str) -> str:
    """Escape unsafe characters while preserving ordinary Unicode and line layout."""

    return "".join(
        json.dumps(character, ensure_ascii=True)[1:-1]
        if is_unsafe_terminal_character(character, allow_layout=True)
        else character
        for character in value
    )


def escape_terminal_label(value: str) -> str:
    """Escape controls and formatting characters in a single-line label."""

    return "".join(
        json.dumps(character, ensure_ascii=True)[1:-1]
        if is_unsafe_terminal_character(character)
        else character
        for character in value
    )

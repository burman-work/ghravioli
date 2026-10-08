"""Shared validation for manifest and embedded Python source."""

from __future__ import annotations

import ast


TARGET_PYTHON = "3.9"
TARGET_FEATURE_VERSION = (3, 9)
MAX_SOURCE_BYTES = 1024 * 1024


class SourceValidationError(ValueError):
    """Python source violates the supported embedded-code contract."""


def decode_and_validate_source(source_bytes: bytes, *, filename: str) -> str:
    """Decode UTF-8 Python and enforce size, null, grammar, and compiler rules."""

    if len(source_bytes) > MAX_SOURCE_BYTES:
        raise SourceValidationError(f"source exceeds {MAX_SOURCE_BYTES} bytes")
    if b"\x00" in source_bytes:
        raise SourceValidationError("source contains a null byte")
    try:
        source_text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SourceValidationError("source must be UTF-8") from error
    try:
        tree = ast.parse(
            source_text,
            filename=filename,
            mode="exec",
            feature_version=TARGET_FEATURE_VERSION,
        )
        compile(tree, filename, "exec")
    except SyntaxError as error:
        detail = error.msg or "invalid syntax"
        location = f" at line {error.lineno}" if error.lineno else ""
        raise SourceValidationError(
            f"invalid Python {TARGET_PYTHON} syntax{location}: {detail}"
        ) from error
    return source_text

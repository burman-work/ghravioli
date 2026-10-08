"""Emit portable component state as a versioned JSON string."""

import json


config = ""
log = "not started"

try:
    normalized_label = "untitled" if label is None or not str(label).strip() else str(label).strip()
    normalized_count = 0 if count is None else int(round(float(count)))
    envelope = {
        "schema": "example.config",
        "version": 1,
        "producer": "example-json-config",
        "payload": {
            "label": normalized_label,
            "count": normalized_count,
        },
        "warnings": [],
    }
    config = json.dumps(envelope, separators=(",", ":"), sort_keys=True)
    log = f"encoded example.config v1 for {normalized_label!r} with count {normalized_count}"
except (TypeError, ValueError) as error:
    config = ""
    log = f"error: {type(error).__name__}: {error}"

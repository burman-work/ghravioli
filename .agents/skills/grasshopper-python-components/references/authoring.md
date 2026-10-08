# Component authoring

## Files and runtime

Each component has UTF-8 Python source and a TOML interface manifest. Treat the
manifest as the contract; do not infer public ports from comments. Embedded
source targets Python 3.9, so avoid later syntax and APIs.

Initialise every output before the main operation. Catch anticipated conversion
failures rather than masking programming errors:

```python
result = None
log = "not run"

try:
    result = value * float(factor)
    log = "scaled value"
except (TypeError, ValueError) as error:
    result = None
    log = "input error: {}".format(error)
```

Logs should include useful counts, decisions, fallbacks, or validation failures.

## Manifest

```toml
kind = "component"
schema_version = 1
target = "rhino8-python3"
target_python = "3.9"
id = "scale-points"
name = "Scale Points"
description = "Scale points from a centre point."
source = "component.py"

[[inputs]]
name = "points"
type = "point"
access = "list"

[[inputs]]
name = "factor"
type = "float"
access = "item"
optional = true

[[outputs]]
name = "scaled_points"
type = "point"
access = "list"

[[outputs]]
name = "log"
type = "str"
access = "item"
```

Schema version, target, and target Python are exact. Unknown fields fail.
Port names are valid Python identifiers, cannot be `out`, and are
unique across inputs and outputs. Exactly one output is named `log` with string type and item
access. Only inputs may declare `optional`.

Access modes are `item` and `list`. Type tokens are `str`, `float`, `bool`,
`point`, `brep`, `generic`, `int`, `vector`, `surface`, `curve`, `mesh`,
`geometry`, and `plane`. Only `str`, `float`, `bool`, `point`, and `brep`
currently receive converter metadata; acceptance in Rhino remains pending.

Source stays beneath its manifest, is at most 1 MiB, uses XML-safe UTF-8 text,
and parses under Python 3.9 grammar.

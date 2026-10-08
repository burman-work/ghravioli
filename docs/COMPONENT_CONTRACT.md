# Component contract

Schema version 1 separates Python computation from the Grasshopper interface.
The schema is closed: misspelled or unknown fields are errors rather than
silently ignored configuration.

## Component manifest

```toml
kind = "component"
schema_version = 1
target = "rhino8-python3"
target_python = "3.9"
id = "scale-values"
name = "Scale Values"
source = "component.py"
description = "Scale a list of numbers."

[[inputs]]
name = "values"
nickname = "V"
description = "Values to scale."
type = "float"
access = "list"
optional = false

[[outputs]]
name = "result"
type = "float"
access = "list"

[[outputs]]
name = "within_tolerance"
description = "True when every scaled value stayed inside the declared range."
type = "bool"
access = "item"
panel = true

[[outputs]]
name = "log"
description = "Human-readable execution summary."
type = "str"
access = "item"
```

An output may set `panel = true` to have a panel placed and wired to it, so its
value is readable the moment the component is pasted. `log` is panelled
automatically. `panel` applies only to outputs.

## Canvas presentation

Four optional top-level booleans control how the generated archive presents
itself, and all default to `true`. An `item` input may also declare `default`,
and a numeric one `min` and `max`, which drive the widget it earns. This is a
complete manifest using all of them:

```toml
kind = "component"
schema_version = 1
target = "rhino8-python3"
target_python = "3.9"
id = "scale-values"
name = "Scale Values"
source = "component.py"
description = "Scale a list of numbers."

legible_names = true      # write full port names as canvas nicknames
log_panel = true          # place a panel wired to the log output
input_widgets = true      # place a toggle or slider on eligible inputs
standard_output = true    # keep Grasshopper's own out console

[[inputs]]
name = "values"
type = "float"
access = "list"

[[inputs]]
name = "factor"
description = "Scale factor."
type = "float"
access = "item"
min = 0.0
max = 10.0
default = 1.0

[[inputs]]
name = "normalize"
description = "Divide by the largest value first."
type = "bool"
access = "item"
default = false

[[outputs]]
name = "result"
type = "float"
access = "list"

[[outputs]]
name = "log"
description = "Human-readable execution summary."
type = "str"
access = "item"
```

`min` and `max` must be declared together with `min` smaller than `max`. A
numeric `default` requires that range and must fall between it; all three values
must be whole numbers for an `int` port. They apply only to `item` access and
only to `float` and `int`; a `bool` port may declare `default` alone. A numeric
port without a range earns no slider rather than an invented domain.

See [canvas presentation](CANVAS.md) for what each flag emits and which parts
remain unverified against Rhino.

## Field rules

Required fields are `kind`, `schema_version`, `target`, `target_python`, `id`,
`name`, and `source`. `description` and `inputs` are optional; inputs may be
omitted. In practice, outputs is required because every component must declare
exactly one `log` output. `schema_version` must be the integer `1`, not a
boolean.

The only supported component target is `rhino8-python3` with target Python
3.9. The builder itself requires Python 3.11 or newer. Source is UTF-8, at most
1 MiB, free of null bytes, parsed with the Python 3.9 grammar, and compiled
before an archive is generated.

Every port requires `name`, `type`, and `access`; `nickname` and `description`
are optional, and only inputs may set `optional`. Port names must be valid
Python identifiers, cannot be `out`, and must be unique across inputs and
outputs. Every component declares exactly one `log` output with string type and
item access.

Manifest files are limited to 256 KiB, component and port names to 200
characters, descriptions to 4,000 characters, ports to 128 per direction, and
graph placements to 256. Text embedded in generated XML must use XML 1.0 legal
characters.

Supported access modes are `item` and `list`. Supported type tokens are `str`,
`float`, `bool`, `point`, `brep`, `generic`, `int`, `vector`, `surface`,
`curve`, `mesh`, `geometry`, and `plane`. Only `str`, `float`, `bool`, `point`,
and `brep` currently receive converter identifiers confirmed by ghRavioli's tests;
other tokens remain unhinted pending Rhino acceptance.

## Graph manifest

```toml
kind = "graph"
schema_version = 1
id = "example-pipeline"
name = "Example Pipeline"

[[components]]
manifest = "first/component.toml"
x = 200.0
y = 200.0
```

Child manifests must be relative to and contained by the graph directory.
Component IDs are unique within a graph. Coordinates are finite numbers. A
`connections` field is rejected because automatic wiring is unsupported.

## Build boundary

Output must end in `.ghclip`. A build refuses to overwrite its top-level
manifest, any child manifest, or any referenced Python source. Once validation
and archive construction succeed, output replacement is atomic.

Initialise outputs before computation. Catch only anticipated data conversion
errors, and summarise success, counts, fallbacks, or failures in `log`. The
standard Grasshopper `out` console exists separately from declared ports.

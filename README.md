# ghRavioli

An agent skill and command-line tool for writing Grasshopper Python components
in code, verifying them, and copy-pasting them into Grasshopper. The components
stay easy to modify and arrange.

Grasshopper keeps a script component's code inside the canvas, where a coding
agent can't easily read, edit or diff it. ghRavioli keeps each component in two
ordinary files instead:

- `component.py` holds the computation;
- `component.toml` declares the inputs and outputs, and how the component sits
  on the canvas.

An agent such as Claude Code or Codex edits those files like any other code.
`ghravioli build` turns them into a `.ghclip` archive, and you paste the
archive onto the Grasshopper canvas. To change a component, edit the files,
rebuild and paste again.

The skill in
[`skills/grasshopper-python-components`](https://github.com/burman-work/ghravioli/tree/main/skills/grasshopper-python-components)
shows the agent how to write components that stay easy to work with: one job
per component, readable port names, a `log` output on every component, native
geometry on the wires and versioned JSON for anything more complex. The builder
handles the layout. A pasted component shows its full port names, a panel with
its log, and a slider or toggle on each input that can take one.

## Status

`ghravioli` 0.1.0a2 is an experimental alpha for Rhino 8 and its Python 3
Script component.

- A generated archive with a component, four sliders, four toggles and a log
  panel pastes onto the canvas in Rhino 8.31 on Windows 10. The test is
  recorded in [Rhino acceptance](https://github.com/burman-work/ghravioli/blob/main/docs/RHINO_ACCEPTANCE.md).
- That test didn't check each slider's range and value, each toggle's state,
  or saving and reopening the definition. Those manual Rhino checks are still
  to do.
- Nobody has tested it in Rhino on macOS yet.
- CI runs the test suite on Linux, macOS and Windows with Python 3.11 to 3.14.
  That covers the builder, not Rhino.

The builder needs Python 3.11 or newer. Component code is checked against
Python 3.9, the version Rhino 8's Python 3 component runs.

An archive can position several components, but ghRavioli doesn't wire them to
each other; you connect them on the canvas. The only wires it creates run
between a component and its own panels, sliders and toggles.

## Install

```bash
python -m pip install ghravioli
ghravioli --help
```

The PyPI package contains the command-line tool and the Python library. The
agent skill, examples and docs live in the repository, so clone it as well if
you want those:

```bash
git clone https://github.com/burman-work/ghravioli.git
cd ghravioli
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

On Windows, activate with `.venv\Scripts\activate`.

## Using the skill with an agent

Install the skill into Claude Code, Codex and other agents with
[skills](https://skills.sh/burman-work/ghravioli):

```bash
npx skills add burman-work/ghravioli
```

Inside this repository, Claude Code finds the skill in
`.claude/skills/grasshopper-python-components` and Codex finds it in
`.agents/skills/grasshopper-python-components`. To use it in another project,
copy `skills/grasshopper-python-components` into that project's skill folder
and make sure the `ghravioli` command is installed where the agent can run it.

Then ask for a component in plain terms, for example: "Make a Grasshopper
component that offsets a curve by a distance between 0 and 5, with a toggle to
flip the side." The agent writes the Python file and the manifest, builds the
archive and inspects it. You paste it.

## A component

[`examples/scale_points/component.py`](https://github.com/burman-work/ghravioli/blob/main/examples/scale_points/component.py) is
ordinary Python. Grasshopper supplies the inputs as variables, and the script
sets the outputs:

```python
scaled_points = []
log = "not started"

try:
    input_points = [] if points is None else list(points)
    scale_factor = 1.0 if factor is None else float(factor)
    scaled_points = [point * scale_factor for point in input_points if point is not None]
    skipped = len(input_points) - len(scaled_points)
    log = f"scaled {len(scaled_points)} point(s) by {scale_factor:g}; skipped {skipped} null value(s)"
except (TypeError, ValueError) as error:
    scaled_points = []
    log = f"error: {type(error).__name__}: {error}"
```

[`examples/scale_points/component.toml`](https://github.com/burman-work/ghravioli/blob/main/examples/scale_points/component.toml)
declares its interface. The `min`, `max` and `default` on `factor` give that
input a slider when the archive is pasted:

```toml
kind = "component"
schema_version = 1
target = "rhino8-python3"
target_python = "3.9"
id = "example-scale-points"
name = "Scale Points"
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
min = 0.0
max = 10.0
default = 1.0

[[outputs]]
name = "scaled_points"
type = "point"
access = "list"

[[outputs]]
name = "log"
type = "str"
access = "item"
```

Validate, build, inspect, then copy it to the clipboard:

```bash
ghravioli validate examples/scale_points/component.toml
ghravioli build examples/scale_points/component.toml --output scale-points.ghclip
ghravioli inspect scale-points.ghclip --json
ghravioli copy examples/scale_points/component.toml
```

Paste onto the Grasshopper canvas. `copy` accepts a manifest or a `.ghclip`
and builds first when given a manifest.

[`examples/json_config/component.toml`](https://github.com/burman-work/ghravioli/blob/main/examples/json_config/component.toml)
shows a component that passes its settings on as a versioned JSON string.

## Arranging components on the canvas

A pasted archive lands at the position it was built with, not under the mouse.
Grasshopper only re-anchors a paste for its own clipboard format, and these
archives arrive as text. The default position is `200, 200`. Pass `--at X,Y`
to `build` or `copy` to put a single component somewhere else, for example
`--at 0,0`.

To place several components in one paste, list them in a graph manifest with a
position for each, as in [`examples/pipeline.toml`](https://github.com/burman-work/ghravioli/blob/main/examples/pipeline.toml):

```toml
kind = "graph"
schema_version = 1
id = "example-pipeline"
name = "Example Pipeline"

[[components]]
manifest = "json_config/component.toml"
x = 200.0
y = 200.0

[[components]]
manifest = "scale_points/component.toml"
x = 440.0
y = 200.0
```

Four settings at the top of a component manifest control how it looks once
pasted. All four default to `true`:

```toml
legible_names = true    # show full port names instead of nicknames
log_panel = true        # add a panel wired to the log output
input_widgets = true    # add a toggle or slider to inputs that can take one
standard_output = true  # keep Grasshopper's own out console
```

A boolean input gets a toggle. A number input gets a slider only when the
manifest gives it a `min` and `max`, so no slider has a made-up range. Any
other output can ask for its own panel with `panel = true`. Keep the `out`
console while debugging: it shows tracebacks, which `log` can't. See
[canvas presentation](https://github.com/burman-work/ghravioli/blob/main/docs/CANVAS.md).

## Passing data between components

- Keep Rhino geometry on native geometry wires.
- Send complex settings as a versioned JSON string, and check the schema and
  version where it's read.
- Don't put Python dictionaries or custom objects on a wire. Grasshopper can't
  display them, and they don't survive recomputes reliably.
- Give every component exactly one `log` output: a short summary for a person
  to read, kept apart from the data.

[Data flow](https://github.com/burman-work/ghravioli/blob/main/docs/DATA_FLOW.md) and the
[component contract](https://github.com/burman-work/ghravioli/blob/main/docs/COMPONENT_CONTRACT.md) have the details.

## Checking an archive before you paste it

A `.ghclip` contains executable Python. Base64 is encoding, not encryption, so
treat an archive from someone else like any code you're about to run:

```bash
ghravioli inspect archive.ghclip --source   # readable source, control characters escaped
ghravioli inspect archive.ghclip --sha256   # a hash of each component's source
ghravioli extract archive.ghclip --output reviewed-source
```

`inspect --source` is the safe terminal view. `ghravioli code` is an exact
machine stream with nothing escaped, for redirecting to a file or another tool.
It refuses to write to a terminal when the source contains unsafe control
characters, unless you pass `--unsafe-terminal`. In a multi-component archive,
choose a component with `--component N`, counting from 1:

```bash
ghravioli code scale-points.ghclip > scale_points.py
ghravioli code pipeline.ghclip --component 2 > second.py
```

The inspector only accepts archives in the exact shape ghRavioli generates.
That makes review easier, but it doesn't make the code safe to run. Embedded
source keeps its own copyright and licence; building an archive doesn't grant
the right to redistribute it. See [security](https://github.com/burman-work/ghravioli/blob/main/docs/SECURITY.md).

## If the clipboard doesn't work

`ghravioli copy` writes the `.ghclip` file first, then tries `pbcopy` on macOS,
PowerShell on Windows, or `wl-copy` or `xclip` on Linux. If none is available,
move the file to the Rhino machine and run `ghravioli copy scale-points.ghclip`
there. As a last fallback, open the `.ghclip` as UTF-8 text, copy the whole XML
document and paste it onto the canvas. Don't double-click it; it isn't a
Grasshopper definition file.

## Licence and support

ghRavioli is released under the [MIT licence](https://github.com/burman-work/ghravioli/blob/main/LICENSE). You can use, change and
redistribute it, including commercially, as long as the licence notice stays
with copies. It is provided as is, with no support, warranty, or promise of
fixes or updates.

## Python API

The public API is `load_manifest`, `build_bytes`, `build_file`,
`inspect_archive`, `ComponentManifest` and `GraphManifest`. Everything else in
the package is internal and may change during the alpha. See
[distribution](https://github.com/burman-work/ghravioli/blob/main/docs/DISTRIBUTION.md) for what a package install includes.

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m compileall -q src scripts tests examples
PYTHONPATH=src python3 -m ghravioli --help
python3 scripts/sync_agent_skills.py --check
python3 scripts/audit_repository.py --tree
python3 -m build
python3 scripts/discover_artifacts.py --dist dist --json
python3 scripts/prepare_rhino_acceptance.py --output .audit/rhino-0.1.0a2
```

`skills/grasshopper-python-components` is the canonical skill. After editing
it, run `python3 scripts/sync_agent_skills.py` to update the copies in
`.agents/skills/` and `.claude/skills/`. `AGENTS.md` and `CLAUDE.md` hold the
same repository instructions for agents working on ghRavioli itself.

## Documentation

- [Component contract](https://github.com/burman-work/ghravioli/blob/main/docs/COMPONENT_CONTRACT.md)
- [Canvas presentation](https://github.com/burman-work/ghravioli/blob/main/docs/CANVAS.md)
- [Data flow between components](https://github.com/burman-work/ghravioli/blob/main/docs/DATA_FLOW.md)
- [Compatibility](https://github.com/burman-work/ghravioli/blob/main/docs/COMPATIBILITY.md)
- [Rhino acceptance](https://github.com/burman-work/ghravioli/blob/main/docs/RHINO_ACCEPTANCE.md)
- [Design](https://github.com/burman-work/ghravioli/blob/main/docs/DESIGN.md)
- [Roadmap](https://github.com/burman-work/ghravioli/blob/main/docs/ROADMAP.md)
- [Security](https://github.com/burman-work/ghravioli/blob/main/docs/SECURITY.md)
- [Distribution](https://github.com/burman-work/ghravioli/blob/main/docs/DISTRIBUTION.md)
- [Release checklist](https://github.com/burman-work/ghravioli/blob/main/docs/RELEASE_CHECKLIST.md)

Rhino® and Grasshopper® are registered trademarks of TLM, Inc., doing business
as Robert McNeel & Associates. ghRavioli is an independent project and is not
affiliated with or endorsed by Robert McNeel & Associates. It bundles no Rhino
or Grasshopper binaries.

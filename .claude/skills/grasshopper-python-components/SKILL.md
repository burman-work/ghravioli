---
name: grasshopper-python-components
description: Use when writing, changing, reviewing or debugging Python 3 components for Rhino 8 Grasshopper. Each component lives as a Python file plus a TOML manifest that the ghravioli CLI builds into a .ghclip archive for pasting onto the canvas, so components stay easy to modify, rearrange and review. Covers port contracts, logs, canvas layout (positions, sliders, toggles, panels), source review and data flow between components.
---

# Grasshopper Python Components

Write Grasshopper Python components as ordinary files so they are easy to
change and lay out. The computation goes in a `.py` file, the interface and
canvas layout go in a sibling `.toml` manifest, and `ghravioli` builds a
`.ghclip` archive that the user pastes onto the canvas. After a change,
rebuild and paste again.

## Workflow

1. Read the project's requirements and any existing component source first.
   When porting code from an older project or a third party, re-implement the
   behaviour unless you have the rights to reuse that code. Don't copy client
   logic, project geometry, XML templates or prose.
2. Put the computation in a Python file and its Grasshopper interface in a
   sibling TOML manifest.
3. Target Python 3.9 for embedded code, even though the toolkit runs on Python
   3.11+. Avoid syntax and standard-library APIs added after Python 3.9.
4. Initialise every output before the main work, and give every component
   exactly one useful human-readable `log` string.
5. Validate, build, inspect the metadata, and review the decoded source and its
   SHA-256.
6. Report what the automated checks showed separately from anything that still
   needs checking by hand in Rhino.

Run `ghravioli --help` for the commands. From a checkout without an install,
use `PYTHONPATH=src python3 -m ghravioli`.

## Keeping components easy to modify and arrange

- Give each component one job. Several small components joined on the canvas
  are easier to change than one large one.
- Make changes in the `.py` file and rebuild. A pasted component holds a copy
  of the code, so edits made in Grasshopper's script editor are lost at the
  next paste.
- Prefer legible canvas names. Grasshopper draws a port's nickname, and the
  default `legible_names = true` writes the full port name there. Keep
  `nickname` for an abbreviated layout, not as the only label.
- Declare `min` and `max` on a numeric input that should get a slider. A
  numeric `default` requires that range, and `int` values must be whole.
  Without a range no slider is generated, which is correct: a slider with an
  invented range can't be set accurately.
- Put `panel = true` on an output that reports a verdict, a count or a
  measurement, so it can be read without wiring anything up. Leave geometry
  outputs bare; a panel on a Brep shows a type name, not a shape.
- Place components with `--at X,Y` (one component) or a graph manifest
  (several). Graphs position components; the user wires them on the canvas.
- Keep the standard `out` console while debugging. It shows standard output
  and uncaught errors, which `log` can't, because `log` is only written when
  the script reaches the end.

## Invariants

- Keep Rhino and Grasshopper geometry on native geometry wires.
- Don't pass a Python dictionary, custom class instance or other
  interpreter-specific state over a wire.
- Pass complex portable state as a versioned JSON string whose consumer checks
  `schema`, `version` and the payload fields.
- Keep the `log` string separate from machine-readable data.
- Declare `item` or `list` access; tree access is unsupported.
- Keep port names unique across inputs and outputs.
- Use only confirmed converter metadata; leave other supported types unhinted.
- Reject absolute paths, path traversal, secrets and unlicensed source.

## Choosing a workflow

- **Embedded archive:** the default and the only implemented workflow. The
  exact source is stored in the generated component.
- **Manual source:** print reviewed source with `ghravioli code` for pasting
  into an existing Python 3 component.
- **Placed graph:** position several components in one archive; automatic
  wiring between them is unsupported.
- **Live-linked source:** an experimental roadmap idea. It isn't implemented
  and has no Rhino test behind it.

## References

- Read [references/authoring.md](references/authoring.md) for Python and TOML.
- Read [references/data-flow.md](references/data-flow.md) for connected values.
- Read [references/workflows.md](references/workflows.md) for CLI and review.
- Read [references/compatibility.md](references/compatibility.md) for status,
  security and Rhino testing.

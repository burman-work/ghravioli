# Canvas presentation

A pasted component should be readable and usable without opening its
manifest. This document covers the four settings that control how a component
looks once pasted, and which parts of them have been checked in Rhino.

All four are booleans at the top level of a component manifest, and all four
default to `true`.

```toml
legible_names = true      # show full port names rather than abbreviations
log_panel = true          # place a panel wired to the log output
input_widgets = true      # place a toggle or slider on eligible inputs
standard_output = true    # keep Grasshopper's own out console
```

## Legible names

Grasshopper draws a port's *nickname*, not its name. A component whose ports
are `width`, `height`, `radius` and `extra_height`, with nicknames `W`, `H`,
`R` and `Xh`, reads `W H R Xh` on the canvas. That's accurate, and hard to use
without the manifest open beside it.

With `legible_names = true`, the archive writes each port's full `name` as its
nickname, and widens both parameter columns to fit the longest label. The
declared `nickname` is retained in the manifest and used when the flag is off,
so an abbreviated layout stays one edit away.

Column widths are computed from label length rather than fixed, so component
width varies. The archive grammar checks the relationship
instead of the number: every parameter in a column shares one width, and the
component width equals `4 + input column + 30 + output column`.

## The `out` console

`out` is not a declared port and does not come from the manifest. It is
Grasshopper's own console for the script component: standard output and any
uncaught error raised while the script runs. It is where a traceback appears,
which makes it the first thing to read when a pasted component does nothing.

It is distinct from `log`. `log` is the component's own summary, written
deliberately by the script and required by the port contract. `out` is whatever
the interpreter emitted, including failures the script never got to report.

`standard_output = false` removes it, and also clears the component's
`UsingStandardOutputParam` flag so Grasshopper does not expect it. Removing it
is reasonable for a finished component and a poor idea while debugging one.

## Output panels

With `log_panel = true` the archive places a panel to the right of the
component and wires it to the `log` output, so a pasted component shows its own
diagnostics without any further action. The panel carries no text of its own;
it displays whatever the component last produced.

Any other output may ask for a panel of its own:

```toml
[[outputs]]
name = "all_closed"
description = "True only if every output curve is closed."
type = "bool"
access = "item"
panel = true
```

Panels stack down the right-hand side, one per requesting output, and never
overlap. `log` is panelled automatically, so declaring `panel = true` on it is
redundant rather than wrong. `panel` is rejected on an input.
Setting `log_panel = false` suppresses only the log panel; other outputs with
`panel = true` still receive their panels.

Without this, a pasted component arrived with its inputs drivable and
everything it reported invisible. An output that carries a verdict rather than
geometry, such as a validity flag, a count or a volume, is only useful if it
can be read without wiring something up first.

Geometry outputs are left bare deliberately. A panel on a Brep shows a type
name, not a shape; those outputs are meant for the next component.

Panel nicknames match their output ports. Other panels also take their
descriptions from their ports; the log panel keeps a fixed description so
existing archives stay inspectable. Inspection cross-checks this metadata
against the wired port, so a panel that claims to read one output while wired
to another is rejected, and no output may drive two panels.

## Input widgets

With `input_widgets = true`, an input earns a stock Grasshopper object wired
into it:

| Declared port | Widget | Condition |
| --- | --- | --- |
| `bool`, `item` access | Boolean Toggle | always; `default` sets its state |
| `float` or `int`, `item` access | Number Slider | only when `min` and `max` are declared |
| anything else | none | |

A slider is generated only when the manifest supplies a range. A slider with
an invented range is worse than none: `step_size = 0.06` on a guessed
`0` to `1` slider can't be set accurately. Declare the range you want:

```toml
[[inputs]]
name = "step_size"
type = "float"
access = "item"
min = 0.0
max = 0.5
default = 0.06
```

`min` and `max` must be declared together, `min` must be smaller than `max`, and
a numeric `default` requires that range and must fall between it. Values for an
`int` slider must be whole numbers. A range on a non-numeric port, or on a
`list` port, is rejected: a single-value widget wired into a list input would
misrepresent what the component receives.

Slider precision follows the range. A domain narrower than one unit gets four
decimal digits rather than three, so a small range stays adjustable.

## Wiring

Companion objects are the only wiring a generated archive contains.
Component-to-component wiring in a graph manifest remains unsupported, and a
`connections` field is still rejected.

Wiring is recorded on the receiving object as a `SourceCount` and a matching
`Source` identity. Inspection enforces both halves: the count must equal the
number of `Source` items, and every referenced identity must belong to an
object the same archive carries. A dangling wire is rejected rather than
pasted.

## Verification status

An archive containing a component plus four Number Sliders, four Boolean
Toggles and a wired Panel pastes onto a Grasshopper canvas on Rhino
8.31.26126.13431 under Windows 10 19045. The object identifiers and container
shapes are therefore accepted by Grasshopper, not just plausible. The
full record, including hashes, is in
[RHINO_ACCEPTANCE.md](RHINO_ACCEPTANCE.md).

| Element | Status |
| --- | --- |
| Legible nicknames and column widths | Paste confirmed, Rhino 8.31 / Windows 10 |
| `standard_output` toggle | Generated; uses the existing standard output parameter |
| Panel, Boolean Toggle, Number Slider objects | Paste confirmed, Rhino 8.31 / Windows 10 |
| Per-companion configuration once pasted | **Not yet itemised** |
| macOS | Not tested |

A successful paste isn't a full compatibility claim. Grasshopper ignores keys
it doesn't recognise, so a companion can paste cleanly and still hold a
default it was never given. What remains unconfirmed is that each slider
carries its declared domain and value, each toggle its declared state, and each
wire is live rather than just present. Those rows in
[RHINO_ACCEPTANCE.md](RHINO_ACCEPTANCE.md) are still unticked, and no row may be
ticked without the exact Rhino, Grasshopper and OS versions the protocol
requires.

The companion object identifiers live in one table in
`src/ghravioli/constants.py`, and each container shape is written by a single
function in `src/ghravioli/archive.py`, so a correction found by further
testing is a small, local change.

If a pasted archive fails, isolate the cause first: set `input_widgets =
false` and `log_panel = false`, rebuild and paste again. If that succeeds, the
component itself is sound and the fault is in a companion. Record the result in
[RHINO_ACCEPTANCE.md](RHINO_ACCEPTANCE.md).

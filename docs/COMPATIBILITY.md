# Compatibility

The automated tests show that generated archives are structurally correct.
Rhino testing is partial: archives paste onto a Grasshopper canvas on Rhino
8.31.26126.13431 under Windows 10, as recorded in
[RHINO_ACCEPTANCE.md](RHINO_ACCEPTANCE.md). That is one row of the acceptance
matrix, not the whole matrix.

| Capability | Status |
| --- | --- |
| Builder/CLI | Python 3.11 to 3.14 on macOS, Windows, and Linux in CI |
| Embedded component source | Python 3.9 grammar target |
| Clipboard adapter | `pbcopy`, PowerShell, `wl-copy`, or `xclip`; archive fallback first |
| Rhino Grasshopper paste, Windows | Confirmed on Rhino 8.31.26126.13431, Windows 10 |
| Rhino Grasshopper paste, macOS | Pending manual verification |
| `item` and `list` access | Structurally generated; manual Rhino verification pending |
| Tree access | Unsupported |
| Multi-component placement | Structurally generated; no automatic wiring between components |
| Legible port nicknames and column widths | Paste confirmed on Rhino 8.31 / Windows 10 |
| Optional standard `out` console | Structurally generated; manual Rhino verification pending |
| Log panel, boolean toggle, number slider | Paste confirmed on Rhino 8.31 / Windows 10; per-companion configuration not yet itemised |
| Companion wiring | Generated and checked for resolvable targets; live behaviour in Rhino not yet itemised |
| Live-linked source | Experimental roadmap item, not implemented |

The provisional minimum is Rhino 8.14 with its Python 3 Script component. It's
a conservative target until the versioned tests in
[RHINO_ACCEPTANCE.md](RHINO_ACCEPTANCE.md) are done, not a claim that every
Rhino build from 8.14 on has been tested.

Converter metadata exists for `str`, `float`, `bool`, `point`, and `brep`;
their behaviour in Rhino is still to be confirmed. Other accepted type tokens
are deliberately left unhinted.

Automatic wiring between components is rejected by schema version 1. The only
wiring a generated archive contains connects a component to the companion
objects it places itself; see [canvas presentation](CANVAS.md). The
live-linked workflow is experimental and isn't part of 0.1.0a2.

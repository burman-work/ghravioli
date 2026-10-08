# Compatibility and testing

## Alpha status

| Capability | Status |
| --- | --- |
| Archive generation | Experimental; covered by automated structural tests |
| Target | Rhino 8.14+ (provisional), Python 3.9 embedded source |
| Paste onto the canvas | Confirmed on Rhino 8.31, Windows 10; macOS not tested |
| Sliders, toggles and log panel | Paste confirmed on Rhino 8.31, Windows 10; per-object settings not yet checked |
| `item` and `list` access | Generated; not yet checked in Rhino |
| Tree access | Unsupported |
| Multi-component positioning | Generated; not yet checked in Rhino |
| Automatic wiring between components | Unsupported |
| Live-linked source | Experimental roadmap item, not implemented |

Converter metadata exists for `str`, `float`, `bool`, `point` and `brep`.
Other supported types stay unhinted. Don't claim more than the results recorded
in ghRavioli's `docs/RHINO_ACCEPTANCE.md`.

## Security and manual testing

Archives contain executable Python, and Base64 doesn't protect it. Review
untrusted archives with the safe terminal view from `inspect --source` and the
JSON-quoted `inspect --sha256` records, or extract them to an empty directory.
Treat `code` as an exact machine stream and redirect it when the source is
untrusted. Source keeps its own copyright and licence, and redistributing it
needs the rights to do so.

A compatibility claim for a platform needs the manual Rhino test in
`docs/RHINO_ACCEPTANCE.md`: paste the archive twice, check the ports and native
geometry, try failure inputs, save, reopen and recompute, and compare the
semantic fields with a neutral Rhino-generated Python component.

If clipboard integration is unavailable, keep the generated `.ghclip` and copy
it on the Rhino machine. Always report structural checks separately from manual
Rhino results.

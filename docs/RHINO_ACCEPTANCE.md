# Rhino acceptance matrix

The provisional floor for this alpha is Rhino 8.14 with Grasshopper's Python 3
Script component. Record the exact Rhino, Grasshopper, Python component and OS
versions, and don't generalise beyond the rows tested.

This is a manual protocol. CI checks the builder and the archive structure,
but it can't establish Rhino, Grasshopper or clipboard compatibility. Start by
running:

```bash
python3 scripts/prepare_rhino_acceptance.py --output .audit/rhino-0.1.0a2
```

The bundle lands in the ignored `.audit/` folder. Verify its `manifest.json`
hashes before and after moving it between machines.

## Neutral reference

Before testing generated output, create a neutral Rhino-generated Python 3
component with equivalent ports and source. Copy it from Grasshopper and retain
its `.ghclip` only in the private evidence bundle. Compare semantic XML fields,
not volatile instance/document UUIDs.

## Matrix

Run every case on macOS and Windows at the claimed minimum version and the
newest available Rhino 8 service release.

| Case | macOS minimum | macOS current | Windows minimum | Windows current |
| --- | --- | --- | --- | --- |
| Scalar/string/bool hints | [ ] | [ ] | [ ] | [ ] |
| Point3d input/output | [ ] | [ ] | [ ] | [ ] |
| Brep input/output | [ ] | [ ] | [ ] | [ ] |
| Optional input | [ ] | [ ] | [ ] | [ ] |
| Item and list access | [ ] | [ ] | [ ] | [ ] |
| Two-component placement | [ ] | [ ] | [ ] | [ ] |
| Clipboard fallback | [ ] | [ ] | [ ] | [ ] |
| Archive pastes onto a clean canvas | [ ] | [ ] | [ ] | [x] |
| Legible port nicknames and column widths | [ ] | [ ] | [ ] | [ ] |
| Component with the standard out console removed | [ ] | [ ] | [ ] | [ ] |
| Log panel object, wired and updating | [ ] | [ ] | [ ] | [ ] |
| Boolean toggle object, wired and carrying its default | [ ] | [ ] | [ ] | [ ] |
| Number slider object, wired with its declared range | [ ] | [ ] | [ ] | [ ] |
| Unicode component names, descriptions, and source | [ ] | [ ] | [ ] | [ ] |

For each cell:

1. Build from a clean checkout and record the command plus source SHA-256 and
   exact Rhino, Grasshopper, Python component, OS, and service-release versions.
2. Inspect embedded source before execution. Exercise Unicode names,
   descriptions, string values, comments, and source text.
3. Paste the same archive twice on a clean canvas and verify fresh component
   instance identities, names, positions, and no unintended connections.
4. Check every port name, nickname, order, required and optional flag, item and list
   access, and expected converter behaviour for str, float, bool, point, and brep.
5. Run valid, null, malformed, and empty-list inputs plus repeated recompute.
6. Confirm safe initialised outputs and one useful `log` value.
7. For geometry, confirm the Grasshopper value remains native (including a
   `Point3d` case) rather than becoming JSON or an opaque Python dictionary.
8. Save, close, reopen, and recompute the definition.
9. Compare semantic fields with the neutral Rhino-generated reference.
10. Attach screenshots, console/log output, archive/source hashes, and defects.

For a companion row, isolate the cause first. Rebuild with `input_widgets =
false` and `log_panel = false`. If that archive pastes cleanly, the fault is in
a companion object rather than the component, and the identifier and container
shape recorded in `src/ghravioli/constants.py` and `src/ghravioli/archive.py`
are the first things to correct against a Rhino-generated reference.

Any crash, unexpected prompt, corrupt reopen, port mismatch, or code mismatch
blocks the compatibility claim for that row. Structural tests alone do not
complete this matrix.

## Recorded results

Only the narrow result below has been established. Every other cell in the
matrix is still pending: none has been through the ten-step protocol above.

### Windows, current service release: archive pastes onto a clean canvas

| | |
| --- | --- |
| Result | Pass |
| Date | 2026-08-23 |
| Reviewer | Repository maintainer |
| Rhino | 8.31.26126.13431 |
| Grasshopper | 8.31.26126.13431 (plug-in version 1.0.0008) |
| Script component | Python 3 Script, `ScriptComponentVersion` 3 |
| OS | Windows 10 Home, 10.0.19045 build 19045 |
| Builder | ghRavioli 0.1.0a2 on CPython 3.12.8 |

Archive under test: a test component with nine inputs and twelve outputs. The
archive carries ten objects: the Python 3 Script component, four Number
Sliders, four Boolean Toggles and one Panel wired to the `log` output.

```
ghravioli build <manifest> --output <archive>.ghclip
ghravioli copy <archive>.ghclip
```

| | |
| --- | --- |
| Embedded source SHA-256 | `4a06c10c5d5e13f75b174bcf7d63c67a31f29ec24c5b8d5fcac11140d91eeaf8` |
| Archive SHA-256 | `f422d42043e8cf677215eb06c98a300e725744cdbb96275ce1613cdc0565bd71` |
| Clipboard SHA-256 | `f422d42043e8cf677215eb06c98a300e725744cdbb96275ce1613cdc0565bd71` |
| Clipboard length | 137,815 characters, no carriage returns introduced |

Observed: the archive pastes onto a clean Grasshopper canvas and the component
appears with its declared ports. An earlier archive of the same component
without companion objects also pasted successfully.

This result is limited. Grasshopper ignores archive keys it doesn't
recognise, so an object can paste cleanly while holding a default it was never
given. The test says nothing about whether each slider carries its declared
domain and value, whether each toggle carries its declared state, whether each
wire is live rather than just present, whether recompute, save, reopen or
malformed input behave correctly, or how any of it compares with a
Rhino-generated reference. Those checks are still pending.

## Clipboard byte and text checks

Do not assume the clipboard worked just because the paste command returns zero.
Record an archive SHA-256, copy it, recover the clipboard text without changing
line endings, encode it as UTF-8, and compare the clipboard hash with the archive
hash before pasting.

On macOS, test the native `pbcopy` path and recover text with `pbpaste`:

```bash
shasum -a 256 .audit/rhino-0.1.0a2/archives/scale-points.ghclip
pbpaste > clipboard-recovered.ghclip
shasum -a 256 clipboard-recovered.ghclip
```

On Windows, use a command compatible with both stock Windows PowerShell 5.1 and
PowerShell 7. It writes the recovered text through .NET with an explicit
BOM-free UTF-8 encoder:

```powershell
Get-FileHash .audit\rhino-0.1.0a2\archives\scale-points.ghclip -Algorithm SHA256
$text = Get-Clipboard -Raw
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText((Join-Path (Get-Location) "clipboard-recovered.ghclip"), $text, $utf8NoBom)
Get-FileHash clipboard-recovered.ghclip -Algorithm SHA256
```

The clipboard adapter prefers `pwsh.exe`/`pwsh` and falls back to
`powershell.exe`/`powershell`. In both cases it sets standard-input decoding to
BOM-free UTF-8, reads one complete string with `Console.In.ReadToEnd()`, and
passes that string to `Set-Clipboard`.

If the platform API normalises text, record the byte mismatch and also
compare decoded Unicode text exactly. Never mark the clipboard row passed
without explaining which comparison was used.

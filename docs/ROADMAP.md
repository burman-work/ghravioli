# Roadmap

## 0.1.0a2: experimental embedded archives

- Closed component and graph manifests with a Python 3.9 target.
- Atomic `.ghclip` generation with fresh UUID4 instance identities.
- Validation, inspection, source hashing/review, extraction, and clipboard copy.
- Native geometry and versioned-JSON examples.
- Cross-agent skill discovery for Codex and Claude Code.
- Canvas presentation: legible names, log and output panels, toggles and
  sliders, and `--at` placement.
- Wheel and source-distribution builds in CI.
- Pending: most of the Rhino acceptance matrix (only the Windows paste row has
  passed).

## 0.1.x: acceptance and hardening

- Record exact Rhino, Grasshopper, OS, and Python component versions.
- Add only newly generated project-neutral acceptance fixtures.
- Expand converter support when each token has Rhino evidence.
- Add resource limits only with adversarial regression tests.

## 0.2: experimental live-linked source

Research a separate workflow in which a component loads a local Python file.
It must show its source root, reload action, missing-file state and errors, and
must not promise hot reload until that's been tested in Rhino. Embedded
archives and manual source review stay available as fallbacks.

Graph connections and automatic wiring are separate research items and must not
enter the stable schema without versioned Rhino compatibility evidence.

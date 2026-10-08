# Repository instructions

## Purpose

ghRavioli is an agent skill and a Python toolkit. Agents write Rhino 8
Grasshopper Python 3 components as a Python file plus a TOML manifest, and the
toolkit builds `.ghclip` clipboard archives from them that can be pasted onto
the canvas.

Keep the repository project-neutral. Do not add project-specific component
code, client data, secrets, user-specific paths, or source you don't have the
right to redistribute. Examples must be generic.

The builder and tests run on Python 3.11 or newer. Code embedded in components
targets Python 3.9: avoid syntax and standard-library APIs added after Python
3.9. An archive can place several components but doesn't wire them to each
other. The only wires a generated archive contains connect a component to the
companion objects (panels, toggles, sliders) it places itself. Live-linked
source is a roadmap item.

## Working commands

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m compileall -q src scripts tests examples
PYTHONPATH=src python3 -m ghravioli --help
python3 scripts/sync_agent_skills.py --check
```

## Change rules

- Work test-first: add a focused failing test, implement the behaviour, then
  run the focused and full suites.
- Keep computation in `.py` files and interfaces in closed-schema `.toml`
  manifests.
- Every component declares exactly one `log` string output.
- Keep Rhino geometry native and pass complex state as versioned JSON text.
  Don't put Python dictionaries or custom objects on wires.
- Only emit a wire to a companion object placed by the same archive. Every
  `Source` must resolve to an object in the archive, and `SourceCount` must
  match the number of `Source` items beside it.
- Resolve source beneath its manifest, and graph children beneath their graph.
- Treat archives as untrusted input when inspecting or extracting them.
- Write archives atomically and never overwrite a manifest or source input.
- Generated `.ghclip` files are build artifacts; don't commit them.
- Don't add `Co-Authored-By` or other AI attribution trailers to commits.

## Skills and documentation

Edit `skills/grasshopper-python-components` (the canonical copy), then run
`python3 scripts/sync_agent_skills.py` and commit both discovery copies. Keep
`AGENTS.md` and `CLAUDE.md` byte-identical. When behaviour or Rhino test
results change, update the README and docs to match.

## Before finishing

Run the full suite, the synchronisation check, CLI smoke tests, the package
build, the source-distribution tests, the compile check,
`python3 scripts/audit_repository.py --tree` and `git diff --check`. Don't
claim Rhino compatibility beyond the results recorded in
`docs/RHINO_ACCEPTANCE.md`; a new claim needs a manual Rhino 8 test on the
platform concerned.

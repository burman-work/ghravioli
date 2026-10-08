# Workflows

Use `ghravioli --help`. From a checkout, prefix commands with
`PYTHONPATH=src python3 -m ghravioli`.

## Embedded archive

```bash
ghravioli validate component.toml
ghravioli build component.toml --output component.ghclip
ghravioli inspect component.ghclip --json
ghravioli inspect component.ghclip --sha256
ghravioli inspect component.ghclip --source
ghravioli copy component.toml
```

Output must end in `.ghclip` and cannot replace a manifest or source input.
`copy` creates the fallback archive before attempting the system clipboard.
Review executable source before pasting an archive received from elsewhere.

## Source review and extraction

```bash
ghravioli code component.toml
ghravioli code component.ghclip
ghravioli code graph.ghclip --component 2
ghravioli extract component.ghclip --output reviewed-source
```

Use `inspect --source` as the safe terminal viewer for untrusted archives. It
visibly escapes terminal and dangerous Unicode formatting controls and quotes
component names. `code` is an exact machine stream: it prints source and
nothing else. Redirect it to a file or pipe, or use `extract`, rather than
displaying untrusted exact source in a terminal. `code` refuses unsafe direct
TTY output unless `--unsafe-terminal` is explicit.

A multi-component archive requires the stable one-based `--component INDEX`
selector. `extract` validates first, writes each component's exact source to a
separate file, and accepts only a missing or empty directory.

## Placed graph

```toml
kind = "graph"
schema_version = 1
id = "example-pipeline"
name = "Example Pipeline"

[[components]]
manifest = "prepare/component.toml"
x = 0
y = 0

[[components]]
manifest = "consume/component.toml"
x = 260
y = 0
```

Paths are relative to the graph manifest and stay inside its directory. Graphs
position components but contain no source connections; automatic wiring is
unsupported.

## Live-linked source

Do not present live-linked source as a current feature. If researched later,
make the source root, file, reload action, missing-file state, and errors visible
and require new Rhino evidence. Preserve embedded and manual workflows as
fallbacks.

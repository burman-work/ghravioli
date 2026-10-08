# Design

## Boundary

ghRavioli lets an agent or a developer write component Python outside
Grasshopper, declare the component's interface in TOML, and generate a
self-contained Rhino 8 Grasshopper Python 3 clipboard archive. Because the code
and interface live in ordinary files, they can be edited, diffed, reviewed and
rebuilt like any other code.

1. A Python file owns computation.
2. A closed TOML manifest owns the interface.
3. Validation checks target, syntax, sizes, paths, fields, ports, and graphs.
4. The builder embeds exact UTF-8 source as Base64 in generated XML.
5. The inspector validates untrusted archives and exposes source and hashes.
6. The CLI validates, builds, inspects, copies, prints, and extracts source.

Production archives get fresh UUID4 instance identities, so output isn't
byte-identical between builds by default. Tests inject a sequence provider for
reproducible fixtures.

Multiple components may be positioned in one archive. Automatic wiring and
live-linked source are outside the alpha boundary.

## Data flow

- Every component has a human-readable string output named `log`.
- Native Grasshopper values and Rhino geometry use native wires.
- Dictionaries and custom Python objects do not cross component boundaries.
- Complex portable state uses a versioned JSON string envelope.
- Only accepted converter metadata is emitted; unconfirmed types are unhinted.

## Independent implementation

ghRavioli is an independent implementation based on documented behaviour and
functional interoperability facts. The Grasshopper object and parameter
identifiers it writes are recorded as constants with comments in
`src/ghravioli/constants.py`. No Rhino or Grasshopper binary is included.

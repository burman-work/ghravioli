# Security Policy

ghRavioli `0.1.0a2` is an experimental alpha released under the MIT licence. It
is provided as is, with no support, warranty, or promise of fixes or updates.

## Reporting a vulnerability

If you find a security problem, you can report it through GitHub's
private vulnerability reporting on the repository's **Security** tab. Don't
open a public issue for an unpatched vulnerability, and don't include secrets
or private material in a report. Reports are read when time allows; there is no
commitment to respond or to release a fix.

## Executable archives

A `.ghclip` generated or inspected by ghRavioli can contain executable Python.
Base64 is encoding, not encryption. Review the embedded source and its SHA-256
hash before pasting an archive you didn't build yourself. The inspector checks
that an archive matches the format ghRavioli generates; it is not a malware
scanner or sandbox.

ghRavioli is an independent project and is not affiliated with or endorsed by
Robert McNeel & Associates.

# Release checklist

A reusable template. Copy it for each release and record the results in the
release notes; don't tick the boxes here.

## Automated checks

- [ ] Full unit suite passes on every Python and OS row in CI.
- [ ] Compile check passes for source, scripts, tests, and examples.
- [ ] Canonical and discovery skill copies are byte-identical.
- [ ] Wheel and source distribution build successfully.
- [ ] Tests pass from the extracted source distribution.
- [ ] Wheel installs in a clean environment and CLI smoke tests pass.
- [ ] `python scripts/audit_repository.py --tree` passes.
- [ ] Documentation TOML examples validate as manifests.
- [ ] `git diff --check` reports no whitespace errors.

## Content checks

- [ ] A history-aware scan (`audit_repository.py --history
      --forbid-coauthor-trailers` with a private deny file) finds no secrets,
      personal paths, project names or attribution trailers.
- [ ] Examples and prose are original or licensed for redistribution.
- [ ] Trademark attribution and non-affiliation wording are present.

## Compatibility claims

- [ ] Every compatibility claim in the README and docs matches a passed row in
      `RHINO_ACCEPTANCE.md`.
- [ ] Clipboard fallback is verified on each platform claimed.
- [ ] The version stays an alpha until the acceptance matrix supports more.

## Publishing

- [ ] Build the wheel and source distribution from the tagged commit.
- [ ] Verify the artifact hashes and attach them to the GitHub release.
- [ ] Publish to GitHub, the Python package index, and any skill directory as
      separate steps.

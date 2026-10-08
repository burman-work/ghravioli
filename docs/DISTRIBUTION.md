# Distribution

## Python package

A wheel install provides the `ghravioli` command and the small public Python
API listed in the README. The runtime package uses only the standard library.
Internal modules and functions may change during the alpha.

The source distribution also contains repository documentation,
examples, templates, tests, scripts, CI configuration, and all three skill
copies so the extracted artifact can run the same verification suite.

## Repository and skill

A GitHub clone is the complete distribution. The canonical skill is
`skills/grasshopper-python-components`; copy that folder into your agent's
skill location to use it in another project. A package install doesn't set up
the skill for Codex, Claude Code or any other agent.

## Release channels

0.1.0a2 is an experimental alpha, distributed from GitHub. It isn't on PyPI
yet. A package upload or a skill-directory submission goes through
`RELEASE_CHECKLIST.md`, and each is a separate decision.

The project name and description must keep the non-affiliation statement and
must not imply an official McNeel product.

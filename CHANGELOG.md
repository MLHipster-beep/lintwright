# Changelog

All notable changes are recorded here.  The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) for the tool itself;
the Debian revision is managed separately in `debian/changelog`.

## [0.3.0] - 2026-10-18

### Added

- 37 rules across five areas: control, rules/compat, changelog, copyright and
  install layout.
- `--format json` with a stable schema for CI annotations.
- `--only` / `--skip` tag filtering, and `--fail-on` threshold selection.
- `--statistics` per-tag counts.
- autopkgtest smoke test, DEP-5 copyright, man page and `debian/watch`.
- Strict-mode snap recipe in `snapcraft.yaml`.

### Packaging

- `Build-Depends` now includes `pybuild-plugin-pyproject`; without it `pybuild`
  refuses to configure a PEP 517 project.
- `debian/lintwright.manpages` was missing, so the binary shipped without a man
  page and lintian reported `no-manual-page`. The rule set did not catch this
  itself — see below.

### Known gap

- `manpage-missing` only inspects `debian/*.install`, so a console script
  installed by `pybuild` is invisible to it. That is exactly how this package
  shipped without a man page on the first build, which is a fair demonstration
  that a linter is not a substitute for the real one.

### Design notes

- Finding severities are registered with the rule rather than at the call
  site, so a rule cannot silently change its own importance between code paths.
- Parsers are separate from rules, which is what makes the rule tests fast:
  most cases build a four-file tree in a temporary directory and assert on
  tags, not on output formatting.

## [0.2.0] - 2026-10-11

### Added

- Changelog parser with explicit problems for missing signatures and
  unparseable dates.
- debhelper compat detection from both `Build-Depends` and `debian/compat`,
  including the conflict case.

### Fixed

- Continuation lines are no longer trimmed, so description bodies keep the
  leading space Debian expects.

## [0.1.0] - 2026-10-05

### Added

- Initial control-file parser and ten rules.
- Text reporter with `path:line: severity: message` output.

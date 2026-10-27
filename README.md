# lintwright

**Static analysis for Debian source packages.** 37 rules over `debian/`, zero
runtime dependencies, JSON output, and a rule set that separates "this will
fail to build" from "a reviewer will ask you to change this".

```
$ lintwright check examples/broken
debian/changelog:1: error: changelog names 'demo-app', control names 'demo' [ changelog-package-mismatch ]
debian/control:4: error: Maintainer 'demo@example.com' is not of the form 'Name <email>' [ control-invalid-maintainer ]
debian/demo.install:1: error: /usr/local is reserved for the administrator (FHS); install under /usr [ install-path-usr-local ]
debian/rules:1: error: file is not executable (chmod +x) [ rules-not-executable ]
debian/source/format:1: warning: format 1.0 cannot carry patches; use '3.0 (quilt)' [ source-format-legacy ]
```

## Why this exists

`lintian` runs after a successful build. By then you have already paid for the
build, and on a slow architecture that is twenty minutes. The failures that
cost the most time in practice are not compiler errors — they are policy
details that are cheap to check statically and expensive to discover late:

- a changelog trailer with one space before the dash, rejected by `dput`
- no `debian/source/format`, so `dpkg-source` silently picks the legacy 1.0
  format and your patches stop being tracked
- `debhelper-compat` declared in both `Build-Depends` and `debian/compat`,
  which `dh` refuses
- an install path under `/usr/local`, which the FHS reserves for the
  administrator and which `lintian` flags as an error
- a `postinst` without `set -e`, where a failing command is ignored and dpkg
  records a successful install anyway

`lintwright` answers "will this tree survive review and upload" in
milliseconds, before the build starts, and gives every answer a stable tag so
a pipeline can suppress exactly one rule.

## Install

From source (no dependencies beyond Python 3.10+):

```bash
git clone https://github.com/MLHipster-beep/lintwright
cd lintwright
python3 -m pip install .
lintwright --version
```

As a Debian package, from the packaging in this repository:

```bash
sudo apt install debhelper dh-python python3-all python3-setuptools
dpkg-buildpackage -us -uc -b
sudo apt install ../lintwright_0.3.0-1_all.deb
lintwright --help
```

The snap recipe is in `snapcraft.yaml`. It uses strict confinement; the tool
only needs read access to the tree you point it at, so `home` is the only plug.

## Usage

```bash
lintwright check [PATH] [--format text|json] [--fail-on error|warning|info|never]
                        [--only TAG]... [--skip TAG]... [--statistics]
lintwright rules [--format text|json]
```

Exit status is `0` when nothing at or above the threshold was found, `1` when
something was, and `2` for usage errors — so `lintwright check .` works as a
pre-commit hook without a wrapper.

JSON is the CI integration surface. It is deliberately flat, one object per
finding, with the tag as a first-class field:

```json
{
  "tool": "lintwright",
  "version": "0.3.0",
  "summary": {"error": 1, "warning": 2, "info": 1},
  "findings": [
    {"tag": "source-format-legacy", "severity": "warning",
     "path": "debian/source/format", "line": 1,
     "message": "format 1.0 cannot carry patches; use '3.0 (quilt)'"}
  ]
}
```

## Rule set

| Area | Tags |
|---|---|
| Control | `control-missing`, `control-parse-error`, `control-missing-source-stanza`, `control-missing-field`, `control-missing-binary-stanza`, `control-binary-missing-field`, `control-invalid-maintainer`, `control-invalid-priority`, `control-description`, `control-package-name-invalid`, `control-duplicate-package`, `control-build-depends-no-debhelper` |
| Build | `rules-missing`, `rules-shebang`, `rules-not-executable`, `debhelper-compat-missing`, `debhelper-compat-conflict`, `debhelper-compat-old`, `source-format-missing`, `source-format-legacy` |
| Changelog | `changelog-missing`, `changelog-parse-error`, `changelog-invalid-urgency`, `changelog-unreleased`, `changelog-maintainer-mismatch`, `changelog-package-mismatch`, `changelog-no-trailing-newline`, `changelog-signature`, `changelog-version-native` |
| Licensing | `copyright-missing`, `copyright-format`, `copyright-license` |
| Layout | `install-path-usr-local`, `maintainer-script-not-executable`, `maintainer-script-no-set-e`, `manpage-missing`, `autopkgtest-missing`, `watch-missing` |

`lintwright rules` prints the same list with severities and summaries.

`examples/broken/` is a deliberately broken package that trips twelve rules.
It is the fixture used for the screenshot above, and it is the fastest way to
see the output without breaking your own tree:

```bash
lintwright check examples/broken
```

## Design decisions

**Parsers are separate from rules.** `deb822.py` knows about fields and
continuation lines; `control.py` and `changelog.py` know what the artefacts
mean; `rules.py` decides what is wrong. That split is what makes the test
suite fast — most cases build a four-file tree in a temporary directory and
assert on tags, not on formatted output.

**Rules are generators that never raise.** A diagnostic tool that crashes on
the file it is meant to diagnose is worse than no tool. Missing files,
unparseable control data and absent changelog entries are all reported as
findings by a different rule, so the rule that needs the artefact can simply
return.

**Line numbers are part of the contract.** A finding that says "somewhere in
debian/control" is not actionable. Every field's source line is retained by
the parser, including fields whose values span lines, which is why the
Description rules point at the field start rather than at the file.

**Severity lives with the rule, not with the call.** `finding()` defaults to
the severity registered on the rule, so a rule cannot quietly become more or
less important on one code path than another. Two rules deliberately emit at a
lower severity for a softer variant (`debhelper-compat-old` for levels 10–12),
and that override is explicit at the call site.

**No third-party dependencies.** Debian main requires every dependency to be
packaged, and a checker that drags in a YAML parser for one config file is a
worse deal than one that does not. Everything here is `argparse`, `re`,
`json`, `email.utils`.

**It is not a replacement for lintian.** lintian checks the binary package and
the archive; this checks the source tree, and it checks a smaller set of things
on purpose. The value is speed and the absence of a build. Where the two
overlap, lintian is authoritative.

## Testing

```bash
make test
```

The suite uses `unittest` from the standard library — 57 tests, no pytest
required, which keeps the Debian build dependency list to `dh-python` and
`python3-setuptools`.

Two of those tests are worth calling out:

- `test_repository_packages_itself_cleanly` runs the full rule set against this
  repository's own `debian/` directory and asserts zero findings. The tool is
  packaged with itself, so a rule that would reject the tool is a test failure.
- `debian/tests/smoke` is an autopkgtest that installs the built package in a
  clean environment, runs it against a deliberately broken tree, and asserts
  the exit status is `1`. That catches packaging mistakes that unit tests
  cannot, such as a module missing from the installed location.

## Packaging notes

- `debian/rules` is three lines plus a test override; the `dh` sequencer does
  the rest, and the override exists so `dpkg-buildpackage` runs the same suite
  as `make test`.
- `debian/copyright` is DEP-5, because licence review should be mechanical.
- `debian/watch` points at GitHub tags, so `uscan` notices new releases.
- `debian/tests/control` declares the smoke test with `Depends: @`, which is
  the autopkgtest idiom for "the package under test".

## Limits

- No archive or binary-package inspection; that is lintian's job.
- No `debian/patches` validation yet — an empty `series` file is the most
  common quilt mistake and is not detected.
- Rules are policy-shaped, not policy-complete. `Standards-Version` is checked
  for presence, not for the current value.
- `manpage-missing` only sees programs listed in `debian/*.install`. A console
  script installed by `pybuild` or `dh-python` is invisible to it, which is how
  this very package shipped without a man page on its first build — lintian
  caught it, as it should.

## Licence

MIT. See `LICENSE`.

"""The rule set.

Each rule is a generator of findings.  Rules never raise on malformed input:
a tool that crashes on the file it is meant to diagnose is worse than no tool,
so every rule guards for the artefact being absent or unparsed and lets a
different rule report that absence.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .control import debhelper_compat
from .model import RULES, Rule, Severity, finding, rule
from .source import SourceContext

REQUIRED_SOURCE_FIELDS = ("Source", "Maintainer", "Build-Depends")
RECOMMENDED_SOURCE_FIELDS = ("Section", "Priority", "Standards-Version")
REQUIRED_BINARY_FIELDS = ("Package", "Architecture", "Description")

VALID_PRIORITIES = {"required", "important", "standard", "optional", "extra"}
VALID_URGENCIES = {"low", "medium", "high", "emergency", "critical"}
VALID_FORMATS = {"3.0 (quilt)", "3.0 (native)", "1.0"}

PACKAGE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]+$")
MAINTAINER_RE = re.compile(r"^[^<>]+ <[^<>\s]+@[^<>\s]+>$")
SYNOPSIS_LIMIT = 80


def _lines(path: Path):
    """Yield (line number, text) for a file, tolerating undecodable bytes."""

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for number, line in enumerate(text.splitlines(), start=1):
        yield number, line


# ---------------------------------------------------------------- control ---


@rule("control-missing", Severity.ERROR, "debian/control must exist")
def check_control_present(ctx: SourceContext):
    if not ctx.exists("debian", "control"):
        yield finding("control-missing", "debian/control", 1, "no control file: dpkg cannot build this tree")


@rule("control-missing-source-stanza", Severity.ERROR, "control needs a source stanza")
def check_source_stanza(ctx: SourceContext):
    if ctx.control is not None and ctx.control.source is None:
        yield finding(
            "control-missing-source-stanza",
            "debian/control",
            1,
            "first paragraph has no 'Source:' field, so there is no source stanza",
        )


@rule("control-missing-field", Severity.ERROR, "required control fields must be present")
def check_control_fields(ctx: SourceContext):
    if ctx.control is None or ctx.control.source is None:
        return
    source = ctx.control.source
    for name in REQUIRED_SOURCE_FIELDS:
        if not source.has(name):
            yield finding("control-missing-field", "debian/control", source.start_line, f"source stanza is missing {name}")
    for name in RECOMMENDED_SOURCE_FIELDS:
        if not source.has(name):
            yield finding(
                "control-missing-field",
                "debian/control",
                source.start_line,
                f"source stanza is missing {name}",
                severity=Severity.WARNING,
            )


@rule("control-missing-binary-stanza", Severity.ERROR, "at least one binary package is required")
def check_binary_stanza(ctx: SourceContext):
    if ctx.control is None or not ctx.control.binaries:
        yield finding("control-missing-binary-stanza", "debian/control", 1, "no binary stanza: nothing would be built")


@rule("control-binary-missing-field", Severity.ERROR, "binary stanzas need Package, Architecture and Description")
def check_binary_fields(ctx: SourceContext):
    if ctx.control is None:
        return
    for stanza in ctx.control.binaries:
        name = stanza.get("Package") or "<unnamed>"
        for field in REQUIRED_BINARY_FIELDS:
            if not stanza.has(field):
                yield finding(
                    "control-binary-missing-field",
                    "debian/control",
                    stanza.start_line,
                    f"binary stanza {name!r} is missing {field}",
                )


@rule("control-invalid-maintainer", Severity.ERROR, "Maintainer must be 'Name <email>'")
def check_maintainer(ctx: SourceContext):
    if ctx.control is None or ctx.control.source is None:
        return
    source = ctx.control.source
    if not source.has("Maintainer"):
        return
    value = source.get("Maintainer")
    if MAINTAINER_RE.match(value) is None:
        yield finding(
            "control-invalid-maintainer",
            "debian/control",
            source.line_of("Maintainer"),
            f"Maintainer {value!r} is not of the form 'Name <email>'",
        )


@rule("control-invalid-priority", Severity.WARNING, "Priority must be a known value")
def check_priority(ctx: SourceContext):
    if ctx.control is None or ctx.control.source is None:
        return
    source = ctx.control.source
    value = source.get("Priority")
    if value and value not in VALID_PRIORITIES:
        yield finding(
            "control-invalid-priority",
            "debian/control",
            source.line_of("Priority"),
            f"Priority {value!r} is not one of {', '.join(sorted(VALID_PRIORITIES))}",
        )


@rule("control-description", Severity.WARNING, "Description needs a short synopsis and an extended body")
def check_description(ctx: SourceContext):
    if ctx.control is None:
        return
    for stanza in ctx.control.binaries:
        if not stanza.has("Description"):
            continue
        value = stanza.get("Description")
        synopsis, _, body = value.partition("\n")
        line = stanza.line_of("Description")
        if len(synopsis) > SYNOPSIS_LIMIT:
            yield finding(
                "control-description",
                "debian/control",
                line,
                f"synopsis is {len(synopsis)} characters; keep it under {SYNOPSIS_LIMIT}",
            )
        if not body.strip():
            yield finding(
                "control-description",
                "debian/control",
                line,
                "extended description is empty; add a blank line and an indented paragraph",
            )


@rule("control-package-name-invalid", Severity.ERROR, "package names are lower-case and start alphanumeric")
def check_package_names(ctx: SourceContext):
    if ctx.control is None:
        return
    for stanza in ctx.control.binaries:
        name = stanza.get("Package")
        if name and PACKAGE_NAME_RE.match(name) is None:
            yield finding(
                "control-package-name-invalid",
                "debian/control",
                stanza.line_of("Package"),
                f"{name!r} is not a valid Debian package name",
            )


@rule("control-duplicate-package", Severity.ERROR, "one stanza per binary package")
def check_duplicate_packages(ctx: SourceContext):
    if ctx.control is None:
        return
    seen: dict[str, int] = {}
    for stanza in ctx.control.binaries:
        name = stanza.get("Package")
        if not name:
            continue
        if name in seen:
            yield finding(
                "control-duplicate-package",
                "debian/control",
                stanza.start_line,
                f"{name!r} is defined twice (first at line {seen[name]})",
            )
        else:
            seen[name] = stanza.start_line


@rule("control-build-depends-no-debhelper", Severity.WARNING, "Build-Depends should use debhelper")
def check_debhelper_dependency(ctx: SourceContext):
    if ctx.control is None:
        return
    depends = ctx.control.all_build_depends()
    if not depends:
        return
    uses_debhelper = any(
        item.split("(")[0].strip().startswith(("debhelper", "dh-")) for item in depends
    )
    if not uses_debhelper:
        yield finding(
            "control-build-depends-no-debhelper",
            "debian/control",
            ctx.control.source.line_of("Build-Depends") if ctx.control.source else 1,
            "no debhelper build dependency; the dh sequencer cannot run",
        )


# ------------------------------------------------------- debian/rules ------


@rule("rules-missing", Severity.ERROR, "debian/rules is the build entry point")
def check_rules_present(ctx: SourceContext):
    if not ctx.exists("debian", "rules"):
        yield finding("rules-missing", "debian/rules", 1, "no rules file: dpkg-buildpackage has nothing to run")


@rule("rules-shebang", Severity.ERROR, "debian/rules must start with #!/usr/bin/make -f")
def check_rules_shebang(ctx: SourceContext):
    text = ctx.text("debian", "rules")
    if text is None:
        return
    first = text.splitlines()[0] if text.splitlines() else ""
    if first.strip() != "#!/usr/bin/make -f":
        yield finding(
            "rules-shebang",
            "debian/rules",
            1,
            f"first line is {first.strip()!r}; Policy requires '#!/usr/bin/make -f'",
        )


@rule("rules-not-executable", Severity.ERROR, "debian/rules must be executable")
def check_rules_executable(ctx: SourceContext):
    path = ctx.path("debian", "rules")
    if path.is_file() and not os.access(path, os.X_OK):
        yield finding("rules-not-executable", "debian/rules", 1, "file is not executable (chmod +x)")


@rule("debhelper-compat-missing", Severity.WARNING, "declare a debhelper compat level")
def check_compat_present(ctx: SourceContext):
    if ctx.control is None:
        return
    declared = debhelper_compat(ctx.control)
    compat_file = ctx.text("debian", "compat")
    if declared is None and compat_file is None:
        yield finding(
            "debhelper-compat-missing",
            "debian/control",
            ctx.control.source.line_of("Build-Depends") if ctx.control.source else 1,
            "no 'debhelper-compat (= N)' in Build-Depends and no debian/compat file",
        )


@rule("debhelper-compat-conflict", Severity.ERROR, "compat must be declared exactly once")
def check_compat_conflict(ctx: SourceContext):
    if ctx.control is None:
        return
    if ctx.text("debian", "compat") is not None and debhelper_compat(ctx.control) is not None:
        yield finding(
            "debhelper-compat-conflict",
            "debian/compat",
            1,
            "compat level declared twice (debian/compat and Build-Depends); dh refuses this",
        )


@rule("debhelper-compat-old", Severity.WARNING, "compat levels below 10 are obsolete")
def check_compat_level(ctx: SourceContext):
    if ctx.control is None:
        return
    level = debhelper_compat(ctx.control)
    source_line = ctx.control.source.line_of("Build-Depends") if ctx.control.source else 1
    if level is None:
        compat_text = ctx.text("debian", "compat")
        if compat_text and compat_text.strip().isdigit():
            level = int(compat_text.strip())
            source_line = 1
    if level is None:
        return
    if level < 10:
        yield finding(
            "debhelper-compat-old",
            "debian/control",
            source_line,
            f"compat level {level} is obsolete; use 13",
        )
    elif level < 13:
        yield finding(
            "debhelper-compat-old",
            "debian/control",
            source_line,
            f"compat level {level} is supported but 13 is current",
            severity=Severity.INFO,
        )


@rule("source-format-missing", Severity.WARNING, "debian/source/format selects the source format")
def check_source_format_present(ctx: SourceContext):
    if not ctx.exists("debian", "source", "format"):
        yield finding(
            "source-format-missing",
            "debian/source/format",
            1,
            "missing file; dpkg-source falls back to 1.0 and loses patch tracking",
        )


@rule("source-format-legacy", Severity.WARNING, "1.0 source format is legacy")
def check_source_format_value(ctx: SourceContext):
    value = ctx.source_format()
    if not value:
        return
    if value not in VALID_FORMATS:
        yield finding(
            "source-format-legacy",
            "debian/source/format",
            1,
            f"unknown format {value!r}; expected one of {', '.join(sorted(VALID_FORMATS))}",
        )
    elif value == "1.0":
        yield finding(
            "source-format-legacy",
            "debian/source/format",
            1,
            "format 1.0 cannot carry patches; use '3.0 (quilt)'",
        )


# ----------------------------------------------------------- changelog -----


@rule("changelog-missing", Severity.ERROR, "debian/changelog is required")
def check_changelog_present(ctx: SourceContext):
    if not ctx.exists("debian", "changelog"):
        yield finding("changelog-missing", "debian/changelog", 1, "no changelog: dpkg cannot determine a version")


@rule("changelog-parse-error", Severity.ERROR, "the entry header must match Policy")
def check_changelog_header(ctx: SourceContext):
    if ctx.changelog_text and ctx.changelog is None:
        first = ctx.changelog_text.splitlines()[0] if ctx.changelog_text.splitlines() else ""
        yield finding(
            "changelog-parse-error",
            "debian/changelog",
            1,
            f"header {first[:70]!r} does not match 'package (version) distribution; urgency=level'",
        )


@rule("changelog-invalid-urgency", Severity.WARNING, "urgency must be a known level")
def check_urgency(ctx: SourceContext):
    entry = ctx.changelog
    if entry is None:
        return
    if entry.urgency not in VALID_URGENCIES:
        yield finding(
            "changelog-invalid-urgency",
            "debian/changelog",
            entry.header_line,
            f"urgency {entry.urgency!r} is not one of {', '.join(sorted(VALID_URGENCIES))}",
        )


@rule("changelog-unreleased", Severity.INFO, "UNRELEASED entries cannot be uploaded")
def check_distribution(ctx: SourceContext):
    entry = ctx.changelog
    if entry is None:
        return
    if entry.distribution.upper() == "UNRELEASED":
        yield finding(
            "changelog-unreleased",
            "debian/changelog",
            entry.header_line,
            "distribution is UNRELEASED; set the target series before uploading",
        )


@rule("changelog-maintainer-mismatch", Severity.WARNING, "changelog signer should match Maintainer")
def check_signer(ctx: SourceContext):
    entry = ctx.changelog
    if entry is None or ctx.control is None or ctx.control.source is None:
        return
    signer = entry.maintainer
    declared = ctx.control.source.get("Maintainer")
    if signer and declared and " ".join(signer.split()).lower() != " ".join(declared.split()).lower():
        yield finding(
            "changelog-maintainer-mismatch",
            "debian/changelog",
            entry.signature_line,
            f"signed by {signer!r} but control says {declared!r}",
        )


@rule("changelog-package-mismatch", Severity.ERROR, "changelog and control must name the same source")
def check_package_name(ctx: SourceContext):
    entry = ctx.changelog
    if entry is None or not ctx.source_name:
        return
    if entry.package != ctx.source_name:
        yield finding(
            "changelog-package-mismatch",
            "debian/changelog",
            entry.header_line,
            f"changelog names {entry.package!r}, control names {ctx.source_name!r}",
        )


@rule("changelog-no-trailing-newline", Severity.WARNING, "changelog must end with exactly one newline")
def check_trailing_newline(ctx: SourceContext):
    text = ctx.changelog_text
    if not text:
        return
    if not text.endswith("\n") or text.endswith("\n\n"):
        yield finding(
            "changelog-no-trailing-newline",
            "debian/changelog",
            text.count("\n") + 1,
            "file must end with a single newline after the signature",
        )


@rule("changelog-signature", Severity.ERROR, "entries end with ' -- Name <email>  date'")
def check_signature(ctx: SourceContext):
    entry = ctx.changelog
    if entry is None:
        return
    for tag, line, message in entry.problems:
        yield finding(tag, "debian/changelog", line, message)


@rule("changelog-version-native", Severity.WARNING, "native and non-native versions disagree with the format")
def check_native_version(ctx: SourceContext):
    entry = ctx.changelog
    if entry is None:
        return
    source_format = ctx.source_format()
    if "native" in source_format and entry.has_revision:
        yield finding(
            "changelog-version-native",
            "debian/changelog",
            entry.header_line,
            f"format is native but version {entry.version!r} carries a Debian revision",
        )
    elif "quilt" in source_format and not entry.has_revision:
        yield finding(
            "changelog-version-native",
            "debian/changelog",
            entry.header_line,
            f"format is non-native but version {entry.version!r} has no Debian revision",
        )


# ------------------------------------------------------------ copyright ---


@rule("copyright-missing", Severity.ERROR, "debian/copyright is required")
def check_copyright_present(ctx: SourceContext):
    if not ctx.exists("debian", "copyright"):
        yield finding("copyright-missing", "debian/copyright", 1, "no copyright file: the package is not distributable")


@rule("copyright-format", Severity.WARNING, "use the machine-readable DEP-5 format")
def check_copyright_format(ctx: SourceContext):
    text = ctx.text("debian", "copyright")
    if text is None:
        return
    if "Format:" not in text:
        yield finding(
            "copyright-format",
            "debian/copyright",
            1,
            "no 'Format:' field; DEP-5 makes licence review mechanical",
        )


@rule("copyright-license", Severity.ERROR, "copyright must state a licence")
def check_copyright_license(ctx: SourceContext):
    text = ctx.text("debian", "copyright")
    if text is None:
        return
    if "License:" not in text:
        yield finding("copyright-license", "debian/copyright", 1, "no 'License:' field anywhere in the file")


# --------------------------------------------------------------- layout ---


@rule("install-path-usr-local", Severity.ERROR, "packages must not install into /usr/local")
def check_usr_local(ctx: SourceContext):
    # .install/.dirs/.links files use paths relative to the root ("usr/local/bin/x"),
    # while debian/rules is shell and would contain an absolute "/usr/local".
    # Both mean the same violation, so both spellings are checked.
    path_files = ctx.glob("*.install") + ctx.glob("*.dirs") + ctx.glob("*.links")
    rules = ctx.path("debian", "rules")

    for path in path_files:
        text = ctx.relpath(path)
        for number, line in _lines(path):
            tokens = line.strip().split()
            if tokens and tokens[0].lstrip("/").startswith("usr/local"):
                yield finding(
                    "install-path-usr-local",
                    text,
                    number,
                    "/usr/local is reserved for the administrator (FHS); install under /usr",
                )

    if rules.is_file():
        for number, line in _lines(rules):
            if "/usr/local" in line:
                yield finding(
                    "install-path-usr-local",
                    "debian/rules",
                    number,
                    "/usr/local is reserved for the administrator (FHS); install under /usr",
                )


@rule("maintainer-script-not-executable", Severity.ERROR, "maintainer scripts must be executable")
def check_maintainer_script_mode(ctx: SourceContext):
    for name in ("preinst", "postinst", "prerm", "postrm", "config"):
        path = ctx.path("debian", name)
        if path.is_file() and not os.access(path, os.X_OK):
            yield finding("maintainer-script-not-executable", f"debian/{name}", 1, "mode is not executable")


@rule("maintainer-script-no-set-e", Severity.WARNING, "maintainer scripts must fail fast")
def check_maintainer_script_set_e(ctx: SourceContext):
    for name in ("preinst", "postinst", "prerm"):
        text = ctx.text("debian", name)
        if text is None:
            continue
        if "set -e" not in text:
            yield finding(
                "maintainer-script-no-set-e",
                f"debian/{name}",
                1,
                "no 'set -e'; a failing command would be ignored and dpkg would record success",
            )


@rule("manpage-missing", Severity.WARNING, "every program in /usr/bin needs a man page")
def check_manpages(ctx: SourceContext):
    install_files = ctx.glob("*.install")
    executables: list[str] = []
    for path in install_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            entry = line.strip()
            if entry.startswith(("usr/bin/", "/usr/bin/")):
                executables.append(entry)
    if executables and not ctx.glob("*.1"):
        yield finding(
            "manpage-missing",
            "debian/",
            1,
            f"{len(executables)} program(s) installed but no man page in debian/*.1",
        )


@rule("autopkgtest-missing", Severity.INFO, "autopkgtest lets Ubuntu test the package on every series")
def check_autopkgtest(ctx: SourceContext):
    if not ctx.path("debian", "tests", "control").is_file():
        yield finding(
            "autopkgtest-missing",
            "debian/tests/control",
            1,
            "no autopkgtest definition; the package cannot be gated in proposed-migration",
        )


@rule("watch-missing", Severity.INFO, "debian/watch enables automated upstream tracking")
def check_watch(ctx: SourceContext):
    if not ctx.exists("debian", "watch"):
        yield finding("watch-missing", "debian/watch", 1, "no watch file; new upstream releases go unnoticed")


def registered_rules() -> list[Rule]:
    return [RULES[tag] for tag in sorted(RULES)]

"""The source-package context every rule reads from.

A rule should not need to know whether a file exists, whether it parsed, or
where it lives.  This object answers all three and records the failure modes
that are not attributable to any single rule (unreadable files, unparseable
control data) so they surface as findings instead of tracebacks.
"""

from __future__ import annotations

from pathlib import Path

from .changelog import ChangelogEntry, parse_changelog
from .control import ControlFile, parse_control
from .deb822 import Deb822Error
from .model import Finding, Severity


class SourceContext:
    """A Debian source tree rooted at *root*."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.debian = self.root / "debian"
        self.control: ControlFile | None = None
        self.changelog: ChangelogEntry | None = None
        self.changelog_text = ""
        self.load_errors: list[Finding] = []
        self._loaded = False

    # -- filesystem helpers -------------------------------------------------

    def path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    def relpath(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    def text(self, *parts: str) -> str | None:
        target = self.path(*parts)
        if not target.is_file():
            return None
        try:
            return target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def exists(self, *parts: str) -> bool:
        return self.path(*parts).exists()

    def glob(self, pattern: str) -> list[Path]:
        return sorted(self.debian.glob(pattern))

    # -- parsing ------------------------------------------------------------

    def load(self) -> "SourceContext":
        if self._loaded:
            return self
        self._loaded = True

        control_text = self.text("debian", "control")
        if control_text is not None:
            try:
                self.control = parse_control(control_text)
            except Deb822Error as exc:
                self.load_errors.append(
                    Finding(
                        tag="control-parse-error",
                        severity=Severity.ERROR,
                        path="debian/control",
                        line=exc.line or 1,
                        message=str(exc),
                    )
                )

        changelog_text = self.text("debian", "changelog")
        if changelog_text is not None:
            self.changelog_text = changelog_text
            self.changelog = parse_changelog(changelog_text)

        return self

    # -- convenience --------------------------------------------------------

    @property
    def source_name(self) -> str:
        if self.control is None or self.control.source is None:
            return ""
        return self.control.source.get("Source")

    @property
    def binary_names(self) -> list[str]:
        if self.control is None:
            return []
        return [stanza.get("Package") for stanza in self.control.binaries]

    def source_format(self) -> str:
        text = self.text("debian", "source", "format")
        return text.strip() if text else ""

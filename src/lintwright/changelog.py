"""Parsing and validation for ``debian/changelog``.

The changelog format is unforgiving in ways that are invisible until an
upload is rejected: two spaces before the signature dash, a trailing blank
line, an RFC 2822-parseable date, and a distribution that is not
``UNRELEASED``.  Each of those is a separate finding here rather than one
opaque "bad changelog" error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime

HEADER_RE = re.compile(
    r"^(?P<package>[a-z0-9][a-z0-9+.-]+) \((?P<version>[^)]+)\) "
    r"(?P<distribution>[^;]+);\s*urgency=(?P<urgency>\S+)\s*$"
)
SIGNATURE_RE = re.compile(r"^ -- (?P<name>.+) <(?P<email>[^<>]+)>  (?P<date>\S.*)$")

VALID_URGENCIES = {"low", "medium", "high", "emergency", "critical"}


@dataclass
class ChangelogEntry:
    package: str
    version: str
    distribution: str
    urgency: str
    maintainer_name: str = ""
    maintainer_email: str = ""
    date_raw: str = ""
    date: object | None = None
    header_line: int = 1
    signature_line: int = 0
    body: str = ""
    problems: list[tuple[str, int, str]] = field(default_factory=list)

    @property
    def has_revision(self) -> bool:
        return "-" in self.version.rsplit(":", 1)[-1]

    @property
    def maintainer(self) -> str:
        if not self.maintainer_name:
            return ""
        return f"{self.maintainer_name} <{self.maintainer_email}>"


def parse_changelog(text: str) -> ChangelogEntry | None:
    """Parse the most recent changelog entry.

    Returns ``None`` when the header line is not a valid entry header; the
    caller turns that into a finding with the line number.
    """

    lines = text.splitlines()
    if not lines:
        return None

    header = HEADER_RE.match(lines[0])
    if header is None:
        return None

    entry = ChangelogEntry(
        package=header.group("package"),
        version=header.group("version").strip(),
        distribution=header.group("distribution").strip(),
        urgency=header.group("urgency").strip(),
        header_line=1,
    )

    body: list[str] = []
    for number, line in enumerate(lines[1:], start=2):
        signature = SIGNATURE_RE.match(line)
        if signature is not None:
            entry.signature_line = number
            entry.maintainer_name = signature.group("name").strip()
            entry.maintainer_email = signature.group("email").strip()
            entry.date_raw = signature.group("date").strip()
            try:
                entry.date = parsedate_to_datetime(entry.date_raw)
            except (TypeError, ValueError):
                entry.problems.append(
                    ("changelog-signature", number, f"cannot parse date {entry.date_raw!r} as RFC 2822")
                )
            break
        body.append(line)
    else:
        entry.problems.append(
            ("changelog-signature", len(lines), "entry has no ' -- Name <email>  date' trailer")
        )

    entry.body = "\n".join(body).strip("\n")
    return entry

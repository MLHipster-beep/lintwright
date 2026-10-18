"""RFC822-style paragraph parser for Debian control files.

A Debian control file is a sequence of paragraphs: ``Field: value`` lines
followed by indented continuation lines, with paragraphs separated by a blank
line.  ``Description`` is the canonical example of a field whose value spans
lines.

The parser keeps the source line number of every field.  That matters more
than it looks: a finding that says "line 12" is actionable, while a finding
that says "somewhere in debian/control" is not, and packaging review is
mostly a long sequence of small exact corrections.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

FIELD_RE = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9-]*):(?P<value>.*)$")


class Deb822Error(ValueError):
    """A control file that cannot be parsed as RFC822-style paragraphs."""

    def __init__(self, message: str, line: int = 0) -> None:
        super().__init__(message)
        self.line = line


@dataclass
class Paragraph:
    """One paragraph of a control file, with field line numbers preserved."""

    start_line: int = 1
    fields: dict[str, str] = field(default_factory=dict)
    field_lines: dict[str, int] = field(default_factory=dict)

    def get(self, name: str, default: str = "") -> str:
        for key, value in self.fields.items():
            if key.lower() == name.lower():
                return value
        return default

    def has(self, name: str) -> bool:
        return any(key.lower() == name.lower() for key in self.fields)

    def line_of(self, name: str) -> int:
        for key, line in self.field_lines.items():
            if key.lower() == name.lower():
                return line
        return self.start_line

    def names(self) -> list[str]:
        return list(self.fields)


def parse_paragraphs(text: str) -> list[Paragraph]:
    """Parse *text* into paragraphs, raising :class:`Deb822Error` on bad syntax."""

    paragraphs: list[Paragraph] = []
    current: Paragraph | None = None
    current_field: str | None = None

    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            if current is not None and current.fields:
                paragraphs.append(current)
            current = None
            current_field = None
            continue

        # Comment lines are legal in control files and are used by humans to
        # annotate build dependencies.  They are not part of any field.
        if line.lstrip().startswith("#"):
            continue

        if line[0] in " \t":
            if current is None or current_field is None:
                raise Deb822Error("continuation line without a preceding field", number)
            current.fields[current_field] += "\n" + line[1:]
            continue

        match = FIELD_RE.match(line)
        if match is None:
            raise Deb822Error(f"not a 'Field: value' line: {line[:60]!r}", number)

        if current is None:
            current = Paragraph(start_line=number)

        name = match.group("name")
        if name in current.fields:
            raise Deb822Error(f"duplicate field {name!r}", number)

        current.fields[name] = match.group("value").strip()
        current.field_lines[name] = number
        current_field = name

    if current is not None and current.fields:
        paragraphs.append(current)

    return paragraphs


def split_list(value: str) -> list[str]:
    """Split a comma-separated control field, dropping empty entries."""

    return [item.strip() for item in value.split(",") if item.strip()]

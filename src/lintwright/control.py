"""Parsing for ``debian/control`` and ``debian/copyright``."""

from __future__ import annotations

from dataclasses import dataclass

from .deb822 import Paragraph, parse_paragraphs, split_list

MAINTAINER_RE = None  # populated lazily to keep this module import-light


@dataclass
class ControlFile:
    paragraphs: list[Paragraph]

    @property
    def source(self) -> Paragraph | None:
        for paragraph in self.paragraphs:
            if paragraph.has("Source"):
                return paragraph
        return None

    @property
    def binaries(self) -> list[Paragraph]:
        return [p for p in self.paragraphs if p.has("Package")]

    @property
    def build_depends(self) -> list[str]:
        if self.source is None:
            return []
        return split_list(self.source.get("Build-Depends"))

    @property
    def build_depends_indep(self) -> list[str]:
        if self.source is None:
            return []
        return split_list(self.source.get("Build-Depends-Indep"))

    def all_build_depends(self) -> list[str]:
        return self.build_depends + self.build_depends_indep


def parse_control(text: str) -> ControlFile:
    return ControlFile(paragraphs=parse_paragraphs(text))


def debhelper_compat(control: ControlFile) -> int | None:
    """Return the declared debhelper compat level, if any.

    Modern packages declare ``debhelper-compat (= N)`` in Build-Depends.
    Older ones ship a ``debian/compat`` file.  Both are read by ``dh``; only
    one may be present.
    """

    for depend in control.all_build_depends():
        if not depend.startswith("debhelper-compat"):
            continue
        _, _, rest = depend.partition("(")
        digits = "".join(character for character in rest if character.isdigit())
        if digits:
            return int(digits)
    return None

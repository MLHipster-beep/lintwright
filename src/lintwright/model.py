"""Findings, severities, and the rule registry.

Rules are plain functions that take a :class:`lintwright.source.SourceContext`
and yield findings.  Registration happens at import time through the
``@rule`` decorator, which keeps the rule's identity, severity and
documentation next to the code that implements it — the three things that
drift apart in tooling like this if you let them live in separate tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, Callable, Iterable

if TYPE_CHECKING:  # pragma: no cover - import cycle broken for type checkers
    from .source import SourceContext


class Severity(IntEnum):
    ERROR = 1
    WARNING = 2
    INFO = 3

    @property
    def label(self) -> str:
        return self.name.lower()

    @classmethod
    def parse(cls, value: str) -> "Severity":
        try:
            return cls[value.strip().upper()]
        except KeyError as exc:
            raise ValueError(f"unknown severity {value!r}") from exc


@dataclass(frozen=True)
class Finding:
    tag: str
    severity: Severity
    path: str
    line: int
    message: str

    def sort_key(self) -> tuple[str, int, str]:
        return (self.path, self.line, self.tag)

    def as_dict(self) -> dict[str, object]:
        return {
            "tag": self.tag,
            "severity": self.severity.label,
            "path": self.path,
            "line": self.line,
            "message": self.message,
        }


@dataclass(frozen=True)
class Rule:
    tag: str
    severity: Severity
    summary: str
    check: Callable[[SourceContext], Iterable[Finding]]


RULES: dict[str, Rule] = {}


def rule(tag: str, severity: Severity, summary: str) -> Callable:
    """Register a check function under *tag*."""

    def decorate(function: Callable[[SourceContext], Iterable[Finding]]):
        if tag in RULES:
            raise RuntimeError(f"duplicate rule tag: {tag}")
        RULES[tag] = Rule(tag=tag, severity=severity, summary=summary, check=function)
        return function

    return decorate


def finding(
    tag: str,
    path: str,
    line: int,
    message: str,
    severity: Severity | None = None,
) -> Finding:
    """Build a finding, defaulting the severity to the rule's registration.

    A few rules report sub-tags that are not separately registered — the
    changelog parser distinguishes a missing signature from an unparseable
    date inside the same rule.  Those default to ERROR, which is the safe
    direction: an unclassified structural problem should not pass CI.
    """

    registered = RULES.get(tag)
    return Finding(
        tag=tag,
        severity=severity or (registered.severity if registered else Severity.ERROR),
        path=path,
        line=max(1, line),
        message=message,
    )


def run_rules(ctx: SourceContext, only: set[str] | None = None, skip: set[str] | None = None) -> list[Finding]:
    """Run every registered rule, returning findings sorted by location."""

    findings: list[Finding] = list(ctx.load_errors)
    for tag in sorted(RULES):
        if only and tag not in only:
            continue
        if skip and tag in skip:
            continue
        findings.extend(RULES[tag].check(ctx))
    findings.sort(key=Finding.sort_key)
    return findings

"""Command line interface for lintwright."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__, rules as _rules  # noqa: F401  (rule registration side effect)
from .model import RULES, Severity, run_rules
from .source import SourceContext

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2

THRESHOLDS = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "info": Severity.INFO,
    "never": None,
}

COLORS = {
    Severity.ERROR: "\033[31m",
    Severity.WARNING: "\033[33m",
    Severity.INFO: "\033[36m",
}
RESET = "\033[0m"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lintwright",
        description="Static analysis for Debian source packages.",
    )
    parser.add_argument("--version", action="version", version=f"lintwright {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="analyse a source tree")
    check.add_argument("path", nargs="?", default=".", help="source tree root (default: .)")
    check.add_argument("--format", choices=("text", "json"), default="text")
    check.add_argument(
        "--fail-on",
        choices=tuple(THRESHOLDS),
        default="error",
        help="lowest severity that produces a non-zero exit (default: error)",
    )
    check.add_argument("--only", action="append", default=[], metavar="TAG", help="run only this tag")
    check.add_argument("--skip", action="append", default=[], metavar="TAG", help="never run this tag")
    check.add_argument("--no-color", action="store_true")
    check.add_argument("--statistics", action="store_true", help="print per-tag counts")

    listing = subparsers.add_parser("rules", help="list the rule set")
    listing.add_argument("--format", choices=("text", "json"), default="text")

    return parser


def _list_rules(output_format: str) -> int:
    if output_format == "json":
        payload = [
            {"tag": rule.tag, "severity": rule.severity.label, "summary": rule.summary}
            for rule in (RULES[tag] for tag in sorted(RULES))
        ]
        print(json.dumps(payload, indent=2))
        return EXIT_OK

    for tag in sorted(RULES):
        rule = RULES[tag]
        print(f"{rule.severity.label:<8} {tag:<38} {rule.summary}")
    print(f"\n{len(RULES)} rules")
    return EXIT_OK


def _check(args: argparse.Namespace) -> int:
    root = Path(args.path)
    if not root.is_dir():
        print(f"lintwright: not a directory: {root}", file=sys.stderr)
        return EXIT_USAGE

    unknown = sorted(set(args.only + args.skip) - set(RULES))
    if unknown:
        print(f"lintwright: unknown tag(s): {', '.join(unknown)}", file=sys.stderr)
        return EXIT_USAGE

    started = time.perf_counter()
    context = SourceContext(root).load()
    findings = run_rules(
        context,
        only=set(args.only) or None,
        skip=set(args.skip) or None,
    )
    elapsed = time.perf_counter() - started

    counts = {severity.label: 0 for severity in Severity}
    for item in findings:
        counts[item.severity.label] += 1

    if args.format == "json":
        print(
            json.dumps(
                {
                    "tool": "lintwright",
                    "version": __version__,
                    "root": str(context.root),
                    "summary": counts,
                    "findings": [item.as_dict() for item in findings],
                },
                indent=2,
            )
        )
    else:
        _print_text(findings, context, counts, args, elapsed)

    threshold = THRESHOLDS[args.fail_on]
    if threshold is None:
        return EXIT_OK
    return EXIT_FINDINGS if any(item.severity <= threshold for item in findings) else EXIT_OK


def _print_text(findings, context, counts, args, elapsed) -> None:
    use_color = sys.stdout.isatty() and not args.no_color
    for item in findings:
        color = COLORS[item.severity] if use_color else ""
        reset = RESET if use_color else ""
        print(f"{item.path}:{item.line}: {color}{item.severity.label}{reset}: {item.message} [ {item.tag} ]")

    total = len(findings)
    summary = f"{counts['error']} errors, {counts['warning']} warnings, {counts['info']} info"
    print(f"\nlintwright {__version__}: {total} findings ({summary}) in {context.root}", file=sys.stderr)
    print(f"{len(RULES)} rules, {elapsed * 1000:.1f} ms", file=sys.stderr)

    if args.statistics and findings:
        per_tag: dict[str, int] = {}
        for item in findings:
            per_tag[item.tag] = per_tag.get(item.tag, 0) + 1
        print("\nby tag:", file=sys.stderr)
        for tag, count in sorted(per_tag.items(), key=lambda pair: (-pair[1], pair[0])):
            print(f"  {count:>4}  {tag}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "rules":
        return _list_rules(args.format)
    return _check(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

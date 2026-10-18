"""Fixture builders for the rule tests."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

BASE_CONTROL = """\
Source: demo
Section: devel
Priority: optional
Maintainer: Test Person <test@example.com>
Build-Depends: debhelper-compat (= 13)
Standards-Version: 4.7.0

Package: demo
Architecture: all
Depends: ${misc:Depends}
Description: a demonstration package
 Longer explanation of what the package does and why it exists.
"""

BASE_CHANGELOG = """\
demo (1.0-1) noble; urgency=medium

  * Initial release.

 -- Test Person <test@example.com>  Mon, 05 Oct 2026 10:00:00 +0000
"""

BASE_COPYRIGHT = """\
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: demo

Files: *
Copyright: 2026 Test Person
License: MIT
"""


def base_files(**overrides: str) -> dict[str, str]:
    files = {
        "debian/control": BASE_CONTROL,
        "debian/changelog": BASE_CHANGELOG,
        "debian/rules": "#!/usr/bin/make -f\n%:\n\tdh $@\n",
        "debian/source/format": "3.0 (quilt)\n",
        "debian/copyright": BASE_COPYRIGHT,
        "debian/watch": "version=4\n",
        "debian/tests/control": "Tests: smoke\nDepends: @\n",
        "debian/demo.1": ".TH demo 1\n",
    }
    files.update(overrides)
    return files


def make_tree(root: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    rules = root / "debian" / "rules"
    if rules.is_file():
        os.chmod(rules, 0o755)
    return root

"""lintwright — static analysis for Debian source packages.

The tool exists because the expensive failures in packaging are not compile
errors.  They are policy details that a reviewer or an archive upload rejects
weeks later: a changelog with one space before the signature dash, a missing
``debian/source/format``, ``/usr/local`` in an install path, a compat level
that no longer exists in the target series.
"""

__version__ = "0.3.0"

__all__ = ["__version__"]

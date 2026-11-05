"""
Compares two unitTAS reports test by test: the tests only one of them ran, and the ones that came out differently.
Times and the details under a line don't count. A failure that is an "expected failure" in the second report is
listed as now marked (@ExpectedFailure), not as a difference. unitTAS's own problem lines are listed apart, and any
of them is a difference: a run with problems didn't run all it was asked to.

  python3 bin/compare_reports.py before/report.txt after/report.txt

For a change that must leave a suite's results as they were (a mod moving onto a new unitTAS, say): the full run
before it, the full run after. Exits 0 when both ran the same tests with the same outcomes, 1 when they differ, 2 on
a usage or report error.

The comparison itself is the Python package's (python/src/unittas/compare.py, `unittas compare`); this script is its
caller for the system's Python, which needs nothing installed.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'python', 'src'))

from unittas.compare import main  # noqa: E402  (after the package's folder is on the path)

if __name__ == '__main__':
  sys.exit(main(*sys.argv[1:]))

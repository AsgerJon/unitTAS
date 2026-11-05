"""
The 'compare' module compares two unitTAS reports test by test: the tests
only one of them ran, and the ones that came out differently. Times and
the details under a line don't count. A failure that is an "expected
failure" in the second report is listed as now marked, not as a
difference. unitTAS's own problem lines are listed apart, and any of them
is a difference: a run with problems didn't run all it was asked to. A
NO RESULT line differs from any verdict.

  unittas compare before/report.txt after/report.txt
  python3 bin/compare_reports.py before/report.txt after/report.txt

For a change that must leave a suite's results as they were (a mod moving
onto a new unitTAS, say): the full run before it, the full run after.
Exits 0 when both ran the same tests with the same outcomes, 1 when they
differ, 2 on a usage or report error. It reads Java runs' reports and
Python runs' alike (the same shape, SPEC.md 9.6 decision 9). The standard
library only: bin/compare_reports.py runs it on the system's Python.

- parse, counts, compare: a report read, counted, and two compared.
- main: the command.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import re
import sys
from typing import Any

#  "Name ... outcome (1.2 s)": the name may hold spaces (save mode's " [house, load 1]"), the outcome too.
RESULT = re.compile(r'^(.+?) \.\.\. (\S.*?) \(\d+\.\d s\)$')
MARKED = {('FAIL', 'expected failure'), ('ERROR', 'expected failure')}
NO_RESULT = 'NO RESULT'
USAGE = 'Usage: unittas compare BEFORE/report.txt AFTER/report.txt (or python3 bin/compare_reports.py ...)'


class ReportError(Exception):
  """A report this can't compare."""


def parse(path: str) -> tuple:
  """The report's tests ({name: outcome}, in order) and its problems ([name, first detail line])."""
  tests = {}
  problems = []
  current = None
  try:
    with open(path, encoding='utf-8') as f:
      text = f.read()
  except OSError as error:
    raise ReportError('%s: %s' % (path, error))
  for line in text.split('\n'):
    if line.startswith('-----'):
      break
    match = RESULT.match(line)
    if match:
      name, outcome = match.group(1), match.group(2)
      if outcome == 'problem':
        problems.append([name, ''])
        current = problems[-1]
        continue
      if name in tests:
        raise ReportError('%s: %s is in it twice' % (path, name))
      tests[name] = outcome
      current = None
    elif current is not None and line.startswith('    ') and not current[1]:
      current[1] = line.strip()
  return tests, problems


def counts(tests: dict) -> str:
  """'834 tests (ok 832, FAIL 2)'."""
  by = {}
  for outcome in tests.values():
    by[outcome] = by.get(outcome, 0) + 1
  parts = ['%s %d' % (outcome, n) for outcome, n in sorted(by.items(), key=lambda item: (-item[1], item[0]))]
  return '%d tests (%s)' % (len(tests), ', '.join(parts) or 'none')


def compare(before: dict, after: dict, problemsBefore: list, problemsAfter: list) -> tuple:
  """The lines to print, and how many of them are differences."""
  lines = []
  differences = 0
  for name, outcome in before.items():
    if name not in after:
      lines.append('only before: %s (%s)' % (name, outcome))
      differences += 1
  for name, outcome in after.items():
    if name not in before:
      lines.append('only after: %s (%s)' % (name, outcome))
      differences += 1
  marked = 0
  for name, outcome in before.items():
    if name in after and after[name] != outcome:
      if (outcome, after[name]) in MARKED:
        lines.append('%s: %s -> %s (now marked)' % (name, outcome, after[name]))
        marked += 1
      else:
        lines.append('%s: %s -> %s' % (name, outcome, after[name]))
        differences += 1
  for when, tests in (('before', before), ('after', after)):
    for name, outcome in tests.items():
      if outcome == NO_RESULT:
        #  no verdict, so nothing to be the same as (SPEC.md 9.8), even beside another NO RESULT
        lines.append('no result %s: %s' % (when, name))
        differences += 1
  for when, problems in (('before', problemsBefore), ('after', problemsAfter)):
    for name, detail in problems:
      lines.append('problem %s: %s: %s' % (when, name, detail))
      differences += 1
  if differences:
    lines.append('%d difference%s' % (differences, '' if differences == 1 else 's'))
  else:
    lines.append('the same: %d tests%s' % (len(after), ', %d now marked' % marked if marked else ''))
  return lines, differences


def main(*args: str, out: Any = None) -> int:
  out = sys.stdout if out is None else out
  if len(args) != 2:
    print(USAGE, file=out)
    return 2
  try:
    before, problemsBefore = parse(args[0])
    after, problemsAfter = parse(args[1])
  except ReportError as error:
    print(error, file=out)
    return 2
  print('before: %s' % counts(before), file=out)
  print('after:  %s' % counts(after), file=out)
  lines, differences = compare(before, after, problemsBefore, problemsAfter)
  for line in lines:
    print(line, file=out)
  return 1 if differences else 0


if __name__ == '__main__':
  sys.exit(main(*sys.argv[1:]))

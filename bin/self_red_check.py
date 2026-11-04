"""
Checks the report of unitTAS's own red run line by line, for what a green run can't show: the report's outcomes and
counts, the class fixtures, the worlds each class ran in, the warnings, and what the run puts back after it.

  ./unittas.sh "self,self-red,nosuch"
  python3 bin/self_red_check.py [report.txt]

The report defaults to unittas-results/latest/report.txt. `self` must be all ok; the self-red suite's tests
(src/self/java/.../self/Red*.java) and the unknown suite 'nosuch' must come out exactly as listed below. Exits 0 when
everything matches, 1 with each difference listed otherwise.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, 'run', 'client', 'config')
#  As RedTests.CONFIG_MARK and RedTests.CONFIG_MADE.
CONFIG_MARK = "# changed by unitTAS's self-red run"
CONFIG_MADE = 'unittas-red.cfg'

EXPECTED = {
  'RedClassTests.testFailsUnderAClassMark': 'expected failure',
  'RedSetUpClassTests.setUpClass': 'ERROR',
  'RedSetUpTests.testNeverRuns': 'ERROR',
  'RedSkipClassTests.testA_skipped': 'skipped',
  'RedSkipClassTests.testB_skippedToo': 'skipped',
  'RedTearDownClassTests.tearDownClass': 'ERROR',
  'RedTearDownClassTests.testA_runs': 'ok',
  'RedTearDownClassTests.testB_runsToo': 'ok',
  'RedTests.testExpectedAssertion': 'expected failure',
  'RedTests.testExpectedException': 'expected failure',
  'RedTests.testLeavesTheConfigChanged': 'ok',
  'RedTests.testUnexpectedSuccess': 'unexpected success',
  'RedTests.testWarnsOutsideAStep': 'ok',
  'RedWorldLeavesTests.testLeavesABlock': 'ok',
  'RedWorldSharedTests.testFindsWhatTheClassBeforeLeft': 'ok',
  'unitTAS.suites': 'problem',
}
#  What some lines must say under them (a part of their details).
DETAILS = {
  'RedSetUpClassTests.setUpClass': ('setUpClass fails on purpose', 'its 1 test not run'),
  'RedTearDownClassTests.tearDownClass': ('tearDownClass fails on purpose, after both tests',),
  'RedSkipClassTests.testA_skipped': ('the whole class is skipped',),
  'RedSkipClassTests.testB_skippedToo': ('the whole class is skipped',),
}
#  Lines that mustn't be there: tests that shouldn't have run.
ABSENT = ('RedSetUpClassTests.testNeverRuns',)
SELF_CLASSES = ('ChatTests.', 'ClassFixtureTests.', 'MixinTests.', 'ResetTests.', 'SlowGameTests.',
                'WorldFreshATests.', 'WorldFreshBTests.')
#  The one class that shares the world of the class before it, and that class.
SHARED = ('RedWorldSharedTests', 'RedWorldLeavesTests')
WARNED = 'RedTests.testWarnsOutsideAStep'
LAST_LINE = 'FAILED (errors=3, skipped=2, expected failures=3, unexpected successes=1, problems=1)'

RESULT = re.compile(r'^(\S+) \.\.\. (.+?) \(\d+\.\d s\)$')
WORLD = re.compile(r'^world (\d+)(, shared)?: (.*)$')


def parse(text: str) -> list:
  """
  The report's results, in order, up to the line of dashes: [name, outcome, detail lines, world line], the world line
  (number, shared, what it says) being the one right before the result, or None.
  """
  results = []
  world = None
  for line in text.split('\n'):
    if line.startswith('-----'):
      break
    match = RESULT.match(line)
    if match:
      results.append([match.group(1), match.group(2), [], world])
      world = None
      continue
    match = WORLD.match(line)
    if match:
      world = (int(match.group(1)), match.group(2) is not None, match.group(3))
    elif line.startswith('    ') and results:
      results[-1][2].append(line[4:])
  return results


def checkWorlds(results: list) -> list:
  """One world line before each class's first line; each a fresh world, one more than the last, but SHARED's."""
  out = []
  seen = set()
  last = 0
  for name, _, _, world in results:
    owner = name.split('.')[0]
    if owner == 'unitTAS':
      if world is not None:
        out.append('a world line before %s' % name)
      continue
    if owner in seen:
      if world is not None:
        out.append('a second world line for %s: %s' % (owner, world[2]))
      continue
    seen.add(owner)
    if world is None:
      out.append('no world line before %s' % name)
      continue
    number, shared, says = world
    if owner == SHARED[0]:
      if not shared or number != last or SHARED[1] not in says:
        out.append('%s should share world %d as %s left it; its line says: world %d%s: %s'
                   % (owner, last, SHARED[1], number, ', shared' if shared else '', says))
    elif shared or number != last + 1:
      out.append('%s should get a fresh world %d; its line says: world %d%s: %s'
                 % (owner, last + 1, number, ', shared' if shared else '', says))
    last = number
  return out


def check(text: str) -> list:
  """Every way the report differs from what the red run should give."""
  out = []
  results = parse(text)
  byName = {result[0]: result for result in results}
  for name, outcome in EXPECTED.items():
    if name not in byName:
      out.append('no line for %s (should be "%s")' % (name, outcome))
    elif byName[name][1] != outcome:
      first = (byName[name][2] or [''])[0]
      out.append('%s is "%s", should be "%s" (%s)' % (name, byName[name][1], outcome, first))
  for name, parts in DETAILS.items():
    if name in byName:
      said = '\n'.join(byName[name][2])
      for part in parts:
        if part not in said:
          out.append('%s doesn\'t say %r under it' % (name, part))
  for name in ABSENT:
    if name in byName:
      out.append('%s ran, and shouldn\'t have (%s)' % (name, byName[name][1]))
  for name, outcome, details, _ in results:
    if name in EXPECTED or name in ABSENT:
      continue
    if not name.startswith(SELF_CLASSES):
      out.append('a line nobody expects: %s ... %s' % (name, outcome))
    elif outcome != 'ok':
      out.append('self test %s is "%s" (%s)' % (name, outcome, (details or [''])[0]))
  for prefix in SELF_CLASSES:
    if not any(result[0].startswith(prefix) for result in results):
      out.append('no test of %s in the report' % prefix[:-1])
  out.extend(checkWorlds(results))
  warnings = [(name, i, details) for name, _, details, _ in results
              for i, line in enumerate(details) if line.startswith('warning: ')]
  if len(warnings) != 1:
    out.append('%d warnings in the report, should be 1 (under %s)' % (len(warnings), WARNED))
  for name, i, details in warnings:
    where = details[i + 1] if i + 1 < len(details) else ''
    if name != WARNED or 'player() outside a server step' not in details[i] \
        or WARNED + '(' not in where:
      out.append('a warning that is not the one expected: under %s: %s / %s' % (name, details[i], where))
  tests = sum(1 for result in results if result[1] != 'problem')
  ran = [line for line in text.split('\n') if line.startswith('Ran ')]
  want = r'^Ran %d tests in \d+\.\d s, 1 problem outside them, 1 warning$' % tests
  if len(ran) != 1 or not re.match(want, ran[0]):
    out.append('the Ran line is %r, should be "Ran %d tests in N s, 1 problem outside them, 1 warning"'
               % (ran[0] if ran else None, tests))
  lines = [line for line in text.split('\n') if line.strip()]
  if not lines or lines[-1] != LAST_LINE:
    out.append('the last line is %r, should be %r' % (lines[-1] if lines else None, LAST_LINE))
  forge = os.path.join(CONFIG, 'forge.cfg')
  if not os.path.isfile(forge):
    out.append('no %s to check (the run should have put it back as it was)' % forge)
  elif CONFIG_MARK in open(forge, encoding='utf-8').read():
    out.append('%s still holds the test\'s change: the config wasn\'t put back' % forge)
  if os.path.exists(os.path.join(CONFIG, CONFIG_MADE)):
    out.append('%s is still there: the config wasn\'t put back exactly' % os.path.join(CONFIG, CONFIG_MADE))
  return out


def main(*args: str) -> int:
  path = args[0] if args else os.path.join(ROOT, 'unittas-results', 'latest', 'report.txt')
  with open(path, encoding='utf-8') as f:
    text = f.read()
  differences = check(text)
  for difference in differences:
    print('- ' + difference)
  print('self-red: %s (%s)' % ('as it should be' if not differences else '%d differences' % len(differences), path))
  return 1 if differences else 0


if __name__ == '__main__':
  sys.exit(main(*sys.argv[1:]))

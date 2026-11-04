"""
Tests of bin/compare_reports.py, run as the user runs it: on two report files, as a separate process.

  python -m unittest discover -s bin/tests
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'compare_reports.py')

HEAD = 'unitTAS report, 2026-11-04 20:00:00, suites: a, b\n\n'
TAIL = '----------------------------------------------------------------------\nRan 4 tests in 1.0 s\n\nFAILED\n'


def report(*lines: str) -> str:
  return HEAD + ''.join(line + '\n' for line in lines) + TAIL


BEFORE = report(
  'GiveTests.testRedWool ... ok (0.5 s)',
  'TorchTests.testParked ... FAIL (1.2 s)',
  '    AssertionError: the torch stayed lit',
  '      at TorchTests.testParked(TorchTests.java:40)',
  '    chat during the test:',
  '      | Given [Torch] * 1',
  'SaveTests.testOpens [house, load 1] ... ok (2.0 s)',
  'SkipTests.testLater ... skipped (0.0 s)',
  '    not yet',
)


class CompareTests(unittest.TestCase):

  def setUp(self) -> None:
    self.folder = tempfile.mkdtemp(prefix='compare-reports-')
    self.addCleanup(shutil.rmtree, self.folder)

  def compare(self, before: str, after: str, *args: str):
    paths = []
    for name, text in (('before.txt', before), ('after.txt', after)):
      path = os.path.join(self.folder, name)
      with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
      paths.append(path)
    return subprocess.run([sys.executable, '-I', SCRIPT, *paths, *args], capture_output=True, text=True)

  def test_the_same_tests_and_outcomes(self) -> None:
    # times and the details under a line don't matter
    after = BEFORE.replace('(0.5 s)', '(0.9 s)').replace('the torch stayed lit', 'still lit')
    result = self.compare(BEFORE, after)
    self.assertEqual(result.returncode, 0, result.stdout)
    self.assertIn('the same: 4 tests', result.stdout)

  def test_a_failure_now_marked_expected(self) -> None:
    after = BEFORE.replace('TorchTests.testParked ... FAIL (1.2 s)', 'TorchTests.testParked ... expected failure (1.2 s)')
    result = self.compare(BEFORE, after)
    self.assertEqual(result.returncode, 0, result.stdout)
    self.assertIn('TorchTests.testParked: FAIL -> expected failure (now marked)', result.stdout)

  def test_an_outcome_that_changed(self) -> None:
    after = BEFORE.replace('GiveTests.testRedWool ... ok', 'GiveTests.testRedWool ... ERROR')
    result = self.compare(BEFORE, after)
    self.assertEqual(result.returncode, 1, result.stdout)
    self.assertIn('GiveTests.testRedWool: ok -> ERROR', result.stdout)

  def test_tests_gone_and_new(self) -> None:
    after = report(
      'GiveTests.testRedWool ... ok (0.5 s)',
      'TorchTests.testParked ... FAIL (1.2 s)',
      'SaveTests.testOpens [house, load 1] ... ok (2.0 s)',
      'NewTests.testFresh ... ok (0.1 s)',
    )
    result = self.compare(BEFORE, after)
    self.assertEqual(result.returncode, 1, result.stdout)
    self.assertIn('only before: SkipTests.testLater (skipped)', result.stdout)
    self.assertIn('only after: NewTests.testFresh (ok)', result.stdout)

  def test_unitTAS_problems_are_listed_apart(self) -> None:
    after = HEAD + "unitTAS.suites ... problem (0.0 s)\n    no suite called 'c'\n" + BEFORE[len(HEAD):]
    result = self.compare(BEFORE, after)
    self.assertEqual(result.returncode, 1, result.stdout)
    self.assertIn("problem after: unitTAS.suites: no suite called 'c'", result.stdout)
    self.assertNotIn('only after: unitTAS.suites', result.stdout)

  def test_a_name_in_both_twice_is_an_error(self) -> None:
    twice = report('GiveTests.testRedWool ... ok (0.5 s)', 'GiveTests.testRedWool ... ok (0.5 s)')
    result = self.compare(twice, BEFORE)
    self.assertEqual(result.returncode, 2, result.stdout)

  def test_usage(self) -> None:
    result = subprocess.run([sys.executable, '-I', SCRIPT], capture_output=True, text=True)
    self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
  unittest.main()

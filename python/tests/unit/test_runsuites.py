"""
Suites run on a Run (unittas.run.runSuites), without a game: modules by name, loaded in name order, run with the
run's own result, which writes unittest's class fixtures into the report as the Java report has them. A setUpClass
that fails is one ERROR line, its tests not run; a skip in setUpClass a skipped line for each test; a tearDownClass
that fails an ERROR line of its own; a suite that isn't there a problem before any test.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import unittest

from unittas.run import Run, runSuites
from test_run import FakeRun


class RunSuitesTests(FakeRun, unittest.TestCase):

  def setUp(self) -> None:
    FakeRun.setUp(self)
    Run.current = self.run
    self.addCleanup(setattr, Run, 'current', None)

  def test_fixtures_and_a_missing_suite(self) -> None:
    self.run.begin()
    result = runSuites(self.run, ['gamefixtures', 'nosuchsuite'], stream=io.StringIO())
    self.assertIsInstance(result, unittest.TestResult)
    with open(self.run.finish(), encoding='utf-8') as file:
      lines = file.read().split('\n')
    body = lines[2:lines.index('-' * 70)]
    self.assertRegex(body[0], r"^unitTAS\.suites \.\.\. problem \(0\.0 s\)$")
    self.assertIn("    no suite called 'nosuchsuite'", body[1])
    rest = [line for line in body[2:] if not line.startswith('      ')]
    self.assertEqual('world 1: the run\'s first, for AFixtureErrorTests', rest[0])
    self.assertRegex(rest[1], r'^AFixtureErrorTests\.setUpClass \.\.\. ERROR \(\d+\.\d s\)$')
    self.assertTrue(any('setUpClass fails on purpose' in line for line in rest[2:6]), rest)
    self.assertIn('    (its 1 test not run)', rest)
    skipped = [line for line in rest if line.startswith('BSkipClassTests.')]
    self.assertEqual(['BSkipClassTests.test_a ... skipped (0.0 s)', 'BSkipClassTests.test_b ... skipped (0.0 s)'],
                     skipped)
    self.assertIn('    setUpClass: the whole class is skipped', rest)
    self.assertTrue(any(line.startswith('world 2: fresh for BSkipClassTests') for line in rest), rest)
    self.assertTrue(any(line.startswith('world 3: fresh for CTearDownErrorTests') for line in rest), rest)
    after = rest[[i for i, line in enumerate(rest) if line.startswith('CTearDownErrorTests.test_1')][0] + 1:]
    self.assertRegex(after[0], r'^CTearDownErrorTests\.tearDownClass \.\.\. ERROR \(\d+\.\d s\)$')
    self.assertEqual('FAILED (errors=2, skipped=2, problems=1)', [line for line in lines if line][-1])
    # the progress numbered as the Java runner's: a setUpClass that failed counts the tests it kept from running
    with open(os.path.join(self.results, 'progress.txt'), encoding='utf-8') as file:
      progress = [line for line in file.read().split('\n') if line.startswith('test ')]
    self.assertEqual(['test 1/4 AFixtureErrorTests.setUpClass ... ERROR', 'test 2/4 BSkipClassTests.test_a ... skipped',
                      'test 3/4 BSkipClassTests.test_b ... skipped', 'test 4/4 CTearDownErrorTests.test_1 ... ok',
                      'test 4/4 CTearDownErrorTests.tearDownClass ... ERROR'], progress)


if __name__ == '__main__':
  unittest.main()

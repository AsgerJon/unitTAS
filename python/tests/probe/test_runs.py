"""
Step 6a of phase 3 (SPEC.md section 9.3): a run's lifecycle and GameTestCase in the development client. gamesuite.py's
classes run on a Run (unittas.run) through unittest's own runner, and the run's report is read back: the world lines
(the run's first, a fresh one, a shared one), each test's outcome, the failure's screenshot on disk, the counts.

  python -m unittas.selftest test_runs.      (through the watcher: "probe test_runs.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import re
import unittest

import gamesuite
from probegame import READY_SECONDS, ROOT, results
from unittas.api import Game
from unittas.dev import DevGame
from unittas.launcher import Sources
from unittas.mappings import Mappings
from unittas.run import Run

RESULT = re.compile(r'^(\S+) \.\.\. (.+?) \(\d+\.\d s\)$')


class RunTests(unittest.TestCase):

  def test_a_run_of_game_test_cases(self) -> None:
    launched = DevGame(ROOT, results(), 'runs')
    connection = launched.start()
    connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    folder = os.path.join(launched.results, 'run')
    run = Run(Game(connection, mappings=Mappings.load(Sources(gradleHome=os.path.join(ROOT, '.gradle-home')))),
              launched.gameDir, folder, stop=launched.stop)
    Run.current = run
    try:
      run.begin()
      loader = unittest.TestLoader()
      suite = unittest.TestSuite(loader.loadTestsFromTestCase(each) for each in (
        gamesuite.AFreshTests, gamesuite.BFreshTests, gamesuite.CSharedTests, gamesuite.DChatTests))
      outcome = unittest.TextTestRunner(stream=io.StringIO(), verbosity=2).run(suite)
    finally:
      Run.current = None
      report = run.finish()
    self.assertEqual(1, len(outcome.failures), outcome.failures + outcome.errors)
    self.assertEqual([], outcome.errors)
    with open(report, encoding='utf-8') as file:
      text = file.read()
    lines = text.split('\n')
    results_ = [(found.group(1), found.group(2)) for found in map(RESULT.match, lines) if found]
    self.assertEqual([('AFreshTests.test_leaves_a_gold_block', 'ok'),
                      ('BFreshTests.test_finds_it_gone_and_leaves_wool', 'ok'),
                      ('CSharedTests.test_finds_the_wool', 'ok'),
                      ('DChatTests.test_a_its_own_chat', 'ok'),
                      ('DChatTests.test_b_fails_on_purpose', 'FAIL')], results_)
    worlds = [line for line in lines if line.startswith('world ')]
    self.assertEqual('world 1: the run\'s first, for AFreshTests', worlds[0])
    self.assertRegex(worlds[1], r'^world 2: fresh for BFreshTests \(the kept world put back, opened in \d+\.\d s\)$')
    self.assertEqual('world 2, shared: CSharedTests runs in it as BFreshTests left it', worlds[2])
    self.assertRegex(worlds[3], r'^world 3: fresh for DChatTests')
    self.assertTrue(os.path.isfile(os.path.join(folder, 'screenshots', 'DChatTests.test_b_fails_on_purpose.png')))
    self.assertEqual('FAILED (failures=1)', [line for line in lines if line][-1])
    self.assertTrue(launched.ended(60), 'the run quit the game')


if __name__ == '__main__':
  unittest.main()

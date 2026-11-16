"""
Worlds as classes in the development client (SPEC.md 17.7 step 1):
worldsuite.py's class, loaded as the run loads tests (grouped by world),
run on a Run; its report read back: each test ok, in its world, and the
world lines (the run's first, Terrain made, Arena made, Arena again as
its setUp left it).

  python -m unittas.selftest test_worldruns.
  (through the watcher: "probe test_worldruns.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import re
import unittest

from probegame import READY_SECONDS, ROOT, results
from unittas.api import Game
from unittas.dev import DevGame
from unittas.launcher import Sources
from unittas.mappings import Mappings
from unittas.run import Run, loadSuites

RESULT = re.compile(r'^(\S+) \.\.\. (.+?) \(\d+\.\d s\)$')


class WorldRunTests(unittest.TestCase):

  def test_tests_in_worlds_of_their_own(self) -> None:
    launched = DevGame(ROOT, results(), 'worldruns')
    connection = launched.start()
    connection.events.waitFor(
      lambda event: event.get('event') == 'ready', READY_SECONDS)
    folder = os.path.join(launched.results, 'run')
    sources = Sources(gradleHome=os.path.join(ROOT, '.gradle-home'))
    game = Game(connection, mappings=Mappings.load(sources))
    run = Run(game, launched.gameDir, folder, stop=launched.stop)
    Run.current = run
    try:
      run.begin()
      suite, problems = loadSuites(['worldsuite.EWorldTests'])
      self.assertEqual([], problems)
      outcome = unittest.TextTestRunner(stream=io.StringIO(),
                                        verbosity=2).run(suite)
    finally:
      Run.current = None
      report = run.finish()
    self.assertEqual([], outcome.failures + outcome.errors)
    with open(report, encoding='utf-8') as file:
      lines = file.read().split('\n')
    found = [(each.group(1), each.group(2))
             for each in map(RESULT.match, lines) if each]
    self.assertEqual(
      [('EWorldTests.test_a_in_the_run_s_flat_world', 'ok'),
       ('EWorldTests.test_b_leaves_wool', 'ok'),
       ('EWorldTests.test_c_finds_the_wool', 'ok'),
       ('EWorldTests.test_d_breaks_the_gold', 'ok'),
       ('EWorldTests.test_e_finds_the_gold_again', 'ok'),
       ('EWorldTests.test_f_on_its_own_layers', 'ok')], found)
    worlds = [line for line in lines if line.startswith('world ')]
    self.assertEqual(5, len(worlds), worlds)
    self.assertEqual("world 1: the run's first, for EWorldTests", worlds[0])
    self.assertRegex(worlds[1], r'^world 2: EWorldTests\.terrain for '
                                r'EWorldTests, made as it says \(type '
                                r'default, seed 8675309')
    self.assertRegex(worlds[2], r'^world 3: EWorldTests\.arena for '
                                r'EWorldTests, made as it says')
    self.assertRegex(worlds[3], r'^world 4: EWorldTests\.arena for '
                                r'EWorldTests, as its setUp left it')
    self.assertRegex(worlds[4], r'^world 5: EWorldTests\.layered for '
                                r'EWorldTests, made as it says \(type '
                                r'flat, .*layers 1xminecraft:bedrock:0 '
                                r'2xminecraft:stone:0 1xminecraft:wool:14'
                                r'.*rules doDaylightCycle=False')
    self.assertTrue(launched.ended(60), 'the run quit the game')


if __name__ == '__main__':
  unittest.main()

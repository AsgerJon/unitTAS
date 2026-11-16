"""
A scenario on a Run in the development client (SPEC.md 15.6 step 5):
scenesuite.py's class, loaded as the run loads tests and run on a Run;
its report read back: each test ok, and under each line what it examined
by command (a lever off, then on; pink wool in the chest, then none; a
stone there, then broken) or observed (a redstone lamp, unlit and lit),
the frames kept in the run's results.

  python -m unittas.selftest test_scenarios.
  (through the watcher: "probe test_scenarios.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import unittest

from probegame import READY_SECONDS, ROOT, results
from unittas.api import Game
from unittas.dev import DevGame
from unittas.run import Run, loadSuites

SAID = '    examined by command: '
SEEN = ("    observed (pixels by the game's ray): the block at (0, 5, 3) "
        "from ")


class ScenarioRunTests(unittest.TestCase):

  def test_a_scenario_on_a_run(self) -> None:
    launched = DevGame(ROOT, results(), 'scenarios')
    connection = launched.start()
    connection.events.waitFor(
      lambda event: event.get('event') == 'ready', READY_SECONDS)
    folder = os.path.join(launched.results, 'run')
    run = Run(Game(connection), launched.gameDir, folder, stop=launched.stop)
    Run.current = run
    try:
      run.begin()
      suite, problems = loadSuites(['scenesuite.SceneTests'])
      self.assertEqual([], problems)
      outcome = unittest.TextTestRunner(stream=io.StringIO(),
                                        verbosity=2).run(suite)
    finally:
      Run.current = None
      report = run.finish()
    with open(report, encoding='utf-8') as file:
      text = file.read()
    self.assertEqual([], outcome.failures + outcome.errors, text)
    lines = [line for line in text.split('\n')
             if line.startswith(('SceneTests.', SAID, SEEN))]
    shown = [SEEN if line.startswith(SEEN) else
             line if line.startswith(SAID) else line.split(' (')[0]
             for line in lines]
    self.assertEqual([
      'SceneTests.test_a_the_lever ... ok',
      SAID + 'MCBlocks.Lever at (5, 4, 7), isOn: False',
      SAID + 'MCBlocks.Lever at (5, 4, 7), isOn: True',
      'SceneTests.test_b_the_chest ... ok',
      SAID + 'MCBlocks.Chest at (3, 4, 5), contents: MCItems.PinkWool',
      SAID + 'MCBlocks.Chest at (3, 4, 5), contents: nothing',
      'SceneTests.test_c_a_block_broken ... ok',
      SAID + 'MCBlocks.Stone at (2, 4, 3), isThere: True',
      SAID + 'MCBlocks.Stone at (2, 4, 3), isThere: False',
      'SceneTests.test_d_the_lamp_seen ... ok', SEEN, SEEN], shown, text)
    frames = sorted(name for name in os.listdir(os.path.join(folder,
                                                             'frames'))
                    if name.endswith('.png'))
    self.assertEqual(['examine-0-5-3-1.png', 'examine-0-5-3-2.png'], frames)
    self.assertTrue(launched.ended(60), 'the run quit the game')


if __name__ == '__main__':
  unittest.main()

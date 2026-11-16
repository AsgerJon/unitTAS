"""
A scenario on a Run on the run's port (SPEC.md 15.6 step 5, 19.7 step 4):
scenesuite.py's class, loaded as the run loads tests and run on a Run;
its report read back: each test ok, and under each line what it examined
by command (a lever off, then on; pink wool in the chest, then none; a
stone there, then broken) or observed (a redstone lamp, unlit and lit),
the frames kept in the run's results.

  python -m unittas.selftest test_scenarios.
  (through the watcher: "probe test_scenarios.", "probe test_scenarios on 26.3-fabric")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import unittest

from ports import at, probeGame
from probegame import READY_SECONDS
from unittas.api import Game
from unittas.run import Run, loadSuites

SAID = '    examined by command: '
SEEN = ("    observed (pixels by the game's ray): the block at %s from "
        % (tuple(at(0, 5, 3)),))


def placed(x: int, y: int, z: int) -> str:
  """A place as the report says it, written in 1.7.10's flat world."""
  return '(%d, %d, %d)' % tuple(at(x, y, z))


class ScenarioRunTests(unittest.TestCase):

  def test_a_scenario_on_a_run(self) -> None:
    launched = probeGame('scenarios')
    connection = launched.start(READY_SECONDS)
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
      SAID + 'MCBlocks.Lever at %s, isOn: False' % placed(5, 4, 7),
      SAID + 'MCBlocks.Lever at %s, isOn: True' % placed(5, 4, 7),
      'SceneTests.test_b_the_chest ... ok',
      SAID + 'MCBlocks.Chest at %s, contents: MCItems.PinkWool' % placed(3, 4, 5),
      SAID + 'MCBlocks.Chest at %s, contents: nothing' % placed(3, 4, 5),
      'SceneTests.test_c_a_block_broken ... ok',
      SAID + 'MCBlocks.Stone at %s, isThere: True' % placed(2, 4, 3),
      SAID + 'MCBlocks.Stone at %s, isThere: False' % placed(2, 4, 3),
      'SceneTests.test_d_the_lamp_seen ... ok', SEEN, SEEN], shown, text)
    frames = sorted(name for name in os.listdir(os.path.join(folder,
                                                             'frames'))
                    if name.endswith('.png'))
    lamp = '%d-%d-%d' % tuple(at(0, 5, 3))
    self.assertEqual(['examine-%s-1.png' % lamp, 'examine-%s-2.png' % lamp], frames)
    self.assertTrue(launched.ended(60), 'the run quit the game')


if __name__ == '__main__':
  unittest.main()

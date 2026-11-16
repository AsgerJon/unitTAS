"""
The model scenario on a Run in the development client (SPEC.md 15.6
step 8): modelsuite.py's class, loaded as the run loads tests and run on
a Run; its report read back: each test ok, and under each line what it
examined by command (the wool still on the locked line; the chest empty,
the lever on, then off, pink wool in the chest; then none) and what the
agent knew of its inventory (no wool, then the wool).

  python -m unittas.selftest test_model.
  (through the watcher: "probe test_model.")
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
KNOWN = '    known to the agent: its inventory: '


class ModelScenarioTests(unittest.TestCase):

  def test_the_model_scenario(self) -> None:
    launched = DevGame(ROOT, results(), 'model')
    connection = launched.start()
    connection.events.waitFor(
      lambda event: event.get('event') == 'ready', READY_SECONDS)
    folder = os.path.join(launched.results, 'run')
    run = Run(Game(connection), launched.gameDir, folder, stop=launched.stop)
    Run.current = run
    try:
      run.begin()
      suite, problems = loadSuites(['modelsuite.LeverAndChestTests'])
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
             if line.startswith(('LeverAndChestTests.', SAID, KNOWN))]
    shown = [line if line.startswith((SAID, KNOWN)) else
             line.split(' (')[0] for line in lines]
    chest = SAID + 'MCBlocks.Chest at (0, 4, 6), contents: '
    lever = SAID + 'MCBlocks.Lever at (4, 4, 6), isOn: '
    self.assertEqual([
      'LeverAndChestTests.test_0_locked ... ok',
      SAID + 'MCBlocks.Chest at (3, 5, 6), contents: MCItems.PinkWool',
      'LeverAndChestTests.test_a_the_wool_let_through ... ok',
      chest + 'nothing', lever + 'True', lever + 'False',
      chest + 'MCItems.PinkWool',
      'LeverAndChestTests.test_b_the_wool_taken ... ok',
      KNOWN + 'nothing', KNOWN + 'MCItems.PinkWool', chest + 'nothing'],
      shown, text)
    self.assertTrue(launched.ended(60), 'the run quit the game')


if __name__ == '__main__':
  unittest.main()

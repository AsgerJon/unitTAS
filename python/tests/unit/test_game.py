"""
A launch's own order (unittas.game.LaunchedGame), with a command that is no game: the game folder's options.txt and
config/ are kept aside before the launch prepares anything, so what the launch writes there for its run (a spec's
options, say) is undone when the game has gone, and the player's own files come back.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

from unittas.game import LaunchedGame


class NoGame(LaunchedGame):
  """A 'game' that writes its run's options while preparing, and exits at once."""

  def gameFolder(self) -> str:
    return os.path.join(self.root(), 'game')

  def command(self) -> list:
    return [sys.executable, '-c', 'pass']

  def outputName(self) -> str:
    return 'output.log'

  def prepare(self) -> None:
    with open(os.path.join(self.gameFolder(), 'options.txt'), 'w', encoding='utf-8') as file:
      file.write('autoJump:false\n')


class LaunchOrderTests(unittest.TestCase):

  def test_what_prepare_writes_is_undone(self) -> None:
    root = tempfile.mkdtemp(prefix='unittas-game-')
    self.addCleanup(shutil.rmtree, root, True)
    os.makedirs(os.path.join(root, 'game'))
    with open(os.path.join(root, 'game', 'options.txt'), 'w', encoding='utf-8') as file:
      file.write('autoJump:true\n')
    game = NoGame(root, os.path.join(root, 'results'), 'nogame')
    game.launch()
    with open(os.path.join(root, 'game', 'options.txt'), encoding='utf-8') as file:
      self.assertEqual('autoJump:false\n', file.read(), 'the run\'s options, while it runs')
    game.stop(5)
    with open(os.path.join(root, 'game', 'options.txt'), encoding='utf-8') as file:
      self.assertEqual('autoJump:true\n', file.read(), 'the player\'s own, back')


if __name__ == '__main__':
  unittest.main()

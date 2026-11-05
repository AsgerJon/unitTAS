"""
Tests of unittas.gamefiles: a game folder's options.txt and config/, kept
aside before a game starts and put back exactly after it has exited, also
after a run that died in between (PROTOCOL.md section 0, point 3).

  python -m unittest discover -s python/tests/unit
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from unittas.gamefiles import GameFiles


def write(path: str, text: str) -> None:
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, 'w', encoding='utf-8') as file:
    file.write(text)


def tree(folder: str) -> dict:
  """Every file and link under the folder, by its path from there: its text, or where the link points."""
  found = {}
  for here, dirs, files in os.walk(folder, followlinks=False):
    for name in dirs + files:
      path = os.path.join(here, name)
      key = os.path.relpath(path, folder)
      if os.path.islink(path):
        found[key] = ('link', os.readlink(path))
      elif os.path.isfile(path):
        with open(path, encoding='utf-8') as file:
          found[key] = file.read()
      else:
        found[key] = 'folder'
  return found


class GameFilesTests(unittest.TestCase):

  def setUp(self) -> None:
    self.game = tempfile.mkdtemp(prefix='unittas-game-')
    self.addCleanup(shutil.rmtree, self.game, True)
    write(os.path.join(self.game, 'options.txt'), 'mainHand:left\npauseOnLostFocus:true\n')
    write(os.path.join(self.game, 'config', 'forge.cfg'), 'general {}\n')
    write(os.path.join(self.game, 'config', 'mods', 'efr.cfg'), 'autoJump=false\n')
    write(os.path.join(self.game, 'saves', 'world', 'level.dat'), 'not touched\n')
    self.before = self.mine()

  def mine(self) -> dict:
    """The player's own files: everything but unitTAS's folder."""
    return {key: value for key, value in tree(self.game).items() if not key.startswith('unittas')}

  def scribble(self) -> None:
    """What a run may do: change, add and remove, in options.txt and config/."""
    write(os.path.join(self.game, 'options.txt'), 'mainHand:right\n')
    write(os.path.join(self.game, 'config', 'forge.cfg'), 'changed by the run\n')
    write(os.path.join(self.game, 'config', 'new.cfg'), 'made by the run\n')
    write(os.path.join(self.game, 'config', 'made', 'deep.cfg'), 'a folder the run made\n')
    os.remove(os.path.join(self.game, 'config', 'mods', 'efr.cfg'))

  def test_put_back_exactly(self) -> None:
    files = GameFiles(self.game)
    files.keep()
    self.scribble()
    self.assertTrue(files.putBack())
    self.assertEqual(self.before, self.mine())

  def test_nothing_of_its_own_left_behind(self) -> None:
    files = GameFiles(self.game)
    files.keep()
    files.putBack()
    self.assertEqual([], [key for key in tree(self.game) if key.startswith(os.path.join('unittas', 'orchestrator'))])

  def test_the_saves_are_not_its_business(self) -> None:
    files = GameFiles(self.game)
    files.keep()
    write(os.path.join(self.game, 'saves', 'world', 'level.dat'), 'played\n')
    files.putBack()
    self.assertEqual('played\n', self.mine()[os.path.join('saves', 'world', 'level.dat')])

  def test_a_run_that_died_is_repaired_first(self) -> None:
    GameFiles(self.game).keep()
    self.scribble()
    #  the run died here, before putting back: the next one finds the copy and puts it back before anything else
    again = GameFiles(self.game)
    again.keep()
    self.assertEqual(self.before, self.mine())
    self.scribble()
    again.putBack()
    self.assertEqual(self.before, self.mine())

  def test_an_options_txt_that_wasnt_there_is_removed(self) -> None:
    os.remove(os.path.join(self.game, 'options.txt'))
    before = self.mine()
    files = GameFiles(self.game)
    files.keep()
    write(os.path.join(self.game, 'options.txt'), 'made by the game\n')
    files.putBack()
    self.assertEqual(before, self.mine())

  def test_no_config_folder(self) -> None:
    shutil.rmtree(os.path.join(self.game, 'config'))
    before = self.mine()
    files = GameFiles(self.game)
    files.keep()
    write(os.path.join(self.game, 'config', 'forge.cfg'), 'made by the game\n')
    files.putBack()
    self.assertEqual(before, self.mine())

  def test_links_are_kept_as_links(self) -> None:
    outside = tempfile.mkdtemp(prefix='unittas-outside-')
    self.addCleanup(shutil.rmtree, outside, True)
    write(os.path.join(outside, 'shared.cfg'), 'elsewhere\n')
    os.symlink(os.path.join(outside, 'shared.cfg'), os.path.join(self.game, 'config', 'shared.cfg'))
    before = self.mine()
    files = GameFiles(self.game)
    files.keep()
    os.remove(os.path.join(self.game, 'config', 'shared.cfg'))
    files.putBack()
    self.assertEqual(before, self.mine())
    with open(os.path.join(outside, 'shared.cfg'), encoding='utf-8') as file:
      self.assertEqual('elsewhere\n', file.read(), 'what a link points at is never written')

  def test_put_back_without_a_copy_does_nothing(self) -> None:
    self.scribble()
    changed = self.mine()
    self.assertFalse(GameFiles(self.game).putBack())
    self.assertEqual(changed, self.mine())

  def test_a_copy_only_counts_once_it_is_whole(self) -> None:
    files = GameFiles(self.game)
    files.keep()
    #  as if the run died while copying: the marker isn't there, so nothing half-made is ever put back
    os.remove(files.marker)
    self.scribble()
    changed = self.mine()
    self.assertFalse(GameFiles(self.game).putBack())
    self.assertEqual(changed, self.mine())


if __name__ == '__main__':
  unittest.main()

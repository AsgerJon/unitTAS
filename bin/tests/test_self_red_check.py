"""
The self-red checker's look at what the run put back (bin/self_red_check.py,
SPEC.md 19.7 step 9c), with no game: the game folder the run ran in
(--game, 1.7.10's development client's by default) holds no file in its
config/ with the red test's mark, nor the red test's own file; the
development client's forge.cfg is back too. CHECK names another copy of the
checker to hold to these (a copy from before a change, say).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import importlib.util
import os
import shutil
import tempfile
import unittest

BIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.environ.get('CHECK', os.path.join(BIN, 'self_red_check.py'))


def checker():
  """The checker, loaded from its file."""
  spec = importlib.util.spec_from_file_location('self_red_check', CHECK)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


class ConfigPutBackTests(unittest.TestCase):

  def setUp(self) -> None:
    self.check = checker()
    self.game = tempfile.mkdtemp(prefix='unittas-red-check-')
    self.addCleanup(shutil.rmtree, self.game, True)
    self.config = os.path.join(self.game, 'config')
    os.makedirs(os.path.join(self.config, 'fabric'))

  def write(self, relative: str, text: str) -> None:
    with open(os.path.join(self.config, relative), 'w',
              encoding='utf-8') as file:
      file.write(text)

  def said(self) -> list:
    """The checker's differences about the config, for an empty report."""
    return [each for each in self.check.check('', True, self.game)
            if 'config' in each]

  def test_a_mark_left_in_any_of_its_files_is_said(self) -> None:
    self.write('fabric/indigo.properties',
               'a = 1\n' + self.check.CONFIG_MARK + '\n')
    said = self.said()
    self.assertEqual(1, len(said), said)
    self.assertIn('indigo.properties still holds', said[0])

  def test_its_own_file_left_is_said(self) -> None:
    self.write(self.check.CONFIG_MADE, 'made\n')
    said = self.said()
    self.assertEqual(1, len(said), said)
    self.assertIn('is still there', said[0])

  def test_a_config_put_back_says_nothing(self) -> None:
    self.write('fabric/indigo.properties', 'a = 1\n')
    self.assertEqual([], self.said())

  def test_the_development_client_s_forge_cfg_must_be_back(self) -> None:
    said = [each for each in self.check.check('', True)
            if 'forge.cfg' in each]
    if os.path.isfile(os.path.join(self.check.GAME, 'config', 'forge.cfg')):
      self.assertEqual([], said)
    else:
      self.assertEqual(1, len(said), said)


if __name__ == '__main__':
  unittest.main()

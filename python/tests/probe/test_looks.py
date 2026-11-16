"""
How blocks look in the development client, from its resource pack
(SPEC.md 15.4's identify): block.faces gives each face's icon for each
meta (a furnace's facings, wool's colours, alike metas together),
texture.get each icon's pixels; a view's
face squared up has the block's pixels where the camera says. The
answers are kept beside the results (looks/answers.json).

  python -m unittas.selftest test_looks.
  (through the watcher: "probe test_looks.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import json
import os
import shutil
import unittest

from mcdex import MCBlocks

from probegame import READY_SECONDS, ROOT, results
from unittas.api import Game
from unittas.dev import DevGame
from unittas.reset import reset
from unittas.values import Block, BlockPos

PLACE = BlockPos(0, 5, 3)


class LooksTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = DevGame(ROOT, results(), 'looks')
    shutil.rmtree(os.path.join(cls.launched.gameDir, 'saves', 'unittas'),
                  ignore_errors=True)
    connection = cls.launched.start()
    connection.events.waitFor(
      lambda event: event.get('event') == 'ready', READY_SECONDS)
    cls.game = Game(connection)
    cls.game.request('world.create', {}, timeout=240)
    cls.folder = os.path.join(cls.launched.results, 'looks')
    os.makedirs(cls.folder, exist_ok=True)
    cls.kept = {}

  @classmethod
  def tearDownClass(cls) -> None:
    try:
      with open(os.path.join(cls.folder, 'answers.json'), 'w',
                encoding='utf-8') as file:
        json.dump(cls.kept, file, indent=1, sort_keys=True)
    finally:
      cls.launched.stop()

  def setUp(self) -> None:
    reset(self.game.connection)

  def test_a_faces(self) -> None:
    looks = self.game.blockFaces(
      [Block('minecraft:stone', 0), Block('minecraft:furnace', 0),
       Block('minecraft:wool', 14), Block('minecraft:lever', 0),
       Block('minecraft:nothing_such', 0)], PLACE)
    self.kept['faces'] = looks
    stone, furnace, wool, lever, nothing = looks
    self.assertTrue(stone['cube'])
    self.assertEqual({'stone'}, set(stone['variants'][0]['faces'].values()))
    self.assertEqual(list(range(16)), sorted(
      meta for variant in stone['variants'] for meta in variant['metas']))
    east = [variant['metas'] for variant in furnace['variants']
            if variant['faces']['east'] == 'furnace_front_off']
    self.assertEqual([[5]], east)
    red = [variant['metas'] for variant in wool['variants']
           if variant['faces']['north'] == 'wool_colored_red']
    self.assertEqual([[14]], red)
    self.assertFalse(lever['cube'])
    self.assertIn('error', nothing)

  def test_b_textures(self) -> None:
    icons = self.game.textures(['stone', 'furnace_front_off', 'no_such'])
    self.kept['textures'] = {name: {key: value for key, value in
                                    each.items() if key != 'pixels'}
                             for name, each in icons.items()}
    stone = icons['stone']
    self.assertEqual((16, 16, 256), (stone['width'], stone['height'],
                                     len(stone['pixels'])))
    self.assertIn('error', icons['no_such'])

  def test_c_a_face_squared_up(self) -> None:
    self.game.setBlock(PLACE, MCBlocks.Stone)
    try:
      self.game.look(0, 0)
      view = self.game.view(PLACE, os.path.join(self.folder, 'stone.png'))
      square = view.square('north')
      self.kept['square'] = {'seen': sum(1 for each in square if each),
                             'eye': list(view.eye), 'rect': list(view.rect)}
      self.assertGreater(sum(1 for each in square if each), 200)
      self.assertEqual((None,) * 256, view.square('south'))
    finally:
      self.game.setBlock(PLACE, MCBlocks.Air)


if __name__ == '__main__':
  unittest.main()

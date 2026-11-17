"""
How blocks look on the run's port, from its resource pack (SPEC.md
15.4's identify, 19.7 step 3c): block.faces gives each face's texture
for each meta (1.7.10: a furnace's facings, wool's colours, alike metas
together) or each state, each way the game draws it (26.3: stone plain or
mirrored, turned or not; each face's corners, where its texture lies on
it, and its tint); texture.get each texture's pixels; a view's face
squared up has the block's pixels where the camera says. The answers
are kept beside the results (looks/answers.json). Places written as in
1.7.10's flat world and moved to the port's (ports.at).

  python -m unittas.selftest test_looks.
  (through the watcher: "probe test_looks.", "probe test_looks on 26.3-fabric")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import json
import os
import shutil
import unittest

from mcdex import MCBlocks

from ports import V1_7_10, V26_3, at, probeGame, start, version
from probegame import READY_SECONDS
from unittas.api import Game
from unittas.reset import reset
from unittas.things import blockOf
from unittas.values import Block

PLACE = at(0, 5, 3)
#  each version's textures, by what they are: 1.7.10's icon names, 26.3's
#  texture names
TEXTURES = {
  'stone': {V1_7_10: 'stone', V26_3: 'minecraft:block/stone'},
  'furnace front': {V1_7_10: 'furnace_front_off',
                    V26_3: 'minecraft:block/furnace_front'},
  'red wool': {V1_7_10: 'wool_colored_red',
               V26_3: 'minecraft:block/red_wool'},
  'none': {V1_7_10: 'no_such', V26_3: 'minecraft:block/no_such'},
}
#  which of a block's metas (1.7.10) or states (26.3) a look is drawn for
DRAWN_FOR = {
  'furnace facing east': {V1_7_10: [[5]],
                          V26_3: [[{'facing': 'east', 'lit': 'false'}]]},
  'red wool': {V1_7_10: [[14]], V26_3: [[{}]]},
}


def texture(what: str) -> str:
  return TEXTURES[what][version()]


def drawnFor(variant: dict) -> list:
  """The metas or the states a look is drawn for."""
  return variant['metas'] if 'metas' in variant else variant['states']


class LooksTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = probeGame('looks')
    shutil.rmtree(os.path.join(cls.launched.gameDir, 'saves', 'unittas'),
                  ignore_errors=True)
    connection = cls.launched.start(READY_SECONDS)
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
    reset(self.game.connection, at=start())

  def test_a_faces(self) -> None:
    game = self.game
    blocks = [blockOf(member, game.version, game.declared())[0]
              for member in (MCBlocks.Stone, MCBlocks.Furnace,
                             MCBlocks.RedWool, MCBlocks.Lever)]
    blocks.append(Block('minecraft:nothing_such', blocks[0].meta))
    looks = game.blockFaces(blocks, PLACE)
    self.kept['faces'] = looks
    stone, furnace, wool, lever, nothing = looks
    self.assertTrue(stone['cube'])
    self.assertEqual({texture('stone')}, {
      icon for variant in stone['variants']
      for icon in variant['faces'].values()})
    if version() == V1_7_10:
      self.assertEqual(list(range(16)), sorted(
        meta for variant in stone['variants'] for meta in variant['metas']))
    else:
      #  26.3 draws stone four ways at random: plain or mirrored, turned
      #  half round or not; each face's corners in the block and on its
      #  texture, 0 to 1
      self.assertEqual(4, len(stone['variants']), stone['variants'])
      self.assertEqual([[{}]] * 4, [drawnFor(each)
                                    for each in stone['variants']])
      for variant in stone['variants']:
        for corners in variant['corners'].values():
          self.assertEqual(4, len(corners))
          for corner in corners:
            self.assertEqual(5, len(corner))
            self.assertTrue(all(-1e-6 <= n <= 1 + 1e-6 for n in corner),
                            corner)
    east = [drawnFor(variant) for variant in furnace['variants']
            if variant['faces']['east'] == texture('furnace front')]
    self.assertEqual(DRAWN_FOR['furnace facing east'][version()], east)
    red = [drawnFor(variant) for variant in wool['variants']
           if variant['faces']['north'] == texture('red wool')]
    self.assertEqual(DRAWN_FOR['red wool'][version()], red)
    self.assertFalse(lever['cube'])
    self.assertIn('error', nothing)

  def test_b_textures(self) -> None:
    names = [texture('stone'), texture('furnace front'), texture('none')]
    icons = self.game.textures(names)
    self.kept['textures'] = {name: {key: value for key, value in
                                    each.items() if key != 'pixels'}
                             for name, each in icons.items()}
    stone = icons[texture('stone')]
    self.assertEqual((16, 16, 256), (stone['width'], stone['height'],
                                     len(stone['pixels'])))
    self.assertIn('error', icons[texture('none')])

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

"""
Blocks identified from their looks alone on the run's port (SPEC.md
15.4's identify, 15.6 step 6, 19.7 step 3c): the agent looks at a block
from each side, sets each face square and compares it with every full
cube's faces as the running game draws them, from its own resource pack
(26.3: each way it draws a block, stone plain or mirrored, each face as
its corners and tint say). A furnace, a crafting table and red wool,
among all blocks; stone among all is said to look as infested stone does
(both versions draw that with stone's texture: no player tells them
apart by looks); stone among a given few, bedrock (stone's pattern,
darker and starker) among them; a crafting table among a given few.
Each decision's scores are kept beside the results (identify/notes.txt),
with the views' frames. Places written as in 1.7.10's flat world and
moved to the port's (ports.at).

  python -m unittas.selftest test_identify.
  (through the watcher: "probe test_identify.", "probe test_identify on 26.3-fabric")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from mcdex import MCBlocks

from ports import at, block, probeGame, start
from probegame import READY_SECONDS
from unittas.agent import Agent
from unittas.api import Game
from unittas.errors import TesttimeError
from unittas.reset import reset
from unittas.run import Run

PLACE = at(3, 4, 6)


class _Noted:
  """A run, as far as notes go: kept in a file."""

  def __init__(self, path: str) -> None:
    self.path = path

  def note(self, text: str) -> None:
    with open(self.path, 'a', encoding='utf-8') as file:
      file.write(text + '\n')


class IdentifyTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = probeGame('identify')
    shutil.rmtree(os.path.join(cls.launched.gameDir, 'saves', 'unittas'),
                  ignore_errors=True)
    connection = cls.launched.start(READY_SECONDS)
    connection.events.waitFor(
      lambda event: event.get('event') == 'ready', READY_SECONDS)
    cls.game = Game(connection)
    cls.game.request('world.create', {}, timeout=240)
    folder = os.path.join(cls.launched.results, 'identify')
    os.makedirs(folder, exist_ok=True)
    cls.agent = Agent(cls.game, os.path.join(folder, 'frames'))
    Run.current = _Noted(os.path.join(folder, 'notes.txt'))

  @classmethod
  def tearDownClass(cls) -> None:
    Run.current = None
    cls.launched.stop()

  def setUp(self) -> None:
    reset(self.game.connection, at=start())

  def tearDown(self) -> None:
    self.game.setBlock(PLACE, MCBlocks.Air)

  def identified(self, block, among=None):
    Run.current.note('-- %s' % self._testMethodName)
    self.game.setBlock(PLACE, block)
    return self.agent.identify(PLACE, among)

  def test_a_stone_among_all(self) -> None:
    with self.assertRaises(TesttimeError) as raised:
      self.identified(MCBlocks.Stone)
    self.assertIn('MCBlocks.InfestedStone and MCBlocks.Stone look the same',
                  str(raised.exception))

  def test_b_a_furnace(self) -> None:
    """
    Facing south: 1.7.10 sets a furnace's facing itself as it is added,
    south with nothing around (a meta 5 asked for isn't kept).
    """
    self.assertIs(MCBlocks.Furnace,
                  self.identified(block('furnace facing south')))

  def test_c_a_crafting_table(self) -> None:
    self.assertIs(MCBlocks.CraftingTable,
                  self.identified(MCBlocks.CraftingTable))

  def test_d_red_wool(self) -> None:
    self.assertIs(MCBlocks.RedWool, self.identified(MCBlocks.RedWool))

  def test_f_stone_among_a_given_few(self) -> None:
    self.assertIs(MCBlocks.Stone, self.identified(
      MCBlocks.Stone, among=[MCBlocks.Bedrock, MCBlocks.Cobblestone,
                             MCBlocks.Stone]))

  def test_e_among_a_given_few(self) -> None:
    self.assertIs(MCBlocks.CraftingTable, self.identified(
      MCBlocks.CraftingTable, among=[MCBlocks.Stone, MCBlocks.Furnace,
                                     MCBlocks.CraftingTable]))


if __name__ == '__main__':
  unittest.main()

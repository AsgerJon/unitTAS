"""
The agent's verbs in the development client (SPEC.md 15.6 step 3), on
flat ground, by a player's keys and look alone: using a lever, on and off
again; breaking a block in creative, and nothing behind it; mining one
in survival; placing a block from its hotbar slot, and where the agent
stands (it steps aside); an item not in the hotbar, a TesttimeError. The
world's state is read by command, as an examination is by default.

  python -m unittas.selftest test_verbs.
  (through the watcher: "probe test_verbs.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from mcdex import MCBlocks, MCItems

from probegame import READY_SECONDS, ROOT, results
from unittas.agent import Agent
from unittas.api import Game
from unittas.dev import DevGame
from unittas.errors import TesttimeError
from unittas.reset import reset
from unittas.values import Block, BlockPos

#  a lever on the ground, off (1.7.10's meta 5; 8 is on)
LEVER = Block('minecraft:lever', 5)
AIR = Block('minecraft:air', 0)


class VerbTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = DevGame(ROOT, results(), 'verbs')
    shutil.rmtree(os.path.join(cls.launched.gameDir, 'saves', 'unittas'),
                  ignore_errors=True)
    connection = cls.launched.start()
    connection.events.waitFor(
      lambda event: event.get('event') == 'ready', READY_SECONDS)
    cls.game = Game(connection)
    cls.game.request('world.create', {}, timeout=240)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.launched.stop()

  def setUp(self) -> None:
    reset(self.game.connection)
    self.agent = Agent(self.game)
    self.placed = []

  def tearDown(self) -> None:
    for pos in reversed(self.placed):
      self.game.setBlock(pos, MCBlocks.Air)

  def place(self, pos: tuple, block) -> None:
    self.game.setBlock(pos, block)
    self.placed.append(pos)

  def test_a_uses_a_lever(self) -> None:
    self.place((5, 4, 7), LEVER)
    self.agent.use(BlockPos(5, 4, 7))
    self.assertEqual(13, self.game.block((5, 4, 7)).meta, 'on')
    self.agent.use(BlockPos(5, 4, 7))
    self.assertEqual(5, self.game.block((5, 4, 7)).meta, 'off again')

  def test_b_breaks_a_block_in_creative(self) -> None:
    self.place((3, 4, 6), MCBlocks.Stone)
    self.agent.breakBlock(BlockPos(3, 4, 6))
    self.assertEqual(AIR, self.game.block((3, 4, 6)))
    #  let go in time: nothing behind it broken
    self.game.ticks(10)
    self.assertEqual('minecraft:grass', self.game.block((3, 3, 6)).id)

  def test_c_mines_a_block_in_survival(self) -> None:
    self.game.command('/gamemode 0')
    self.place((3, 4, 6), MCBlocks.Dirt)
    before = self.agent.perceive().tick
    seen = self.agent.breakBlock(BlockPos(3, 4, 6))
    self.assertEqual(AIR, self.game.block((3, 4, 6)))
    #  dirt by hand: 15 ticks of mining
    self.assertGreaterEqual(seen.tick - before, 15)

  def test_d_places_a_block_from_its_slot(self) -> None:
    self.game.setSlot('main.3', MCItems.Stone, 16)
    self.placed.append((4, 4, 6))
    self.agent.place(BlockPos(4, 4, 6), MCItems.Stone)
    self.assertEqual(Block('minecraft:stone', 0),
                     self.game.block((4, 4, 6)))
    self.assertEqual(3, self.game.inventory(side='client').selected)

  def test_e_places_where_it_stands(self) -> None:
    self.game.setSlot('main.0', MCItems.Stone, 16)
    self.placed.append((0, 4, 0))
    self.agent.place(BlockPos(0, 4, 0), MCItems.Stone)
    self.assertEqual('minecraft:stone', self.game.block((0, 4, 0)).id)

  def test_f_not_in_the_hotbar(self) -> None:
    with self.assertRaises(TesttimeError) as raised:
      self.agent.place(BlockPos(4, 4, 6), MCItems.Stone)
    self.assertIn('no MCItems.Stone in the hotbar', str(raised.exception))


if __name__ == '__main__':
  unittest.main()

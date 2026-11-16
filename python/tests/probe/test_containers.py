"""
The agent and containers in the development client (SPEC.md 15.6 step
4), on flat ground, by a player's means alone: a chest opened by using
it, its screen read as it shows the chest; a stack taken and one put by
shift-clicks (container.click), the chest then read by command as the
server holds it; the screen closed as Esc does; a block that isn't a
container, a TesttimeError.

  python -m unittas.selftest test_containers.
  (through the watcher: "probe test_containers.")
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
from unittas.values import BlockPos, Item

CHEST = (3, 4, 5)
#  1.7.10's chest with three pink wool in its first slot
WITH_WOOL = '{Items:[{Slot:0b,id:35s,Count:3b,Damage:6s}]}'


class ContainerTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = DevGame(ROOT, results(), 'containers')
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
    self.game.request('block.set', {
      'pos': list(CHEST), 'block': {'id': 'minecraft:chest', 'meta': 2},
      'tile': WITH_WOOL})
    self.agent = Agent(self.game)

  def tearDown(self) -> None:
    self.game.setBlock(CHEST, MCBlocks.Air)

  def chestItems(self) -> list:
    """The chest's items as the server holds them, by command."""
    return list(self.game.block(CHEST, tile=True).tile['Items'])

  def test_a_opens_a_chest(self) -> None:
    shown = self.agent.open(BlockPos(*CHEST))
    self.assertFalse(shown.playerOwn)
    self.assertEqual(27, len(shown.contents))
    self.assertEqual(Item('minecraft:wool', 3, 6), shown.contents[0])
    self.assertIn('GuiChest', self.game.screen().className)

  def test_b_takes_a_stack(self) -> None:
    self.agent.open(BlockPos(*CHEST))
    taken = self.agent.take(MCItems.PinkWool)
    self.assertEqual(Item('minecraft:wool', 3, 6), taken)
    self.assertEqual([], self.chestItems())
    self.assertIn(taken, self.game.inventory().main)

  def test_c_puts_a_stack(self) -> None:
    self.game.setSlot('main.2', MCItems.Stone, 16)
    self.game.ticks(3)
    self.agent.open(BlockPos(*CHEST))
    put = self.agent.put(MCItems.Stone)
    self.assertEqual(Item('minecraft:stone', 16, 0), put)
    self.agent.close()
    stone = [each for each in self.chestItems() if each['id'] == 1]
    self.assertEqual(1, len(stone), self.chestItems())
    self.assertEqual(16, stone[0]['Count'])
    self.assertTrue(self.game.slot('main.2').empty)

  def test_d_closes_it(self) -> None:
    self.agent.open(BlockPos(*CHEST))
    self.agent.close()
    self.assertIsNone(self.game.screen())
    self.assertTrue(self.game.container().playerOwn)

  def test_e_a_block_that_isn_t_one(self) -> None:
    self.game.setBlock((3, 4, 7), MCBlocks.Stone)
    try:
      with self.assertRaises(TesttimeError) as raised:
        self.agent.open(BlockPos(3, 4, 7))
      self.assertIn('opened no container', str(raised.exception))
    finally:
      self.game.setBlock((3, 4, 7), MCBlocks.Air)


if __name__ == '__main__':
  unittest.main()

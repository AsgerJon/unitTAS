"""
The agent and containers (SPEC.md 15.6 step 4), without a game: a fake
player (fakeplayer.py) whose chests open their screens as 1.7.10's do.
open uses the block and sees its screen open; contents reads it as the
screen shows it; take and put shift-click one stack across, as a player
does, and see it moved; close closes it as Esc does. What can't be done
is a TesttimeError naming what happened.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import unittest

from mcdex import MCItems

from test_agent import PlayedTests
from unittas.errors import TesttimeError
from unittas.values import BlockPos, Item

WOOL = {'id': 'minecraft:wool', 'count': 3, 'meta': 6}
STONE = {'id': 'minecraft:stone', 'count': 16, 'meta': 0}
STICKS = {'id': 'minecraft:stick', 'count': 64, 'meta': 0}
CHEST = (3, 4, 5)


class ContainerTests(PlayedTests):

  def setUp(self) -> None:
    PlayedTests.setUp(self)
    self.player.walls[CHEST] = 'minecraft:chest'
    self.player.chests[CHEST] = [WOOL] + [None] * 26

  def test_opens_a_chest(self) -> None:
    shown = self.agent.open(BlockPos(*CHEST))
    self.assertFalse(shown.playerOwn)
    self.assertEqual(Item('minecraft:wool', 3, 6), shown.contents[0])
    self.assertEqual(shown.contents, self.agent.contents())
    self.assertEqual([('open', CHEST)], self.player.clicks)
    self.assertOnlyAPlayersMeans()

  def test_takes_a_stack(self) -> None:
    self.agent.open(BlockPos(*CHEST))
    taken = self.agent.take(MCItems.PinkWool)
    self.assertEqual(Item('minecraft:wool', 3, 6), taken)
    self.assertIsNone(self.player.chests[CHEST][0])
    self.assertIn(WOOL, self.player.hotbar + self.player.rest)
    self.assertOnlyAPlayersMeans()

  def test_puts_a_stack(self) -> None:
    self.player.hotbar[2] = STONE
    self.agent.open(BlockPos(*CHEST))
    put = self.agent.put(MCItems.Stone)
    self.assertEqual(Item('minecraft:stone', 16, 0), put)
    self.assertEqual(STONE, self.player.chests[CHEST][1])
    self.assertIsNone(self.player.hotbar[2])

  def test_closes_it(self) -> None:
    self.agent.open(BlockPos(*CHEST))
    self.agent.close()
    self.assertIsNone(self.player.screen)
    with self.assertRaises(TesttimeError) as raised:
      self.agent.contents()
    self.assertIn('no container is open', str(raised.exception))
    self.assertOnlyAPlayersMeans()

  def test_what_isn_t_there(self) -> None:
    self.agent.open(BlockPos(*CHEST))
    with self.assertRaises(TesttimeError) as raised:
      self.agent.take(MCItems.Stone)
    message = str(raised.exception)
    self.assertIn('no MCItems.Stone in the container', message)
    self.assertIn('minecraft:wool', message)
    with self.assertRaises(TesttimeError) as raised:
      self.agent.put(MCItems.Stone)
    self.assertIn('no MCItems.Stone in the inventory',
                  str(raised.exception))

  def test_no_room(self) -> None:
    self.player.hotbar = [STICKS] * 9
    self.player.rest = [STICKS] * 27
    self.agent.open(BlockPos(*CHEST))
    with self.assertRaises(TesttimeError) as raised:
      self.agent.take(MCItems.PinkWool)
    self.assertIn('moved none of it', str(raised.exception))

  def test_part_of_a_stack(self) -> None:
    """Room for two of the three: what moved is two, one stays."""
    self.player.hotbar = [STICKS] * 8 + [dict(WOOL, count=62)]
    self.player.rest = [STICKS] * 27
    self.agent.open(BlockPos(*CHEST))
    self.assertEqual(Item('minecraft:wool', 2, 6),
                     self.agent.take(MCItems.PinkWool))
    self.assertEqual(dict(WOOL, count=1), self.player.chests[CHEST][0])

  def test_a_block_that_isn_t_one(self) -> None:
    self.player.walls[(3, 4, 7)] = 'minecraft:stone'
    with self.assertRaises(TesttimeError) as raised:
      self.agent.open(BlockPos(3, 4, 7))
    self.assertEqual('open', raised.exception.step)
    self.assertIn('opened no container', str(raised.exception))


if __name__ == '__main__':
  unittest.main()

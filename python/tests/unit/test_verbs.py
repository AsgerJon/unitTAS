"""
The agent's verbs (SPEC.md 15.6 step 3), without a game: a fake player
(fakeplayer.py) clicks as 1.7.10's does. Each verb infers its approach:
into reach, looking at the block, then the click, by the keys alone.
use right-clicks a block; breakBlock holds the attack key until the
crosshair no longer meets the block, and no longer; place selects the
item's hotbar slot by its key, clicks a face of a block beside the
place, and sees the new block there. What can't be done is a
TesttimeError naming what happened.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import unittest

from mcdex import MCItems

from test_agent import PlayedTests
from unittas.errors import TesttimeError
from unittas.values import BlockPos

STONE = {'id': 'minecraft:stone', 'count': 64, 'meta': 0}
DIRT = {'id': 'minecraft:dirt', 'count': 64, 'meta': 0}
STICK = {'id': 'minecraft:stick', 'count': 1, 'meta': 0}


class UseTests(PlayedTests):

  def test_uses_a_lever(self) -> None:
    self.player.walls[(6, 4, 9)] = 'minecraft:lever'
    self.agent.use(BlockPos(6, 4, 9))
    self.assertEqual({(6, 4, 9): True}, self.player.levers)
    self.assertEqual([('use', (6, 4, 9))], self.player.clicks)
    self.assertGreater(self.player.z, 3.0, 'it walked into reach')
    self.assertOnlyAPlayersMeans()

  def test_a_lever_lower_than_its_block_s_middle(self) -> None:
    """
    26.3's floor lever is 0.375 high and narrow (x 5/16 to 11/16, z 4/16 to
    12/16): a ray through the block's middle, or its faces', passes over
    it, so the agent looks lower, as a player does.
    """
    self.player.walls[(6, 4, 9)] = 'minecraft:lever'
    self.player.lows[(6, 4, 9)] = (5 / 16, 0.0, 4 / 16, 11 / 16, 6 / 16,
                                   12 / 16)
    self.agent.use(BlockPos(6, 4, 9))
    self.assertEqual({(6, 4, 9): True}, self.player.levers)
    self.assertOnlyAPlayersMeans()

  def test_twice_is_off_again(self) -> None:
    self.player.walls[(2, 4, 3)] = 'minecraft:lever'
    self.agent.use(BlockPos(2, 4, 3))
    self.agent.use(BlockPos(2, 4, 3))
    self.assertEqual({(2, 4, 3): False}, self.player.levers)

  def test_using_air(self) -> None:
    with self.assertRaises(TesttimeError) as raised:
      self.agent.use(BlockPos(2, 4, 3))
    self.assertEqual('use', raised.exception.step)
    self.assertIn("isn't targeted", str(raised.exception))
    self.assertEqual([], self.player.clicks)


class BreakTests(PlayedTests):

  def test_in_creative_at_once(self) -> None:
    self.player.walls[(3, 4, 7)] = 'minecraft:stone'
    self.agent.breakBlock(BlockPos(3, 4, 7))
    self.assertNotIn((3, 4, 7), self.player.walls)
    #  and nothing behind it
    self.assertEqual([('broke', (3, 4, 7))], self.player.clicks)
    self.assertOnlyAPlayersMeans()

  def test_by_mining(self) -> None:
    self.player.creative = False
    self.player.hardness = 12
    self.player.walls[(3, 4, 4)] = 'minecraft:stone'
    before = self.player.tick
    self.agent.breakBlock(BlockPos(3, 4, 4))
    self.assertEqual([('broke', (3, 4, 4))], self.player.clicks)
    self.assertGreaterEqual(self.player.tick - before, 12)
    self.assertOnlyAPlayersMeans()

  def test_a_block_that_changes_as_it_is_mined(self) -> None:
    """
    Dirt grown to grass while it is mined (a random tick's, as on 1.21.1 on
    2026-11-18): still a block there, so the mining goes on to the end, as
    a player's does; the crosshair meeting another id is no break.
    """
    self.player.creative = False
    self.player.hardness = 12
    self.player.walls[(3, 4, 4)] = 'minecraft:dirt'
    self.player.becomes[(3, 4, 4)] = (5, 'minecraft:grass')
    self.agent.breakBlock(BlockPos(3, 4, 4))
    self.assertNotIn((3, 4, 4), self.player.walls)
    self.assertEqual([('broke', (3, 4, 4))], self.player.clicks)
    self.assertOnlyAPlayersMeans()

  def test_the_budget_spent(self) -> None:
    self.player.creative = False
    self.player.hardness = 500
    self.player.walls[(3, 4, 4)] = 'minecraft:obsidian'
    with self.assertRaises(TesttimeError) as raised:
      self.agent.breakBlock(BlockPos(3, 4, 4), ticks=40)
    message = str(raised.exception)
    self.assertIn('minecraft:obsidian', message)
    self.assertIn('still there after', message)
    self.assertOnlyAPlayersMeans()


class PlaceTests(PlayedTests):

  def test_on_the_ground(self) -> None:
    self.player.hotbar[3] = STONE
    self.agent.place(BlockPos(4, 4, 6), MCItems.Stone)
    self.assertEqual('minecraft:stone', self.player.walls.get((4, 4, 6)))
    self.assertEqual(3, self.player.selected)
    self.assertEqual([('placed', (4, 4, 6))], self.player.clicks)
    self.assertOnlyAPlayersMeans()

  def test_its_own_slot(self) -> None:
    self.player.hotbar[0] = DIRT
    self.player.hotbar[4] = STONE
    self.agent.place(BlockPos(4, 4, 6), MCItems.Stone)
    self.assertEqual(4, self.player.selected)
    self.assertEqual('minecraft:stone', self.player.walls.get((4, 4, 6)))

  def test_against_a_side(self) -> None:
    """
    Nothing below the place: a block beside it takes the click. From in
    reach, it looks at the place and at each face turned its way, and at
    no face turned away (the west block's east face).
    """
    self.player.x, self.player.z = 2.5, 6.5
    self.player.hotbar[0] = STONE
    self.player.walls[(5, 4, 6)] = 'minecraft:stone'
    self.player.walls[(5, 5, 6)] = 'minecraft:stone'
    self.agent.place(BlockPos(4, 5, 6), MCItems.Stone)
    self.assertEqual([('placed', (4, 5, 6))], self.player.clicks)
    #  the place, then below, south, north, and east's west face
    self.assertEqual(5, self.player.ops.count('player.look'))

  def test_a_click_that_places_nothing(self) -> None:
    self.player.hotbar[0] = STICK
    with self.assertRaises(TesttimeError) as raised:
      self.agent.place(BlockPos(4, 4, 6), MCItems.Stick)
    self.assertIn('placed nothing at (4, 4, 6)', str(raised.exception))

  def test_where_it_stands(self) -> None:
    """A player steps aside first."""
    self.player.hotbar[0] = STONE
    self.agent.place(BlockPos(0, 4, 0), MCItems.Stone)
    self.assertEqual([('placed', (0, 4, 0))], self.player.clicks)
    self.assertFalse(self.player.standsIn((0, 4, 0)))

  def test_nothing_to_place_against(self) -> None:
    self.player.hotbar[0] = STONE
    with self.assertRaises(TesttimeError) as raised:
      self.agent.place(BlockPos(4, 7, 6), MCItems.Stone)
    self.assertIn('nothing to place it against', str(raised.exception))
    self.assertEqual([], self.player.clicks)

  def test_not_in_the_hotbar(self) -> None:
    with self.assertRaises(TesttimeError) as raised:
      self.agent.place(BlockPos(4, 4, 6), MCItems.Stone)
    self.assertIn('no MCItems.Stone in the hotbar', str(raised.exception))
    self.assertEqual([], self.player.clicks)

  def test_a_place_taken(self) -> None:
    self.player.hotbar[0] = STONE
    self.player.walls[(4, 4, 6)] = 'minecraft:dirt'
    with self.assertRaises(TesttimeError) as raised:
      self.agent.place(BlockPos(4, 4, 6), MCItems.Stone)
    self.assertIn('minecraft:dirt is there', str(raised.exception))


if __name__ == '__main__':
  unittest.main()

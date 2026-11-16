"""
The agent over terrain (SPEC.md 15.6 step 7), without a game: a fake
player that steps up half a block, jumps, and falls as 1.7.10's does.
walkTo finds its way from what it perceives: around a wall, up a slab,
up a block by a jump, down off a pillar, to a place further off than it
sees (looking again on the way); and says there is no way when the place
is shut in or too high. The keys only, and every key let go.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import math
import unittest

from test_agent import PlayedTests
from unittas.errors import TesttimeError
from unittas.values import Vec3


class PathTests(PlayedTests):

  def assertAt(self, place: Vec3, within: float = 0.25) -> None:
    short = math.hypot(place.x - self.player.x, place.z - self.player.z)
    self.assertLessEqual(short, within, 'at %.2f, %.2f, %.2f' % (
      self.player.x, self.player.y, self.player.z))
    self.assertAlmostEqual(place.y, self.player.y, places=6)

  def test_around_a_wall(self) -> None:
    for x in range(-3, 4):
      for y in (4, 5):
        self.player.walls[(x, y, 3)] = 'minecraft:stone'
    place = Vec3(0.5, 4.0, 7.5)
    self.agent.walkTo(place)
    self.assertAt(place)
    self.assertOnlyAPlayersMeans()

  def test_up_a_slab(self) -> None:
    self.player.raised[(0, 3)] = 4.5
    place = Vec3(0.5, 4.5, 3.5)
    self.agent.walkTo(place)
    self.assertAt(place)
    self.assertNotIn('key.jump', self.player.ops_keys())

  def test_up_a_block_by_a_jump(self) -> None:
    self.player.raised[(0, 3)] = 5.0
    place = Vec3(0.5, 5.0, 3.5)
    self.agent.walkTo(place)
    self.assertAt(place)
    self.assertIn('key.jump', self.player.ops_keys())
    self.assertOnlyAPlayersMeans()

  def test_down_off_a_pillar(self) -> None:
    self.player.raised[(0, 0)] = 6.0
    self.player.y = 6.0
    place = Vec3(3.5, 4.0, 0.5)
    self.agent.walkTo(place)
    self.assertAt(place)

  def test_further_than_it_sees(self) -> None:
    for z in range(8, 12):
      for y in (4, 5):
        self.player.walls[(10, y, z)] = 'minecraft:stone'
    place = Vec3(20.5, 4.0, 10.5)
    self.agent.walkTo(place)
    self.assertAt(place)
    self.assertGreater(self.player.ops.count('player.perceive'), 2)

  def test_no_way_up_two(self) -> None:
    self.player.raised[(0, 3)] = 6.0
    with self.assertRaises(TesttimeError) as raised:
      self.agent.walkTo(Vec3(0.5, 6.0, 3.5))
    self.assertEqual('walkTo', raised.exception.step)
    self.assertIn('no way to (0.50, 6.00, 3.50)', str(raised.exception))

  def test_no_way_in(self) -> None:
    for x in range(2, 7):
      for y in (4, 5):
        self.player.walls[(x, y, 4)] = 'minecraft:stone'
        self.player.walls[(x, y, 8)] = 'minecraft:stone'
    for z in range(5, 8):
      for y in (4, 5):
        self.player.walls[(2, y, z)] = 'minecraft:stone'
        self.player.walls[(6, y, z)] = 'minecraft:stone'
    with self.assertRaises(TesttimeError) as raised:
      self.agent.walkTo(Vec3(4.5, 4.0, 6.5))
    self.assertIn('no way to', str(raised.exception))
    self.assertEqual(set(), self.player.keys)


if __name__ == '__main__':
  unittest.main()

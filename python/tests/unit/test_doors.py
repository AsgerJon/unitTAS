"""
The agent and doors (SPEC.md 15.6 step 7), without a game: a fake player
whose wooden doors open and shut by a click (their box along one edge or
another), in a wall with no other way through. walkTo goes through: a
shut door opened first, an open one left as it is; a door that blocks
open or shut is a TesttimeError; an iron door, which no hand opens, is a
wall: no way.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import math
import unittest

from test_agent import PlayedTests
from unittas.errors import TesttimeError
from unittas.values import Vec3

THROUGH = Vec3(0.5, 4.0, 6.5)


class DoorTests(PlayedTests):

  def setUp(self) -> None:
    PlayedTests.setUp(self)
    for x in range(-8, 9):
      if x != 0:
        for y in (4, 5):
          self.player.walls[(x, y, 3)] = 'minecraft:stone'

  def assertThrough(self) -> None:
    short = math.hypot(THROUGH.x - self.player.x, THROUGH.z - self.player.z)
    self.assertLessEqual(short, 0.25)

  def test_a_shut_door_opened(self) -> None:
    self.player.doors[(0, 3)] = {'open': False}
    self.agent.walkTo(THROUGH)
    self.assertThrough()
    self.assertEqual([('door', (0, 4, 3))], self.player.clicks)
    self.assertTrue(self.player.doors[(0, 3)]['open'])
    self.assertOnlyAPlayersMeans()

  def test_an_open_door_left_open(self) -> None:
    self.player.doors[(0, 3)] = {'open': True}
    self.agent.walkTo(THROUGH)
    self.assertThrough()
    self.assertEqual([], self.player.clicks)

  def test_a_door_that_blocks_either_way(self) -> None:
    self.player.doors[(0, 3)] = {'open': False, 'stuck': True}
    with self.assertRaises(TesttimeError) as raised:
      self.agent.walkTo(THROUGH)
    self.assertIn("the door at (0, 4, 3) doesn't let the agent through",
                  str(raised.exception))
    self.assertEqual(set(), self.player.keys)

  def test_an_iron_door_is_a_wall(self) -> None:
    self.player.doors[(0, 3)] = {'open': False, 'hand': False}
    with self.assertRaises(TesttimeError) as raised:
      self.agent.walkTo(THROUGH)
    self.assertIn('no way to', str(raised.exception))
    self.assertEqual([], self.player.clicks)


if __name__ == '__main__':
  unittest.main()

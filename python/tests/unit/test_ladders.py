"""
The agent and ladders (SPEC.md 15.6 step 7), without a game: a fake
player with a wall four high across z 3 and a ladder up its north face
at x 0 (its blocks at z 2, their boxes along their south edge). walkTo
climbs it onto the wall from wherever it starts, and comes down it,
slowly (never landing hard); a ladder that stops short of the top is no
way up, and the wall without one no way down. Slipping off it on the way
down is a TesttimeError.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import unittest

from test_agent import PlayedTests
from unittas.errors import TesttimeError
from unittas.values import Vec3

TOP = Vec3(0.5, 8.0, 3.5)
BELOW = Vec3(0.5, 4.0, 0.5)
#  The fastest a player lands from a ladder: it slides at 0.15 a tick at
#  most (a fall from the wall's top lands at 0.6)
SLIDE = 0.2


class LadderTests(PlayedTests):

  def setUp(self) -> None:
    PlayedTests.setUp(self)
    for x in range(-8, 9):
      self.player.raised[(x, 3)] = 8.0

  def ladder(self, ys: range = range(4, 8)) -> None:
    for y in ys:
      self.player.ladders[(0, y, 2)] = 'south'

  def onTop(self, x: float = 0.5) -> None:
    self.player.x, self.player.y, self.player.z = x, 8.0, 3.5

  def test_up_a_ladder(self) -> None:
    self.ladder()
    for start in (BELOW, Vec3(4.5, 4.0, 0.5), Vec3(-3.5, 4.0, 1.5)):
      with self.subTest(start=start):
        self.player.x, self.player.y, self.player.z = start.x, 4.0, start.z
        self.agent.walkTo(TOP)
        self.assertThere(TOP)
        self.assertEqual(8.0, self.player.y)
        self.assertEqual(set(), self.player.keys)
    self.assertNotIn('key.jump', self.player.keysAsked)
    self.assertOnlyAPlayersMeans()

  def test_down_a_ladder(self) -> None:
    self.ladder()
    for x in (0.5, 0.3, -2.5, 3.5):
      with self.subTest(x=x):
        self.onTop(x)
        self.player.landed = []
        self.agent.walkTo(BELOW)
        self.assertThere(BELOW)
        self.assertEqual(4.0, self.player.y)
        self.assertLess(max(self.player.landed), SLIDE, 'landed hard')
    self.assertOnlyAPlayersMeans()

  def test_held_over_it_drifting(self) -> None:
    """
    No edge holds the sneaking player: it goes over moving, and the
    drift (11 times its motion, in the air) would take it off the
    ladder's block unless it pushes against it.
    """
    self.ladder()
    self.player.edged = lambda d, alongX: d
    self.onTop()
    self.agent.walkTo(BELOW)
    self.assertThere(BELOW)
    self.assertLess(max(self.player.landed), SLIDE, 'landed hard')

  def test_slipped_off(self) -> None:
    """A ladder whose block doesn't hold the player: it falls past it."""
    self.ladder()
    self.player.onLadder = lambda: False
    self.onTop()
    with self.assertRaises(TesttimeError) as raised:
      self.agent.walkTo(BELOW)
    self.assertIn('slipped off the ladder at (0, 7, 2)',
                  str(raised.exception))
    self.assertEqual(set(), self.player.keys)

  def test_not_up_a_short_ladder(self) -> None:
    self.ladder(range(4, 6))
    with self.assertRaises(TesttimeError) as raised:
      self.agent.walkTo(TOP)
    self.assertIn('no way to', str(raised.exception))
    self.assertEqual(set(), self.player.keys)

  def test_not_down_without_one(self) -> None:
    self.onTop()
    with self.assertRaises(TesttimeError) as raised:
      self.agent.walkTo(BELOW)
    self.assertIn('no way to', str(raised.exception))
    self.assertEqual(8.0, self.player.y)


if __name__ == '__main__':
  unittest.main()

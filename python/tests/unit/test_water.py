"""
The agent and water (SPEC.md 15.6 step 7), without a game: a fake player
with a trench across the way, z 2 to 4 from x -8 to 8, of water one or
two deep to the ground's top. walkTo swims across and climbs out onto
the far bank, holding jump in the water (its head up) and never pressing
it twice quickly (creative's player would fly). A trench of lava is no
way, nor is a bank higher than the water.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import unittest

from test_agent import PlayedTests
from unittas.errors import TesttimeError
from unittas.values import Vec3

FAR = Vec3(0.5, 4.0, 6.5)


class WaterTests(PlayedTests):

  def trench(self, deep: int = 1, kind: str = 'water') -> None:
    liquid = self.player.water if kind == 'water' else self.player.lava
    for x in range(-8, 9):
      for z in (2, 3, 4):
        for y in range(4 - deep, 4):
          self.player.dug.add((x, y, z))
          liquid.add((x, y, z))

  def assertAcross(self, place: Vec3) -> None:
    self.assertThere(place)
    self.assertEqual(4.0, self.player.y)
    self.assertTrue(self.player.swam, 'it swam')
    self.assertOnlyAPlayersMeans()

  def test_across_shallow_water(self) -> None:
    self.trench()
    self.agent.walkTo(FAR)
    self.assertAcross(FAR)

  def test_across_deep_water(self) -> None:
    self.trench(deep=2)
    self.agent.walkTo(FAR)
    self.assertAcross(FAR)

  def test_across_it_aslant(self) -> None:
    self.trench(deep=2)
    self.player.x = -3.5
    place = Vec3(4.5, 4.0, 7.5)
    self.agent.walkTo(place)
    self.assertAcross(place)

  def test_back_again(self) -> None:
    """Across and back: jump held and let go twice, never too soon."""
    self.trench()
    self.agent.walkTo(FAR)
    self.agent.walkTo(Vec3(0.5, 4.0, 0.5))
    self.assertAcross(Vec3(0.5, 4.0, 0.5))

  def test_never_into_lava(self) -> None:
    self.trench(kind='lava')
    with self.assertRaises(TesttimeError) as raised:
      self.agent.walkTo(FAR)
    self.assertIn('no way to', str(raised.exception))
    self.assertEqual(0.5, self.player.z)

  def test_not_out_onto_a_higher_bank(self) -> None:
    self.trench()
    for x in range(-8, 9):
      self.player.raised[(x, 5)] = 5.0
    with self.assertRaises(TesttimeError) as raised:
      self.agent.walkTo(Vec3(0.5, 5.0, 5.5))
    self.assertIn('no way to', str(raised.exception))
    self.assertFalse(self.player.swam)


if __name__ == '__main__':
  unittest.main()

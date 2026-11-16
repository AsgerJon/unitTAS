"""
The agent and water on the run's port (SPEC.md 15.6 step 7, 19.7): a
trench across the way, z 2 to 4 from x -8 to 8 (all the agent sees
across), in the ground, filled to its top. The agent swims across a
trench of water one deep and one two deep, and climbs out onto the far
bank, dry and not flying; a trench of lava is no way. The ground is put
back after each.

  python -m unittas.selftest test_water.
  (through the watcher: "probe test_water.", "probe test_water on 26.3-fabric")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import math
import os
import shutil
import unittest

from mcdex import MCBlocks

from ports import at, point, probeGame, start
from probegame import READY_SECONDS
from unittas.agent import Agent
from unittas.api import Game
from unittas.errors import TesttimeError
from unittas.reset import reset

FAR = point(0.5, 4.0, 6.5)


class WaterTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = probeGame('water')
    shutil.rmtree(os.path.join(cls.launched.gameDir, 'saves', 'unittas'),
                  ignore_errors=True)
    connection = cls.launched.start(READY_SECONDS)
    connection.events.waitFor(
      lambda event: event.get('event') == 'ready', READY_SECONDS)
    cls.game = Game(connection)
    cls.game.request('world.create', {}, timeout=240)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.launched.stop()

  def setUp(self) -> None:
    reset(self.game.connection, at=start())
    self.agent = Agent(self.game)
    self.replaced = []

  def tearDown(self) -> None:
    for pos, block in reversed(self.replaced):
      self.game.setBlock(pos, block)

  def trench(self, kind: str = 'water', deep: int = 1) -> None:
    """The trench dug and filled, its deepest blocks first."""
    for y in range(4 - deep, 4):
      for x in range(-8, 9):
        for z in (2, 3, 4):
          pos = at(x, y, z)
          self.replaced.append((pos, self.game.block(pos)))
          self.game.setBlock(pos, MCBlocks.Water if kind == 'water' else MCBlocks.Lava)

  def assertAcross(self, seen) -> None:
    short = math.hypot(FAR.x - seen.pos.x, FAR.z - seen.pos.z)
    self.assertLessEqual(short, 0.25, 'at %s' % (seen.pos,))
    self.assertAlmostEqual(FAR.y, seen.pos.y, 3)
    self.assertFalse(seen.inWater)
    self.assertFalse(seen.flying)

  def test_a_across_shallow_water(self) -> None:
    self.trench()
    self.assertAcross(self.agent.walkTo(FAR))

  def test_b_across_deep_water(self) -> None:
    self.trench(deep=2)
    self.assertAcross(self.agent.walkTo(FAR))

  def test_c_never_into_lava(self) -> None:
    self.trench(kind='lava')
    with self.assertRaises(TesttimeError) as raised:
      self.agent.walkTo(FAR)
    self.assertIn('no way to', str(raised.exception))
    self.assertFalse(self.agent.perceive().inLava)


if __name__ == '__main__':
  unittest.main()

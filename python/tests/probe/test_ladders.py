"""
The agent and ladders on the run's port (SPEC.md 15.6 step 7, 19.7):
a wall four high across z 3, a ladder up its north face at x 0 (meta 2,
on the wall at its south). The agent climbs it onto the wall, and comes
down it from the wall's top without slipping off; a ladder that stops
two short of the top is no way up.

  python -m unittas.selftest test_ladders.
  (through the watcher: "probe test_ladders.", "probe test_ladders on 26.3-fabric")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import math
import os
import shutil
import unittest

from mcdex import MCBlocks

from ports import at, block, point, probeGame, start
from probegame import READY_SECONDS
from unittas.agent import Agent
from unittas.api import Game
from unittas.errors import TesttimeError
from unittas.reset import reset
from unittas.values import Vec3

TOP = point(0.5, 8.0, 3.5)
BELOW = point(0.5, 4.0, 0.5)


class LadderTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = probeGame('ladders')
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
    self.placed = []

  def tearDown(self) -> None:
    for pos in reversed(self.placed):
      self.game.setBlock(pos, MCBlocks.Air)

  def place(self, pos: tuple, block) -> None:
    """The block at pos, written in 1.7.10's flat world, on the port's."""
    pos = at(*pos)
    self.game.setBlock(pos, block)
    self.placed.append(pos)

  def wall(self, ladder: range) -> None:
    """The wall, then the ladder's blocks on it (a ladder needs it)."""
    for x in range(-3, 4):
      for y in range(4, 8):
        self.place((x, y, 3), MCBlocks.Stone)
    for y in ladder:
      self.place((0, y, 2), block('ladder facing north'))

  def assertAt(self, place: Vec3, seen) -> None:
    short = math.hypot(place.x - seen.pos.x, place.z - seen.pos.z)
    self.assertLessEqual(short, 0.25, 'at %s' % (seen.pos,))
    self.assertAlmostEqual(place.y, seen.pos.y, 3)

  def test_a_up_a_ladder(self) -> None:
    self.wall(range(4, 8))
    self.assertAt(TOP, self.agent.walkTo(TOP))

  def test_b_down_a_ladder(self) -> None:
    self.wall(range(4, 8))
    self.game.teleport(TOP)
    self.assertAt(BELOW, self.agent.walkTo(BELOW))

  def test_c_a_short_ladder(self) -> None:
    self.wall(range(4, 6))
    with self.assertRaises(TesttimeError) as raised:
      self.agent.walkTo(TOP)
    self.assertIn('no way to', str(raised.exception))


if __name__ == '__main__':
  unittest.main()

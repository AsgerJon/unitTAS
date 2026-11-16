"""
The agent and doors on the run's port (SPEC.md 15.6 step 7, 19.7):
a wall with one way through, a wooden door shut in it, opened by the
agent's click and walked through (read open by command after); a fence
gate the same; an iron door, which no hand opens: no way.

  python -m unittas.selftest test_doors.
  (through the watcher: "probe test_doors.", "probe test_doors on 26.3-fabric")
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

THROUGH = point(0.5, 4.0, 6.5)


class DoorTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = probeGame('doors')
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

  def wall(self, block) -> None:
    """A wall across the way, two high, its middle left for a door."""
    for x in range(-8, 9):
      if x != 0:
        for y in (4, 5):
          self.place((x, y, 3), block)

  def assertOpen(self, pos) -> None:
    """Open, read by command: 1.7.10's meta bit 4, 26.3's state."""
    there = self.game.block(pos)
    if there.state:
      self.assertEqual('true', there.properties['open'], there)
    else:
      self.assertEqual(4, there.meta & 4, there)

  def assertThrough(self, seen) -> None:
    short = math.hypot(THROUGH.x - seen.pos.x, THROUGH.z - seen.pos.z)
    self.assertLessEqual(short, 0.25, 'at %s' % (seen.pos,))

  def test_a_a_wooden_door(self) -> None:
    self.wall(MCBlocks.Stone)
    #  the top half first: a bottom half alone falls apart
    self.place((0, 5, 3), block('wooden door, upper'))
    self.place((0, 4, 3), block('wooden door, lower'))
    self.assertThrough(self.agent.walkTo(THROUGH))
    self.assertOpen(at(0, 4, 3))

  def test_b_a_fence_gate(self) -> None:
    self.wall(MCBlocks.OakFence)
    self.place((0, 4, 3), block('fence gate'))
    self.assertThrough(self.agent.walkTo(THROUGH))
    self.assertOpen(at(0, 4, 3))

  def test_c_an_iron_door(self) -> None:
    self.wall(MCBlocks.Stone)
    self.place((0, 5, 3), block('iron door, upper'))
    self.place((0, 4, 3), block('iron door, lower'))
    with self.assertRaises(TesttimeError) as raised:
      self.agent.walkTo(THROUGH)
    self.assertIn('no way to', str(raised.exception))


if __name__ == '__main__':
  unittest.main()

"""
The agent and doors in the development client (SPEC.md 15.6 step 7):
a wall with one way through, a wooden door shut in it, opened by the
agent's click and walked through (read open by command after); a fence
gate the same; an iron door, which no hand opens: no way.

  python -m unittas.selftest test_doors.
  (through the watcher: "probe test_doors.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import math
import os
import shutil
import unittest

from mcdex import MCBlocks

from probegame import READY_SECONDS, ROOT, results
from unittas.agent import Agent
from unittas.api import Game
from unittas.dev import DevGame
from unittas.errors import TesttimeError
from unittas.reset import reset
from unittas.values import Block, Vec3

THROUGH = Vec3(0.5, 4.0, 6.5)


class DoorTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = DevGame(ROOT, results(), 'doors')
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
    self.agent = Agent(self.game)
    self.placed = []

  def tearDown(self) -> None:
    for pos in reversed(self.placed):
      self.game.setBlock(pos, MCBlocks.Air)

  def place(self, pos: tuple, block) -> None:
    self.game.setBlock(pos, block)
    self.placed.append(pos)

  def wall(self, block) -> None:
    """A wall across the way, two high, its middle left for a door."""
    for x in range(-8, 9):
      if x != 0:
        for y in (4, 5):
          self.place((x, y, 3), block)

  def assertThrough(self, seen) -> None:
    short = math.hypot(THROUGH.x - seen.pos.x, THROUGH.z - seen.pos.z)
    self.assertLessEqual(short, 0.25, 'at %s' % (seen.pos,))

  def test_a_a_wooden_door(self) -> None:
    self.wall(MCBlocks.Stone)
    #  the top half first: a bottom half alone falls apart
    self.place((0, 5, 3), Block('minecraft:wooden_door', 8))
    self.place((0, 4, 3), Block('minecraft:wooden_door', 1))
    self.assertThrough(self.agent.walkTo(THROUGH))
    self.assertEqual(4, self.game.block((0, 4, 3)).meta & 4, 'open')

  def test_b_a_fence_gate(self) -> None:
    self.wall(MCBlocks.OakFence)
    self.place((0, 4, 3), Block('minecraft:fence_gate', 0))
    self.assertThrough(self.agent.walkTo(THROUGH))
    self.assertEqual(4, self.game.block((0, 4, 3)).meta & 4, 'open')

  def test_c_an_iron_door(self) -> None:
    self.wall(MCBlocks.Stone)
    self.place((0, 5, 3), Block('minecraft:iron_door', 8))
    self.place((0, 4, 3), Block('minecraft:iron_door', 1))
    with self.assertRaises(TesttimeError) as raised:
      self.agent.walkTo(THROUGH)
    self.assertIn('no way to', str(raised.exception))


if __name__ == '__main__':
  unittest.main()

"""
The agent walking on the run's port (SPEC.md 15.6 step 2, 19.7), on flat
ground, by a player's inputs alone (the keys and the look) and what it
perceives: to a place and still there, as the server sees it too; with a
close margin; around a wall; into reach of a block and looking at it
until the crosshair targets it; not seeing a block behind another, a
TesttimeError; the tick budget spent. Places written as in 1.7.10's flat
world and moved to the port's (ports.at, ports.point).

  python -m unittas.selftest test_walk.
  (through the watcher: "probe test_walk.", "probe test_walk on 26.3-fabric")
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
from unittas.values import Block, Vec3


class WalkTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = probeGame('walk')
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

  def assertThere(self, place: Vec3, at: Vec3, within: float) -> None:
    short = math.hypot(place.x - at.x, place.z - at.z)
    self.assertLessEqual(short, within, 'at %s' % (at,))

  def test_a_walks_to_a_place(self) -> None:
    place = point(6.5, 4.0, 4.5)
    before = self.agent.perceive()
    seen = self.agent.walkTo(place)
    self.assertThere(place, seen.pos, 0.25)
    #  in about the ticks the fake player takes (fakeplayer.py: 46), well
    #  inside its budget (100 and 12 a block: 187); kept for the record
    took = seen.tick - before.tick
    with open(os.path.join(self.launched.results, 'walk-ticks.txt'), 'a',
              encoding='utf-8') as file:
      file.write('walkTo %s: %d ticks, ended at %s\n' % (place, took,
                                                        seen.pos))
    self.assertLessEqual(took, 80)
    #  a player's walk: the server has it from the client's packets
    self.game.ticks(5)
    self.assertThere(place, self.game.player().pos, 0.3)

  def test_b_a_close_margin(self) -> None:
    place = point(-3.25, 4.0, -2.75)
    seen = self.agent.walkTo(place, within=0.1)
    self.assertThere(place, seen.pos, 0.1)

  def test_c_a_wall_in_the_way(self) -> None:
    """Walked around, its way found (SPEC.md 15.6 step 7)."""
    for x in range(-3, 4):
      for y in (4, 5):
        self.place((x, y, 3), MCBlocks.Stone)
    place = point(0.5, 4.0, 8.5)
    self.assertThere(place, self.agent.walkTo(place).pos, 0.25)

  def test_d_into_reach_and_looking_at_a_block(self) -> None:
    block = at(6, 4, 9)
    self.place((6, 4, 9), MCBlocks.RedWool)
    seen = self.agent.reach(block)
    centre = (6.5, block.y + 0.5, 9.5)
    far = math.dist((seen.eye.x, seen.eye.y, seen.eye.z), centre)
    self.assertLessEqual(far, seen.blockReach)
    looked = self.agent.lookAt(block)
    self.assertEqual('block', looked.target.kind)
    self.assertEqual(block, looked.target.pos)
    target = Block(looked.target.id, looked.target.meta, state=looked.target.state)
    self.assertIn(MCBlocks.RedWool, self.game.membersOf(target))

  def test_e_a_block_behind_another(self) -> None:
    self.place((0, 5, 4), MCBlocks.RedWool)
    for x in (-1, 0, 1):
      for y in (4, 5, 6):
        self.place((x, y, 3), MCBlocks.Stone)
    with self.assertRaises(TesttimeError) as raised:
      self.agent.lookAt(at(0, 5, 4))
    wall = at(0, 5, 3)
    self.assertIn('minecraft:stone at (%d, %d, %d)' % (wall.x, wall.y, wall.z), str(raised.exception))

  def test_f_the_budget_spent(self) -> None:
    with self.assertRaises(TesttimeError) as raised:
      self.agent.walkTo(point(0.5, 4.0, 30.5), ticks=10)
    self.assertIn('tick budget (10) is spent', str(raised.exception))


if __name__ == '__main__':
  unittest.main()

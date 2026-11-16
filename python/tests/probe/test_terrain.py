"""
The agent over terrain in the development client (SPEC.md 15.6 step 7),
by a player's keys and look alone, its way found from what it perceives:
around a wall; up a slab, as the game steps; up a block, by a jump; down
off a pillar; to a place further off than it sees, looking again on the
way; and no way into a place walled in, a TesttimeError.

  python -m unittas.selftest test_terrain.
  (through the watcher: "probe test_terrain.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import json
import math
import os
import shutil
import unittest

from mcdex import MCBlocks

from probegame import READY_SECONDS, ROOT, results
from unittas.agent import Agent
from unittas.api import Game
from unittas.dev import DevGame
from unittas.codec import fromJson
from unittas.errors import TesttimeError
from unittas.perception import Perception
from unittas.terrain import Terrain
from unittas.reset import reset
from unittas.values import Block, Vec3


class TerrainTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = DevGame(ROOT, results(), 'terrain')
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


  def assertAt(self, place: Vec3, seen) -> None:
    short = math.hypot(place.x - seen.pos.x, place.z - seen.pos.z)
    self.assertLessEqual(short, 0.25, 'at %s' % (seen.pos,))
    self.assertAlmostEqual(place.y, seen.pos.y, places=3)

  def test_0_what_it_sees(self) -> None:
    """The ground as the agent perceives it, wide: kept, and read."""
    self.place((0, 4, 3), MCBlocks.Stone)
    wire = self.game.request('player.perceive',
                             {'around': 8, 'below': 3, 'above': 3})
    folder = os.path.join(self.launched.results, 'terrain')
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, 'perceived.json'), 'w',
              encoding='utf-8') as file:
      json.dump(wire, file, indent=1)
    seen = fromJson(Perception, wire)
    here = Terrain(seen, 8, 3, 3)
    self.assertEqual(((4.0,), (5.0,), (4.0,)), (
      here.floors(0, 2), here.floors(0, 3), here.floors(0, 0)),
      [each for each in seen.blocks if (each.pos.x, each.pos.z) == (0, 3)])

  def test_a_around_a_wall(self) -> None:
    for x in range(-3, 4):
      for y in (4, 5):
        self.place((x, y, 3), MCBlocks.Stone)
    place = Vec3(0.5, 4.0, 7.5)
    self.assertAt(place, self.agent.walkTo(place))

  def test_b_up_a_slab(self) -> None:
    self.place((0, 4, 3), Block('minecraft:stone_slab', 0))
    place = Vec3(0.5, 4.5, 3.5)
    self.assertAt(place, self.agent.walkTo(place))

  def test_c_up_a_block_by_a_jump(self) -> None:
    self.place((0, 4, 3), MCBlocks.Stone)
    place = Vec3(0.5, 5.0, 3.5)
    self.assertAt(place, self.agent.walkTo(place))

  def test_d_down_off_a_pillar(self) -> None:
    for y in (4, 5):
      self.place((0, y, 0), MCBlocks.Stone)
    #  the setup stands the player on it
    self.game.teleport((0.5, 6.0, 0.5))
    place = Vec3(3.5, 4.0, 0.5)
    self.assertAt(place, self.agent.walkTo(place))

  def test_e_further_than_it_sees(self) -> None:
    for z in range(8, 12):
      for y in (4, 5):
        self.place((10, y, z), MCBlocks.Stone)
    place = Vec3(20.5, 4.0, 10.5)
    self.assertAt(place, self.agent.walkTo(place))

  def test_f_no_way_in(self) -> None:
    for x in range(2, 7):
      for z in (4, 8):
        for y in (4, 5):
          self.place((x, y, z), MCBlocks.Stone)
    for z in range(5, 8):
      for x in (2, 6):
        for y in (4, 5):
          self.place((x, y, z), MCBlocks.Stone)
    with self.assertRaises(TesttimeError) as raised:
      self.agent.walkTo(Vec3(4.5, 4.0, 6.5))
    self.assertIn('no way to (4.50, 4.00, 6.50)', str(raised.exception))


if __name__ == '__main__':
  unittest.main()

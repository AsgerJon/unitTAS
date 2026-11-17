"""
What the player perceives (player.perceive, SPEC.md 15.6 step 1) on the
run's port (19.7), on flat ground: the crosshair's target by the game's
own pick (the ground below, a wall's face ahead, a minecart, nothing
when looking up), the player's eye, box and reach, running into a wall
as the game collides it, and the blocks around it as the game collides
with them (the ground, a wall, a flower and water that stop nothing, a
ladder that is climbed). Places written as in 1.7.10's flat world and
moved to the port's (ports.at), things by mcdex member. The answers seen
are saved as <results>/perceive/perceptions.json, the unit tests'
fixtures (python/tests/unit/fixtures/perceptions.json for 1.7.10,
perceptions-26.3.json for 26.3, copied from a run).

  python -m unittas.selftest test_perceive.
  (through the watcher: "probe test_perceive.",
  "probe test_perceive on 26.3-fabric")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import json
import math
import os
import shutil
import unittest

from mcdex import MCBlocks, MCEntities

from ports import V1_7_10, V1_21_1, V26_3, at, block, lift, probeGame, start, version
from probegame import READY_SECONDS
from unittas.api import Game
from unittas.box import Box
from unittas.codec import fromJson, toJson
from unittas.perception import Perception
from unittas.reset import reset
from unittas.things import entityOf
from unittas.values import Vec3

#  the client player's eye above its feet, and its box, standing
EYE = 1.62
WIDTH = 0.6
HEIGHT = 1.8
#  a creative player's reach, blocks and entities: 6 for entities in 1.7.10, 5 from 1.20.5's attributes on
REACH = {V1_7_10: (5.0, 6.0), V1_21_1: (5.0, 5.0), V26_3: (5.0, 5.0)}


class PerceiveTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = probeGame('perceive')
    shutil.rmtree(os.path.join(cls.launched.gameDir, 'saves', 'unittas'),
                  ignore_errors=True)
    connection = cls.launched.start(READY_SECONDS)
    connection.events.waitFor(
      lambda event: event.get('event') == 'ready', READY_SECONDS)
    cls.game = Game(connection)
    cls.game.request('world.create', {}, timeout=240)
    cls.recorded = []

  @classmethod
  def tearDownClass(cls) -> None:
    try:
      folder = os.path.join(cls.launched.results, 'perceive')
      os.makedirs(folder, exist_ok=True)
      path = os.path.join(folder, 'perceptions.json')
      with open(path, 'w', encoding='utf-8') as file:
        json.dump(cls.recorded, file, indent=1, sort_keys=True)
    finally:
      cls.launched.stop()

  def setUp(self) -> None:
    reset(self.game.connection, at=start())

  def perceived(self, around: int = 2) -> Perception:
    """The answer read, checked to write back as it came, and recorded."""
    wire = self.game.request('player.perceive', {'around': around})
    seen = fromJson(Perception, wire)
    self.assertEqual(wire, toJson(seen))
    self.recorded.append(wire)
    return seen

  def near(self, seen: Perception, pos: tuple):
    """The block perceived at pos; a failure when none was."""
    found = [each for each in seen.blocks if each.pos == at(*pos)]
    self.assertEqual(1, len(found), '%s among %s' % (pos, seen.blocks))
    return found[0]

  def test_a_the_ground_below(self) -> None:
    self.game.look(0, 90)
    seen = self.perceived()
    self.assertEqual('block', seen.target.kind)
    self.assertEqual(at(0, 3, 0), seen.target.pos)
    self.assertEqual('up', seen.target.face)
    self.assertAlmostEqual(lift(4.0), seen.target.hit.y, places=6)
    self.assertTrue(seen.onGround)
    self.assertAlmostEqual(seen.pos.y + EYE, seen.eye.y, places=4)
    box = seen.box
    self.assertAlmostEqual(WIDTH, box.maxX - box.minX, places=4)
    self.assertAlmostEqual(HEIGHT, box.maxY - box.minY, places=4)
    self.assertAlmostEqual(seen.pos.y, box.minY, places=6)
    self.assertEqual(REACH[version()], (seen.blockReach, seen.entityReach))
    ground = self.near(seen, (0, 3, 0))
    self.assertEqual((Box(0.0, lift(3.0), 0.0, 1.0, lift(4.0), 1.0),), ground.boxes)
    #  around 2: the 5 by 5 under the feet, and nothing above it
    self.assertEqual(25, len(seen.blocks))
    self.assertEqual({at(0, 3, 0).y}, {each.pos.y for each in seen.blocks})

  def test_b_a_wall_ahead(self) -> None:
    wall = [at(0, 4, 2), at(0, 5, 2)]
    for pos in wall:
      self.game.setBlock(pos, MCBlocks.Stone)
    try:
      self.game.look(0, 0)
      seen = self.perceived()
      #  yaw 0 looks south (+z): the upper stone's north face, at eye height
      self.assertEqual(at(0, 5, 2), seen.target.pos)
      self.assertEqual('north', seen.target.face)
      self.assertAlmostEqual(2.0, seen.target.hit.z, places=6)
      self.assertEqual('minecraft:stone', seen.target.id)
      self.assertTrue(self.near(seen, (0, 4, 2)).solid)
      self.assertEqual(lift(5.0), self.near(seen, (0, 4, 2)).top)
      self.assertFalse(seen.collidedHorizontally)
      self.game.keyDown('key.forward')
      try:
        self.game.ticks(20)
        walked = self.perceived()
      finally:
        self.game.keyUp('key.forward')
      #  against the wall: stopped there by the game
      self.assertTrue(walked.collidedHorizontally)
      self.assertAlmostEqual(2.0, walked.box.maxZ, places=6)
    finally:
      for pos in wall:
        self.game.setBlock(pos, MCBlocks.Air)

  def test_c_an_entity_ahead(self) -> None:
    cart = self.game.spawn(MCEntities.Minecart, (0.5, lift(4.0), 2.5))
    try:
      self.game.ticks(2)
      eye = self.perceived().eye
      drop = eye.y - lift(4.35)
      self.game.look(0, math.degrees(math.atan2(drop, 2.0)))
      seen = self.perceived()
      self.assertEqual('entity', seen.target.kind)
      self.assertEqual(cart.entity, seen.target.entity)
      #  MinecartRideable in 1.7.10, minecraft:minecart in 26.3
      self.assertEqual(entityOf(MCEntities.Minecart, self.game.version)[0], seen.target.type)
    finally:
      self.game.remove(cart)

  def test_d_what_stops_nothing_and_what_is_climbed(self) -> None:
    placed = [((-2, 4, 0), MCBlocks.Stone),
              ((-1, 4, 0), block('ladder facing east')),
              ((1, 4, 0), MCBlocks.Poppy),
              ((1, 3, 1), MCBlocks.Water)]
    for pos, each in placed:
      self.game.setBlock(at(*pos), each)
    try:
      self.game.ticks(2)
      seen = self.perceived()
      ladder = self.near(seen, (-1, 4, 0))
      self.assertTrue(ladder.climbable)
      self.assertTrue(ladder.solid)
      self.assertFalse(self.near(seen, (-2, 4, 0)).climbable)
      poppy = self.near(seen, (1, 4, 0))
      self.assertFalse(poppy.solid)
      self.assertFalse(poppy.liquid)
      water = self.near(seen, (1, 3, 1))
      self.assertTrue(water.liquid)
      self.assertFalse(water.solid)
    finally:
      for pos, _ in reversed(placed):
        self.game.setBlock(at(*pos), MCBlocks.Air if pos[1] > 3 else
                           MCBlocks.GrassBlock)

  def test_f_sneaking(self) -> None:
    """
    Sneaking lowers the eye (1.7.10's client lowers posY 0.08; 26.3's
    crouching pose is lower), not the feet: they stay on the ground, the
    box's foot, in player.get too.
    """
    self.game.keyDown('key.sneak')
    try:
      self.game.ticks(5)
      seen = self.perceived()
      client = self.game.player(side='client')
    finally:
      self.game.keyUp('key.sneak')
    self.assertTrue(seen.sneaking)
    self.assertEqual((lift(4.0),) * 3,
                     (seen.box.minY, seen.pos.y, client.pos.y))
    self.assertLess(seen.eye.y, seen.pos.y + EYE)

  def test_e_nothing_within_reach(self) -> None:
    self.game.look(0, -90)
    seen = self.perceived()
    self.assertTrue(seen.target.nothing)
    self.assertEqual(Vec3, type(seen.pos))


if __name__ == '__main__':
  unittest.main()

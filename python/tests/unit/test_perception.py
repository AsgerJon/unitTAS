"""
What the player perceives (player.perceive, SPEC.md 15.6 step 1) as
Python values, without a game: read from an answer shaped as the probe
sends it (and, in fixtures/perceptions.json, answers the probe really
sent), and back. A missing field is refused by name, and so are a face
that isn't one of the six and a box that isn't six numbers. The rate the
look turns at (mouse.rate, SPEC.md 19.7 step 12) is in it: none is 0, 0.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import copy
import json
import os
import unittest

from unittas.box import Box
from unittas.codec import fromJson, toJson
from unittas.mouserate import MouseRate
from unittas.nearblock import NearBlock
from unittas.perception import Perception
from unittas.target import Target
from unittas.values import BlockPos, Look, Vec3

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'fixtures', 'perceptions.json')

GRASS = {'pos': [0, 3, 0], 'id': 'minecraft:grass', 'meta': 0,
         'boxes': [[0.0, 3.0, 0.0, 1.0, 4.0, 1.0]], 'liquid': False,
         'climbable': False, 'opens': False}
POPPY = {'pos': [1, 4, 0], 'id': 'minecraft:red_flower', 'meta': 0,
         'boxes': [], 'liquid': False, 'climbable': False, 'opens': False}
LADDER = {'pos': [-1, 4, 0], 'id': 'minecraft:ladder', 'meta': 5,
          'boxes': [[-1.0, 4.0, 0.0, -0.875, 5.0, 1.0]], 'liquid': False,
          'climbable': True, 'opens': False}
DOOR = {'pos': [2, 4, 0], 'id': 'minecraft:wooden_door', 'meta': 1,
        'boxes': [[2.0, 4.0, 0.0, 3.0, 5.0, 0.1875]], 'liquid': False,
        'climbable': False, 'opens': True}
LOOKING_DOWN = {
  'tick': 812, 'pos': [0.5, 4.0, 0.5], 'eye': [0.5, 5.62, 0.5],
  'box': [0.2, 4.0, 0.2, 0.8, 5.8, 0.8],
  'look': {'yaw': 0.0, 'pitch': 90.0},
  'motion': [0.0, -0.0784000015258789, 0.0], 'on_ground': True,
  'collided': {'horizontally': False, 'vertically': True},
  'in_water': False, 'in_lava': False, 'on_ladder': False,
  'sneaking': False, 'sprinting': False, 'flying': False,
  'reach': {'block': 5.0, 'entity': 6.0},
  'mouse_rate': {'yaw': 0.0, 'pitch': 0.0, 'frames': 0},
  'target': {'block': [0, 3, 0], 'face': 'up', 'hit': [0.5, 4.0, 0.5],
             'id': 'minecraft:grass', 'meta': 0},
  'blocks': [GRASS, POPPY, LADDER, DOOR]}
PIG_TARGET = {'entity': 412, 'type': 'Pig', 'hit': [0.5, 4.6, 2.05]}
#  26.3's: no meta, a state (SPEC.md 12.6, D4)
DOOR_26 = {'pos': [2, -60, 0], 'id': 'minecraft:oak_door',
           'state': {'facing': 'north', 'half': 'lower', 'hinge': 'left',
                     'open': 'false', 'powered': 'false'},
           'boxes': [[2.0, -60.0, 0.8125, 3.0, -59.0, 1.0]], 'liquid': False,
           'climbable': False, 'opens': True}
GRASS_TARGET_26 = {'block': [0, -61, 0], 'face': 'up', 'hit': [0.5, -60.0, 0.5],
                   'id': 'minecraft:grass_block', 'state': {'snowy': 'false'}}


def _with(**changes) -> dict:
  """The answer looking down, with these keys changed."""
  wire = copy.deepcopy(LOOKING_DOWN)
  wire.update(changes)
  return wire


class PerceptionClassTests(unittest.TestCase):
  """Each value's fields are the ones it declares (test_values' rule)."""

  def test_only_the_declared_fields(self) -> None:
    for cls in (Box, Target, NearBlock, MouseRate, Perception):
      with self.subTest(cls.__name__):
        value = cls()
        names = list(value.asDict())
        self.assertEqual([], [n for n in names if n.startswith('_')])
        self.assertEqual(hash(cls()), hash(value))


class PerceptionTests(unittest.TestCase):

  def test_read_and_back(self) -> None:
    seen = fromJson(Perception, LOOKING_DOWN)
    self.assertEqual(812, seen.tick)
    self.assertEqual(Vec3(0.5, 4.0, 0.5), seen.pos)
    self.assertEqual(Vec3(0.5, 5.62, 0.5), seen.eye)
    self.assertEqual(Box(0.2, 4.0, 0.2, 0.8, 5.8, 0.8), seen.box)
    self.assertEqual(Look(0.0, 90.0), seen.look)
    self.assertTrue(seen.onGround)
    self.assertFalse(seen.collidedHorizontally)
    self.assertTrue(seen.collidedVertically)
    self.assertFalse(seen.inWater or seen.inLava or seen.onLadder)
    self.assertFalse(seen.sneaking or seen.sprinting or seen.flying)
    self.assertEqual((5.0, 6.0), (seen.blockReach, seen.entityReach))
    self.assertEqual(MouseRate(0.0, 0.0, 0), seen.mouseRate)
    self.assertTrue(seen.mouseRate.none)
    self.assertEqual(4, len(seen.blocks))
    self.assertEqual(LOOKING_DOWN, toJson(seen))

  def test_the_rate_in_force(self) -> None:
    """
    The rate mouse.rate set, in degrees a tick (its signs player.look's),
    and the frames it has turned the look in since.
    """
    wire = _with(mouse_rate={'yaw': 2.5, 'pitch': -1.0, 'frames': 87})
    seen = fromJson(Perception, wire)
    self.assertEqual(MouseRate(2.5, -1.0, 87), seen.mouseRate)
    self.assertFalse(seen.mouseRate.none)
    self.assertEqual(wire, toJson(seen))
    self.assertTrue(MouseRate(0.0, 0.0, 12).none)

  def test_a_block_targeted(self) -> None:
    target = fromJson(Perception, LOOKING_DOWN).target
    self.assertEqual('block', target.kind)
    self.assertFalse(target.nothing)
    self.assertEqual(BlockPos(0, 3, 0), target.pos)
    self.assertEqual('up', target.face)
    self.assertEqual(Vec3(0.5, 4.0, 0.5), target.hit)
    self.assertEqual(('minecraft:grass', 0), (target.id, target.meta))

  def test_an_entity_targeted(self) -> None:
    wire = _with(target=PIG_TARGET)
    target = fromJson(Perception, wire).target
    self.assertEqual('entity', target.kind)
    self.assertEqual((412, 'Pig'), (target.entity, target.type))
    self.assertEqual(Vec3(0.5, 4.6, 2.05), target.hit)
    self.assertEqual(wire, toJson(fromJson(Perception, wire)))

  def test_nothing_within_reach(self) -> None:
    wire = _with(target=None)
    seen = fromJson(Perception, wire)
    self.assertIs(Target.NOTHING, seen.target)
    self.assertTrue(seen.target.nothing)
    self.assertEqual(wire, toJson(seen))

  def test_the_blocks_around(self) -> None:
    grass, poppy, ladder, door = fromJson(Perception, LOOKING_DOWN).blocks
    self.assertTrue(door.opens)
    self.assertFalse(grass.opens)
    self.assertEqual(BlockPos(0, 3, 0), grass.pos)
    self.assertEqual((Box(0.0, 3.0, 0.0, 1.0, 4.0, 1.0),), grass.boxes)
    self.assertTrue(grass.solid)
    self.assertEqual(4.0, grass.top)
    #  a flower is there, but nothing stops the player: its floor is its top
    self.assertFalse(poppy.solid)
    self.assertEqual(4.0, poppy.top)
    self.assertTrue(ladder.climbable)
    self.assertEqual(('minecraft:ladder', 5), (ladder.id, ladder.meta))

  def test_26_3_s_state_and_no_meta(self) -> None:
    """26.3's blocks near and its target: a state, no meta (-1); back as they came."""
    wire = _with(blocks=[DOOR_26], target=GRASS_TARGET_26)
    seen = fromJson(Perception, wire)
    door = seen.blocks[0]
    self.assertEqual(-1, door.meta)
    self.assertEqual('false', door.properties['open'])
    self.assertTrue(door.opens)
    self.assertEqual(-1, seen.target.meta)
    self.assertEqual({'snowy': 'false'}, seen.target.properties)
    self.assertEqual(wire, toJson(seen))
    #  1.7.10's keep their meta and have no state
    grass = fromJson(Perception, LOOKING_DOWN).blocks[0]
    self.assertEqual(((), 0), (grass.state, grass.meta))

  def test_refused_by_name(self) -> None:
    wire = _with()
    del wire['eye']
    with self.assertRaisesRegex(ValueError, 'a perception has no "eye"'):
      fromJson(Perception, wire)
    with self.assertRaisesRegex(ValueError, 'a box is a list of six'):
      fromJson(Perception, _with(box=[0.2, 4.0, 0.2, 0.8, 5.8]))
    target = dict(LOOKING_DOWN['target'], face='sideways')
    with self.assertRaisesRegex(ValueError, "'sideways'"):
      fromJson(Perception, _with(target=target))
    with self.assertRaisesRegex(ValueError, 'neither "block" nor "entity"'):
      fromJson(Perception, _with(target={'hit': [0.0, 0.0, 0.0]}))
    near = dict(GRASS)
    del near['liquid']
    with self.assertRaisesRegex(ValueError, 'a block near has no "liquid"'):
      fromJson(Perception, _with(blocks=[near]))
    wire = _with()
    del wire['mouse_rate']
    with self.assertRaisesRegex(ValueError,
                                'a perception has no "mouse_rate"'):
      fromJson(Perception, wire)
    with self.assertRaisesRegex(ValueError, 'a mouse rate has no "frames"'):
      fromJson(Perception, _with(mouse_rate={'yaw': 0.0, 'pitch': 0.0}))


class RecordedPerceptionsTests(unittest.TestCase):
  """
  Every perception the probe really sent (tests/probe/test_perceive.py
  records them, on each port) reads, and goes back unchanged: 1.7.10's in
  perceptions.json, 26.3's (states, no meta) in perceptions-26.3.json.
  """

  def check(self, name: str) -> list:
    with open(os.path.join(os.path.dirname(FIXTURES), name),
              encoding='utf-8') as file:
      recorded = json.load(file)
    self.assertTrue(recorded)
    for wire in recorded:
      with self.subTest(file=name, tick=wire.get('tick')):
        self.assertEqual(wire, toJson(fromJson(Perception, wire)))
    return recorded

  def test_each_recorded_answer_of_1_7_10(self) -> None:
    self.check('perceptions.json')

  def test_each_recorded_answer_of_26_3(self) -> None:
    recorded = self.check('perceptions-26.3.json')
    blocks = [block for wire in recorded for block in wire['blocks']]
    self.assertTrue(blocks)
    self.assertFalse([block for block in blocks if 'meta' in block],
                     '26.3 has no meta')
    self.assertTrue([block for block in blocks if 'state' in block])


if __name__ == '__main__':
  unittest.main()

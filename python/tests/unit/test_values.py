"""
The protocol's values (PROTOCOL.md section 5) as Python values, without a game: each read from an answer shaped as the
probe sends it (and, in fixtures/answers.json, answers the probe really sent), and back. Equality and hashing come free;
an empty slot is Item.EMPTY; a field the package doesn't know is ignored, and a missing one is refused by name.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import json
import os
import unittest

from unittas.codec import fromJson, toJson
from unittas.snbt import Byte, Compound, String
from unittas.values import (Block, BlockPos, ChatLine, Effect, Entity, Inventory, Item, LogLine, Look, Player, Screen,
                            Sound, Vec3)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'answers.json')

PIG = {'entity': 412, 'type': 'Pig', 'class': 'net.minecraft.entity.passive.EntityPig',
       'uuid': '0c1d3a5e-2f44-4b8e-9c1a-5d6e7f809a1b', 'pos': [3.5, 4.0, 3.5],
       'look': {'yaw': 90.0, 'pitch': 0.0}, 'motion': [0.0, -0.0784000015258789, 0.0],
       'dimension': 'minecraft:overworld', 'alive': True, 'on_ground': True, 'name': 'Pig', 'custom_name': None,
       'riding': None, 'fire_ticks': 0, 'health': 10.0, 'max_health': 10.0}
ARROW = {'entity': 413, 'type': 'Arrow', 'class': 'net.minecraft.entity.projectile.EntityArrow',
         'uuid': '9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d', 'pos': [0.5, 5.0, 0.5],
         'look': {'yaw': 0.0, 'pitch': 0.0}, 'motion': [0.0, 0.0, 0.0], 'dimension': 'minecraft:overworld',
         'alive': True, 'on_ground': False, 'name': 'arrow', 'custom_name': 'Bob', 'riding': {'entity': 412},
         'fire_ticks': 20}
PLAYER = {'entity': 182, 'name': 'Dev', 'uuid': '380df991-f603-344c-a090-369bad2a924a', 'pos': [0.5, 4.0, 0.5],
          'look': {'yaw': 0.0, 'pitch': 0.0}, 'motion': [0.0, 0.0, 0.0], 'dimension': 'minecraft:overworld',
          'game_mode': 'creative', 'health': 20.0, 'max_health': 20.0, 'food': 20, 'saturation': 5.0,
          'xp': {'level': 0, 'progress': 0.0, 'total': 0}, 'on_ground': True, 'flying': False, 'may_fly': True,
          'sneaking': False, 'sprinting': False, 'sleeping': False, 'riding': None, 'fire_ticks': 0, 'air': 300,
          'fall_distance': 0.0, 'arrows': 0,
          'effects': [{'effect': 'potion.moveSpeed', 'id': 1, 'amplifier': 1, 'duration': 600, 'ambient': False}]}


class ItemTests(unittest.TestCase):

  def test_read_and_back(self) -> None:
    wire = {'id': 'minecraft:wool', 'count': 3, 'meta': 14}
    item = fromJson(Item, wire)
    self.assertEqual(Item('minecraft:wool', 3, 14), item)
    self.assertEqual(wire, toJson(item))

  def test_an_empty_slot_is_item_empty(self) -> None:
    self.assertIs(Item.EMPTY, fromJson(Item, None))
    self.assertTrue(Item.EMPTY.empty)
    self.assertFalse(Item('minecraft:stone', 1, 0).empty)
    self.assertIsNone(toJson(Item.EMPTY), 'an empty slot goes back as null')

  def test_input_defaults(self) -> None:
    self.assertEqual(Item('minecraft:stone', 1, 0), fromJson(Item, {'id': 'minecraft:stone'}))

  def test_nbt_as_a_typed_tree(self) -> None:
    item = fromJson(Item, {'id': 'minecraft:wool', 'count': 1, 'meta': 14, 'nbt': '{display:{Name:"Red"},x:1b}'})
    self.assertIsInstance(item.nbt, Compound)
    self.assertEqual(String('Red'), item.nbt['display']['Name'])
    self.assertEqual(Byte(1), item.nbt['x'])
    self.assertEqual('{display:{Name:"Red"},x:1b}', toJson(item)['nbt'])
    self.assertIsNone(Item('minecraft:stone', 1, 0).nbt)

  def test_equal_and_hashed_as_values(self) -> None:
    self.assertEqual(hash(Item('minecraft:wool', 1, 14)), hash(fromJson(Item, {'id': 'minecraft:wool', 'meta': 14})))
    self.assertEqual(1, len({Item('a:b', 1, 0), Item('a:b', 1, 0)}))

  def test_refused_by_name(self) -> None:
    for wire, named in (({'count': 1}, 'id'), ({'id': 3}, 'id'), ({'id': 'a:b', 'count': 'x'}, 'count'),
                        ({'id': 'a:b', 'count': True}, 'count'), ('wool', 'item')):
      with self.assertRaises(ValueError) as refused:
        fromJson(Item, wire)
      self.assertIn(named, str(refused.exception), wire)

  def test_unknown_fields_ignored(self) -> None:
    self.assertEqual(Item('a:b', 1, 0), fromJson(Item, {'id': 'a:b', 'components': {}, 'later': 1}))


class PlaceTests(unittest.TestCase):

  def test_positions_and_looks(self) -> None:
    self.assertEqual(Vec3(3.5, 4.0, 3.5), fromJson(Vec3, [3.5, 4, 3.5]))
    self.assertEqual([3.5, 4.0, 3.5], toJson(Vec3(3.5, 4, 3.5)))
    self.assertEqual(BlockPos(40, 4, -2), fromJson(BlockPos, [40, 4, -2]))
    self.assertEqual([40, 4, -2], toJson(BlockPos(40, 4, -2)))
    self.assertEqual(Look(90.0, -15.0), fromJson(Look, {'yaw': 90, 'pitch': -15.0}))
    self.assertEqual({'yaw': 90.0, 'pitch': -15.0}, toJson(Look(90, -15)))

  def test_refused(self) -> None:
    for kind, wire in ((Vec3, [1, 2]), (Vec3, [1, 'a', 3]), (BlockPos, [1.5, 2, 3]), (Look, {'yaw': 1})):
      with self.assertRaises(ValueError):
        fromJson(kind, wire)


class BlockTests(unittest.TestCase):

  def test_with_and_without_its_tile(self) -> None:
    self.assertEqual(Block('minecraft:wool', 14), fromJson(Block, {'id': 'minecraft:wool', 'meta': 14}))
    self.assertIsNone(fromJson(Block, {'id': 'minecraft:chest', 'meta': 0, 'tile': None}).tile)
    chest = fromJson(Block, {'id': 'minecraft:chest', 'meta': 2, 'tile': '{id:"Chest",x:40}'})
    self.assertEqual(String('Chest'), chest.tile['id'])
    self.assertEqual({'id': 'minecraft:chest', 'meta': 2, 'tile': '{id:"Chest",x:40}'}, toJson(chest))
    self.assertEqual({'id': 'minecraft:wool', 'meta': 14}, toJson(Block('minecraft:wool', 14)))


class InventoryTests(unittest.TestCase):

  def test_whole(self) -> None:
    wire = {'selected': 2, 'main': [None] * 2 + [{'id': 'minecraft:wool', 'count': 3, 'meta': 14}] + [None] * 33,
            'armor': {'feet': {'id': 'minecraft:leather_boots', 'count': 1, 'meta': 0}, 'legs': None, 'chest': None,
                      'head': None},
            'cursor': None}
    inventory = fromJson(Inventory, wire)
    self.assertEqual(36, len(inventory.main))
    self.assertEqual(Item('minecraft:wool', 3, 14), inventory.held)
    self.assertEqual(Item('minecraft:leather_boots', 1, 0), inventory.feet)
    self.assertIs(Item.EMPTY, inventory.head)
    self.assertIs(Item.EMPTY, inventory.cursor)
    self.assertEqual(wire, toJson(inventory))


class EntityTests(unittest.TestCase):

  def test_a_living_entity(self) -> None:
    pig = fromJson(Entity, PIG)
    self.assertEqual(412, pig.entity)
    self.assertEqual('net.minecraft.entity.passive.EntityPig', pig.className)
    self.assertEqual(Vec3(3.5, 4.0, 3.5), pig.pos)
    self.assertEqual(10.0, pig.health)
    self.assertIsNone(pig.customName)
    self.assertIsNone(pig.riding)
    self.assertEqual(PIG, toJson(pig))

  def test_one_that_isn_t_living(self) -> None:
    arrow = fromJson(Entity, ARROW)
    self.assertIsNone(arrow.health)
    self.assertIsNone(arrow.maxHealth)
    self.assertEqual('Bob', arrow.customName)
    self.assertEqual(412, arrow.riding)
    self.assertEqual(ARROW, toJson(arrow))

  def test_equal_and_hashed(self) -> None:
    self.assertEqual(fromJson(Entity, PIG), fromJson(Entity, dict(PIG)))
    self.assertEqual(hash(fromJson(Entity, PIG)), hash(fromJson(Entity, dict(PIG))))
    self.assertNotEqual(fromJson(Entity, PIG), fromJson(Entity, dict(PIG, health=9.0)))

  def test_missing_by_name(self) -> None:
    for key in ('entity', 'pos', 'look', 'alive'):
      wire = dict(PIG)
      del wire[key]
      with self.assertRaises(ValueError) as refused:
        fromJson(Entity, wire)
      self.assertIn(key, str(refused.exception))


class PlayerTests(unittest.TestCase):

  def test_read_and_back(self) -> None:
    player = fromJson(Player, PLAYER)
    self.assertEqual('Dev', player.name)
    self.assertEqual('creative', player.gameMode)
    self.assertEqual((Effect('potion.moveSpeed', 1, 1, 600, False),), player.effects)
    self.assertIsNone(player.riding)
    self.assertIsNone(player.camera, 'the server side has no camera')
    self.assertEqual(PLAYER, toJson(player))

  def test_the_client_s_camera(self) -> None:
    client = fromJson(Player, dict(PLAYER, camera=1))
    self.assertEqual(1, client.camera)
    self.assertEqual(dict(PLAYER, camera=1), toJson(client))


class EventValueTests(unittest.TestCase):

  def test_a_chat_line(self) -> None:
    wire = {'plain': 'Given [Red Wool] * 1', 'formatted': '§fGiven [Red Wool] * 1§r', 'json': '{"text":"x"}'}
    line = fromJson(ChatLine, wire)
    self.assertEqual('Given [Red Wool] * 1', line.plain)
    self.assertIsNone(line.kind, '1.7.10 has no kind')
    self.assertEqual(wire, toJson(line))

  def test_a_sound(self) -> None:
    wire = {'id': 'minecraft:random.click', 'known': True, 'from': None, 'volume': 1.0, 'pitch': 1.0,
            'pos': [0.5, 4.0, 0.5]}
    sound = fromJson(Sound, wire)
    self.assertEqual(Vec3(0.5, 4.0, 0.5), sound.pos)
    self.assertIsNone(sound.callers, 'a sound the game has: no callers asked for')
    self.assertEqual(wire, toJson(sound))
    missing = dict(wire, id='minecraft:mob.wobble', known=False, **{'from': 'EntityWobble.onUpdate'})
    self.assertEqual('EntityWobble.onUpdate', fromJson(Sound, missing).callers)
    self.assertEqual(missing, toJson(fromJson(Sound, missing)))

  def test_a_log_line(self) -> None:
    wire = {'level': 'WARN', 'logger': 'FML', 'thread': 'Client thread', 'message': 'a warning', 'thrown': None}
    line = fromJson(LogLine, wire)
    self.assertIsNone(line.thrown)
    self.assertEqual(wire, toJson(line))
    thrown = fromJson(LogLine, dict(wire, thrown='java.lang.IllegalStateException: no'))
    self.assertEqual('java.lang.IllegalStateException: no', thrown.thrown)

  def test_a_screen(self) -> None:
    wire = {'class': 'net.minecraft.client.gui.inventory.GuiInventory', 'chat': False, 'container': True,
            'pauses': False}
    screen = fromJson(Screen, wire)
    self.assertTrue(screen.container)
    self.assertEqual(wire, toJson(screen))
    self.assertIsNone(fromJson(Screen, None), 'no screen open')


class RecordedAnswersTests(unittest.TestCase):
  """Every answer the probe really sent (tests/probe/test_values.py records them) reads, and goes back unchanged."""

  def test_each_recorded_answer(self) -> None:
    with open(FIXTURES, encoding='utf-8') as file:
      recorded = json.load(file)
    kinds = {'Item': Item, 'Block': Block, 'Inventory': Inventory, 'Entity': Entity, 'Player': Player,
             'ChatLine': ChatLine, 'Sound': Sound, 'LogLine': LogLine, 'Screen': Screen}
    self.assertTrue(set(kinds) <= set(recorded), sorted(recorded))
    for kindName, answers in recorded.items():
      for wire in answers:
        with self.subTest(kind=kindName, wire=wire):
          self.assertEqual(wire, toJson(fromJson(kinds[kindName], wire)))


if __name__ == '__main__':
  unittest.main()

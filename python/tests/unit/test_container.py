"""
An open container as its screen shows it (container.get, PROTOCOL.md
8.5; SPEC.md 15.6 step 4) as a Python value, without a game: its slots
by number, the player's own among them and the container's, read from an
answer shaped as the probe sends it, and back.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import unittest

from unittas.codec import fromJson, toJson
from unittas.container import Container
from unittas.values import Item

WOOL = {'id': 'minecraft:wool', 'count': 3, 'meta': 6}
#  a small chest: its 27 slots, then the player's 27 and its hotbar's 9
CHEST = {'class': 'net.minecraft.inventory.ContainerChest', 'window': 3,
         'player_own': False,
         'slots': [{'index': i, 'item': WOOL if i in (0, 58) else None}
                   for i in range(63)],
         'player_slots': [27, 62]}
#  the player's own: crafting, armour, its 27, its hotbar
OWN = {'class': 'net.minecraft.inventory.ContainerPlayer', 'window': 0,
       'player_own': True,
       'slots': [{'index': i, 'item': None} for i in range(45)],
       'player_slots': [9, 44]}


class ContainerTests(unittest.TestCase):

  def test_only_the_declared_fields(self) -> None:
    names = list(Container().asDict())
    self.assertEqual([], [n for n in names if n.startswith('_')])

  def test_read_and_back(self) -> None:
    chest = fromJson(Container, CHEST)
    self.assertEqual('net.minecraft.inventory.ContainerChest',
                     chest.className)
    self.assertEqual(3, chest.window)
    self.assertFalse(chest.playerOwn)
    self.assertEqual(63, len(chest.slots))
    self.assertEqual(Item('minecraft:wool', 3, 6), chest.slots[0])
    self.assertIs(Item.EMPTY, chest.slots[1])
    self.assertEqual(CHEST, toJson(chest))
    self.assertEqual(OWN, toJson(fromJson(Container, OWN)))

  def test_the_container_s_slots_and_the_player_s(self) -> None:
    chest = fromJson(Container, CHEST)
    self.assertEqual(tuple(range(27)), chest.theirs)
    self.assertEqual(tuple(range(27, 63)), chest.own)
    #  what the container holds, as its screen shows it
    self.assertEqual((Item('minecraft:wool', 3, 6),),
                     tuple(item for item in chest.contents
                           if not item.empty))
    self.assertEqual(27, len(chest.contents))
    own = fromJson(Container, OWN)
    self.assertEqual(tuple(range(9)), own.theirs)

  def test_none_of_the_player_s(self) -> None:
    wire = dict(CHEST, player_slots=None)
    seen = fromJson(Container, wire)
    self.assertEqual((), seen.own)
    self.assertEqual(tuple(range(63)), seen.theirs)
    self.assertEqual(wire, toJson(seen))

  def test_refused_by_name(self) -> None:
    slots = list(CHEST['slots'])
    slots[0], slots[1] = slots[1], slots[0]
    with self.assertRaisesRegex(ValueError, 'slot 1 where 0'):
      fromJson(Container, dict(CHEST, slots=slots))
    with self.assertRaisesRegex(ValueError, 'player_slots'):
      fromJson(Container, dict(CHEST, player_slots=[27]))
    with self.assertRaisesRegex(ValueError, 'has no "window"'):
      fromJson(Container, {key: value for key, value in CHEST.items()
                           if key != 'window'})


if __name__ == '__main__':
  unittest.main()

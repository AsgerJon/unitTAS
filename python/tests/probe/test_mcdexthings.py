"""
Things by mcdex member in the development client (SPEC.md 14.5 steps 3
and 4): the game's API given mcdex members puts in what 1.7.10 has for
them, and reads back as that version's own: pink wool's meta, red wool,
a wither skeleton's skull and a potted poppy with their block entities'
data, a wither skeleton by its type's data, the Nether by its number.
The elytra vanilla 1.7.10 lacks is Missing, before the game is asked.
Back: what the game reports is those members again (twins both, a
tool's damage no meta, a wither skeleton no plain one), and so is an
effect by its number.

  python -m unittas.selftest test_mcdexthings.
  (through the watcher: "probe test_mcdexthings.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from mcdex import (MCBlocks, MCDimensions, MCEffects, MCEntities, MCItems,
                   Version)

from probegame import READY_SECONDS, ROOT, results
from unittas.api import Game
from unittas.dev import DevGame
from unittas.errors import Missing
from unittas.launcher import Sources
from unittas.mappings import Mappings
from unittas.reset import reset
from unittas.snbt import loads
from unittas.values import Block, Item


class McdexThingTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = DevGame(ROOT, results(), 'mcdexthings')
    shutil.rmtree(os.path.join(cls.launched.gameDir, 'saves', 'unittas'),
                  ignore_errors=True)
    connection = cls.launched.start()
    connection.events.waitFor(
      lambda event: event.get('event') == 'ready', READY_SECONDS)
    sources = Sources(gradleHome=os.path.join(ROOT, '.gradle-home'))
    cls.game = Game(connection, mappings=Mappings.load(sources))
    cls.game.request('world.create', {}, timeout=240)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.launched.stop()

  def setUp(self) -> None:
    reset(self.game.connection)

  def test_a_the_version_is_mcdexs(self) -> None:
    self.assertIs(Version.V1_7_10, self.game.version)

  def test_an_item_by_member(self) -> None:
    self.game.setSlot('held', MCItems.PinkWool, 3)
    self.assertEqual(Item('minecraft:wool', 3, 6), self.game.held())

  def test_an_item_vanilla_lacks_is_missing(self) -> None:
    with self.assertRaises(Missing) as raised:
      self.game.setSlot('armor.chest', MCItems.Elytra)
    self.assertIn("Vanilla 1.7.10 has no 'elytra'", str(raised.exception))
    self.assertTrue(self.game.slot('armor.chest').empty)

  def test_blocks_by_member(self) -> None:
    self.game.setBlock((3, 4, 3), MCBlocks.RedWool)
    self.assertEqual(Block('minecraft:wool', 14), self.game.block((3, 4, 3)))
    self.game.setBlock((4, 4, 3), MCBlocks.WitherSkeletonSkull)
    skull = self.game.block((4, 4, 3), tile=True)
    self.assertEqual(('minecraft:skull', 1), (skull.id, skull.meta))
    self.assertEqual(1, skull.tile['SkullType'])
    self.game.setBlock((5, 4, 3), MCBlocks.PottedPoppy)
    pot = self.game.block((5, 4, 3), tile=True)
    self.assertEqual('minecraft:flower_pot', pot.id)
    self.assertEqual((38, 0), (pot.tile['Item'], pot.tile['Data']))

  def test_an_entity_by_member(self) -> None:
    entity = self.game.spawn(MCEntities.WitherSkeleton, (6.5, 4, 6.5))
    try:
      self.assertEqual('Skeleton', entity.type)
      read = self.game.request('entity.get',
                               {'entity': entity.entity, 'nbt': True})
      self.assertEqual(1, loads(read['nbt'])['SkeletonType'])
    finally:
      self.game.remove(entity)

  def test_a_dimension_by_member(self) -> None:
    self.game.teleport((0.5, 64, 0.5), dimension=MCDimensions.TheNether)
    self.assertEqual('minecraft:the_nether', self.game.player().dimension)
    self.game.teleport((0.5, 4, 0.5), dimension=MCDimensions.Overworld)
    self.assertEqual('minecraft:overworld', self.game.player().dimension)

  def test_items_read_back_as_members(self) -> None:
    self.game.setSlot('held', MCItems.PinkWool)
    self.assertEqual({MCItems.PinkWool},
                     self.game.membersOf(self.game.held()))
    self.game.setSlot('held', Item('minecraft:iron_pickaxe', 1, 37))
    self.assertEqual({MCItems.IronPickaxe},
                     self.game.membersOf(self.game.held()))
    self.game.setSlot('held', MCItems.Steak)
    self.assertEqual({MCItems.Steak, MCItems.CookedBeef},
                     self.game.membersOf(self.game.held()))

  def test_blocks_read_back_as_members(self) -> None:
    self.game.setBlock((3, 4, 5), MCBlocks.RedWool)
    self.assertEqual({MCBlocks.RedWool},
                     self.game.membersOf(self.game.block((3, 4, 5))))
    self.game.setBlock((4, 4, 5), MCBlocks.WitherSkeletonSkull)
    self.assertEqual({MCBlocks.WitherSkeletonSkull},
                     self.game.membersOf(self.game.block((4, 4, 5),
                                                         tile=True)))
    self.game.setBlock((5, 4, 5), MCBlocks.PottedPoppy)
    self.assertEqual({MCBlocks.PottedPoppy},
                     self.game.membersOf(self.game.block((5, 4, 5),
                                                         tile=True)))

  def test_entities_read_back_as_members(self) -> None:
    wither = self.game.spawn(MCEntities.WitherSkeleton, (6.5, 4, 8.5))
    plain = self.game.spawn(MCEntities.Skeleton, (8.5, 4, 8.5))
    try:
      self.assertEqual({MCEntities.WitherSkeleton},
                       self.game.membersOf(wither))
      self.assertEqual({MCEntities.Skeleton}, self.game.membersOf(plain))
      found = self.game.entities(type=MCEntities.WitherSkeleton)
      self.assertIn(wither.entity, [each.entity for each in found])
      self.assertNotIn(plain.entity, [each.entity for each in found])
    finally:
      self.game.remove(wither)
      self.game.remove(plain)

  def test_an_effect_reads_back_by_its_number(self) -> None:
    self.game.command('/effect @p 19 30 0')
    effects = self.game.player().effects
    self.assertIn(frozenset({MCEffects.Poison}),
                  [self.game.membersOf(each) for each in effects])


if __name__ == '__main__':
  unittest.main()

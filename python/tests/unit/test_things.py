"""
Things by mcdex member (SPEC.md 14.3, 14.5 steps 2 to 4), without a
game: each id mcdex holds for a version read into its parts and turned
into what the probe takes, exactly as the spec's table has them, for
every id mcdex holds for 1.7.10 and 26.3 in the catalogues the API
takes; a thing vanilla lacks there is Missing, and a version mcdex has
no data for is no result. Back: a value the game reports is the set of
members its id fits, the most specific first (twins both; a tool's
damage no meta; data a subset); assertThing on it.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import unittest

from mcdex import (MCBlocks, MCDimensions, MCEffects, MCEntities, MCItems,
                   MCParticles, NotInVersion, Version)

from unittas.errors import (Missing, NeedFailed, NoMcdexData, NoMcdexThing,
                            NoResult)
from unittas.testcase import GameTestCase
from unittas.things import (ThingId, blockOf, dimensionOf, entityOf, itemOf,
                            membersOf, parse, resolve)
from unittas.values import Block, Effect, Entity, Item

VERSIONS = (Version.V1_7_10, Version.V26_3)


def held(catalogue: type, version: Version) -> list:
  """The members of 'catalogue' that have an id in 'version'."""
  out = []
  for member in catalogue:
    try:
      member[version]
    except NotInVersion:
      continue
    out.append(member)
  return out


class ParseTests(unittest.TestCase):
  """An mcdex id read into its parts, as the spec's table has them."""

  def test_the_table(self) -> None:
    """SPEC.md 14.3's cases, exactly."""
    cases = {
      'minecraft:wool:6': ThingId('minecraft:wool', 6, True),
      'minecraft:spawn_egg{EntityTag:{id:"Bat"}}':
        ThingId('minecraft:spawn_egg', nbt='{EntityTag:{id:"Bat"}}'),
      'minecraft:skull:1{SkullType:4b}':
        ThingId('minecraft:skull', 1, True, nbt='{SkullType:4b}'),
      'minecraft:cauldron[level=1]':
        ThingId('minecraft:cauldron', state='level=1'),
      'Skeleton{SkeletonType:1}':
        ThingId('Skeleton', nbt='{SkeletonType:1}'),
      'minecraft:pink_wool': ThingId('minecraft:pink_wool'),
      '22': ThingId(number=22, isNumber=True),
      '-1': ThingId(number=-1, isNumber=True),
    }
    for text, expected in cases.items():
      with self.subTest(text=text):
        self.assertEqual(expected, parse(text))
        self.assertEqual(text, parse(text).text())

  def test_a_shape_outside_the_grammar_is_refused(self) -> None:
    """Nothing is guessed: an id that doesn't fit raises."""
    for text in ('', 'a:b:c', 'minecraft:x[level=1', 'minecraft:x{a:1',
                 'minecraft::wool', ':wool', 'minecraft:wool:'):
      with self.subTest(text=text):
        with self.assertRaises(ValueError):
          parse(text)

  def test_every_id_of_1_7_10_and_26_3_reads_and_writes_back(self) -> None:
    """Each id mcdex holds there, its parts written back as it was."""
    for catalogue in (MCItems, MCBlocks, MCEntities, MCEffects,
                      MCDimensions):
      for version in VERSIONS:
        for member in held(catalogue, version):
          text = member[version].minecraftId
          with self.subTest(member=str(member), version=str(version)):
            self.assertEqual(text, parse(text).text())


class ProbeValueTests(unittest.TestCase):
  """A member turned into what the probe takes, in each version."""

  def test_an_item(self) -> None:
    self.assertEqual(Item('minecraft:wool', 1, 6),
                     itemOf(MCItems.PinkWool, Version.V1_7_10))
    self.assertEqual(Item('minecraft:pink_wool', 5, 0),
                     itemOf(MCItems.PinkWool, Version.V26_3, 5))

  def test_a_block(self) -> None:
    """A block and its block entity's data, '' for none."""
    self.assertEqual((Block('minecraft:wool', 14), ''),
                     blockOf(MCBlocks.RedWool, Version.V1_7_10))
    self.assertEqual((Block('minecraft:red_wool', 0), ''),
                     blockOf(MCBlocks.RedWool, Version.V26_3))
    self.assertEqual((Block('minecraft:skull', 1), '{SkullType:1b}'),
                     blockOf(MCBlocks.WitherSkeletonSkull, Version.V1_7_10))
    self.assertEqual((Block('minecraft:flower_pot', 0), '{Item:38,Data:0}'),
                     blockOf(MCBlocks.PottedPoppy, Version.V1_7_10))

  def test_an_entity(self) -> None:
    """Its type and its data, '' for none."""
    self.assertEqual(('Skeleton', '{SkeletonType:1}'),
                     entityOf(MCEntities.WitherSkeleton, Version.V1_7_10))
    self.assertEqual(('minecraft:wither_skeleton', ''),
                     entityOf(MCEntities.WitherSkeleton, Version.V26_3))
    self.assertEqual(('Zombie', ''),
                     entityOf(MCEntities.Zombie, Version.V1_7_10))

  def test_a_dimension(self) -> None:
    """1.7.10's number, which its probe takes, or the modern name."""
    self.assertEqual(-1, dimensionOf(MCDimensions.TheNether,
                                     Version.V1_7_10))
    self.assertEqual('minecraft:the_nether',
                     dimensionOf(MCDimensions.TheNether, Version.V26_3))

  def test_every_member_of_1_7_10_and_26_3_turns_into_probe_values(
      self) -> None:
    """No id mcdex holds there is one the probe can't be given."""
    kinds = ((MCItems, lambda m, v: itemOf(m, v)), (MCBlocks, blockOf),
             (MCEntities, entityOf), (MCDimensions, dimensionOf))
    for catalogue, convert in kinds:
      for version in VERSIONS:
        for member in held(catalogue, version):
          with self.subTest(member=str(member), version=str(version)):
            convert(member, version)

  def test_a_member_of_another_catalogue_is_refused(self) -> None:
    """A block where an item goes is the test's mistake."""
    with self.assertRaises(TypeError):
      itemOf(MCBlocks.RedWool, Version.V1_7_10)
    with self.assertRaises(TypeError):
      blockOf(MCItems.PinkWool, Version.V1_7_10)
    with self.assertRaises(TypeError):
      entityOf(MCItems.PinkWool, Version.V1_7_10)
    with self.assertRaises(TypeError):
      dimensionOf(MCEntities.Zombie, Version.V1_7_10)


class MissingTests(unittest.TestCase):
  """What vanilla lacks, and what mcdex has no data for."""

  def test_a_thing_vanilla_lacks_is_missing(self) -> None:
    """A FAIL with mcdex's reason (SPEC.md 13.2, 14.4)."""
    with self.assertRaises(Missing) as raised:
      itemOf(MCItems.Elytra, Version.V1_7_10)
    self.assertIsInstance(raised.exception, NeedFailed)
    self.assertIsInstance(raised.exception, AssertionError)
    self.assertIn('MCItems.Elytra', str(raised.exception))
    self.assertIn("Vanilla 1.7.10 has no 'elytra'", str(raised.exception))
    self.assertIs(MCItems.Elytra, raised.exception.member)
    self.assertIs(Version.V1_7_10, raised.exception.version)

  def test_no_data_for_the_version_is_no_result(self) -> None:
    """mcdex can't say whether the game has it (M3)."""
    particle = list(MCParticles)[0]
    with self.assertRaises(NoMcdexData) as raised:
      resolve(particle, Version.V1_7_10)
    self.assertIsInstance(raised.exception, NoResult)
    self.assertIn('no data', str(raised.exception))


class ReadBackTests(unittest.TestCase):
  """A value the game reports, as the set of members its id fits."""

  def test_an_item(self) -> None:
    self.assertEqual({MCItems.PinkWool},
                     membersOf(Item('minecraft:wool', 1, 6),
                               Version.V1_7_10))
    self.assertEqual({MCItems.PinkWool},
                     membersOf(Item('minecraft:pink_wool', 1, 0),
                               Version.V26_3))

  def test_twins_are_both(self) -> None:
    """Two members with one id: the game can't tell them apart."""
    for version in VERSIONS:
      with self.subTest(version=str(version)):
        self.assertEqual({MCItems.Steak, MCItems.CookedBeef},
                         membersOf(Item('minecraft:cooked_beef', 1, 0),
                                   version))

  def test_an_old_id_two_things_shared(self) -> None:
    """1.12.2's pumpkin was both the pumpkin and the carved one."""
    self.assertEqual({MCBlocks.Pumpkin, MCBlocks.CarvedPumpkin},
                     membersOf(Block('minecraft:pumpkin', 0),
                               Version.V1_12_2))

  def test_a_tool_s_damage_is_no_meta(self) -> None:
    """mcdex's id has no meta, so the item's (its damage) doesn't count."""
    self.assertEqual({MCItems.IronPickaxe},
                     membersOf(Item('minecraft:iron_pickaxe', 1, 37),
                               Version.V1_7_10))

  def test_a_spawn_egg_s_data_is_a_subset(self) -> None:
    """The egg's reported data holds more than its EntityTag."""
    egg = Item('minecraft:spawn_egg', 1, 0,
               '{EntityTag:{id:"Bat"},display:{Name:"Flappy"}}')
    self.assertEqual({MCItems.BatSpawnEgg}, membersOf(egg, Version.V1_10))

  def test_block_entity_data_tells_blocks_apart(self) -> None:
    """The most specific match wins: a potted poppy is no empty pot."""
    skull = Block('minecraft:skull', 1, True, '{SkullType:1b,Rot:4b}')
    self.assertEqual({MCBlocks.WitherSkeletonSkull},
                     membersOf(skull, Version.V1_7_10))
    pot = Block('minecraft:flower_pot', 0, True, '{Item:38,Data:0}')
    self.assertEqual({MCBlocks.PottedPoppy},
                     membersOf(pot, Version.V1_7_10))
    empty = Block('minecraft:flower_pot', 0, True, '{Item:0,Data:0}')
    self.assertEqual({MCBlocks.FlowerPot}, membersOf(empty, Version.V1_7_10))

  def test_data_not_read_is_refused(self) -> None:
    """A block or entity whose members differ by data, its data unread."""
    with self.assertRaises(ValueError):
      membersOf(Block('minecraft:skull', 1), Version.V1_7_10)
    with self.assertRaises(ValueError):
      membersOf(Entity(type='Skeleton'), Version.V1_7_10)

  def test_an_entity_by_its_data(self) -> None:
    """1.7.10's wither skeleton is a skeleton of type 1; numbers by value."""
    wither = Entity(type='Skeleton', nbtAsked=True,
                    snbt='{SkeletonType:1b,Health:20s}')
    plain = Entity(type='Skeleton', nbtAsked=True, snbt='{SkeletonType:0b}')
    self.assertEqual({MCEntities.WitherSkeleton},
                     membersOf(wither, Version.V1_7_10))
    self.assertEqual({MCEntities.Skeleton},
                     membersOf(plain, Version.V1_7_10))
    self.assertEqual({MCEntities.WitherSkeleton},
                     membersOf(Entity(type='minecraft:wither_skeleton'),
                               Version.V26_3))

  def test_an_effect(self) -> None:
    """1.7.10's by its number, 26.3's by its name."""
    self.assertEqual({MCEffects.Poison},
                     membersOf(Effect(id=19), Version.V1_7_10))
    self.assertEqual({MCEffects.Poison},
                     membersOf(Effect(effect='minecraft:poison'),
                               Version.V26_3))

  def test_an_id_mcdex_has_no_member_for_is_an_empty_set(self) -> None:
    """1.7.10's lit furnace (M6): the assertion says what that means."""
    self.assertEqual(set(), membersOf(Block('minecraft:lit_furnace', 2),
                                      Version.V1_7_10))


class DeclaredTests(unittest.TestCase):
  """A mod's declarations of what vanilla lacks (SPEC.md 14.4, M4)."""

  def declared(self) -> dict:
    return {MCItems.Elytra: (parse('etfuturum:elytra'), 'robert.Hooks')}

  def test_a_declared_thing_resolves_to_the_mod_s_id(self) -> None:
    self.assertEqual(ThingId('etfuturum:elytra'),
                     resolve(MCItems.Elytra, Version.V1_7_10,
                             self.declared()))
    self.assertEqual(Item('etfuturum:elytra', 1, 0),
                     itemOf(MCItems.Elytra, Version.V1_7_10,
                            declared=self.declared()))

  def test_it_reads_back_as_the_member(self) -> None:
    self.assertEqual({MCItems.Elytra},
                     membersOf(Item('etfuturum:elytra', 1, 0),
                               Version.V1_7_10, self.declared()))

  def test_undeclared_is_still_missing_and_says_so(self) -> None:
    with self.assertRaises(Missing) as raised:
      resolve(MCItems.Elytra, Version.V1_7_10, {})
    self.assertIn('no mod declares it', str(raised.exception))


class _Game:
  """A game's version, declarations and reading back, without a game."""

  def __init__(self, version: Version) -> None:
    self.version = version

  def declared(self) -> dict:
    return {}

  def membersOf(self, value: object) -> frozenset:
    return membersOf(value, self.version)


class AssertThingTests(unittest.TestCase):
  """GameTestCase.assertThing: a value the game reported, as a member."""

  def case(self, version: Version) -> GameTestCase:
    class Case(GameTestCase):
      def runTest(self) -> None:
        pass

    case = Case()
    case.game = _Game(version)
    return case

  def test_it_passes_for_any_member_the_value_is(self) -> None:
    case = self.case(Version.V1_7_10)
    case.assertThing(Item('minecraft:wool', 1, 6), MCItems.PinkWool)
    case.assertThing(Item('minecraft:cooked_beef', 1, 0), MCItems.Steak)
    case.assertThing(Item('minecraft:cooked_beef', 1, 0),
                     MCItems.CookedBeef)

  def test_another_thing_fails_naming_both_ids(self) -> None:
    case = self.case(Version.V1_7_10)
    with self.assertRaises(AssertionError) as raised:
      case.assertThing(Item('minecraft:wool', 1, 14), MCItems.PinkWool)
    said = str(raised.exception)
    self.assertIn('minecraft:wool:14', said)
    self.assertIn('MCItems.PinkWool', said)
    self.assertIn('minecraft:wool:6', said)

  def test_an_empty_slot_fails(self) -> None:
    case = self.case(Version.V1_7_10)
    with self.assertRaises(AssertionError) as raised:
      case.assertThing(Item.EMPTY, MCItems.PinkWool)
    self.assertIn('empty', str(raised.exception))

  def test_a_member_vanilla_lacks_is_missing(self) -> None:
    case = self.case(Version.V1_7_10)
    with self.assertRaises(Missing):
      case.assertThing(Item('minecraft:stone', 1, 0), MCItems.Elytra)

  def test_a_value_mcdex_knows_no_member_for_is_no_result(self) -> None:
    """M6: the game may well be right, and unitTAS can't tell."""
    case = self.case(Version.V1_7_10)
    with self.assertRaises(NoMcdexThing) as raised:
      case.assertThing(Block('minecraft:lit_furnace', 2), MCBlocks.Furnace)
    self.assertIsInstance(raised.exception, NoResult)
    self.assertIn('minecraft:lit_furnace', str(raised.exception))


if __name__ == '__main__':
  unittest.main()

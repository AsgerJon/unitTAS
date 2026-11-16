"""
Things by mcdex member (SPEC.md 14.3, 14.5 steps 2 and 3), without a
game: each id mcdex holds for a version read into its parts and turned
into what the probe takes, exactly as the spec's table has them, for
every id mcdex holds for 1.7.10 and 26.3 in the catalogues the API
takes; a thing vanilla lacks there is Missing, and a version mcdex has
no data for is no result.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import unittest

from mcdex import (MCBlocks, MCDimensions, MCEffects, MCEntities, MCItems,
                   MCParticles, NotInVersion, Version)

from unittas.errors import Missing, NeedFailed, NoMcdexData, NoResult
from unittas.things import (ThingId, blockOf, dimensionOf, entityOf, itemOf,
                            parse, resolve)
from unittas.values import Block, Item

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


if __name__ == '__main__':
  unittest.main()

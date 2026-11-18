"""
GameTestCases in worlds of their own (SPEC.md 17.3, 17.8), for
test_worldruns.py to run on the run's port (19.7 step 9c): not a test
module (the probe's discovery doesn't load it). Things by mcdex member
(1.7.10's leaves the kind that never decays), heights from the port's
start, a rule by the version's own name.

- test_a, decorated by no world, runs in the run's flat world: its
  ground found from its start, never at a fixed height (tall grass
  isn't ground, leaves are);
- Terrain, a seeded world of default terrain: test_b leaves wool, and
  test_c finds it, since a world's tests share it;
- Arena, fresh: its setUp places gold once; test_d finds it and breaks
  it, and test_e finds it again, in the copy kept after setUp;
- Layered, a flat world described in mcdex's terms (SPEC.md 17.4):
  bedrock, two stone and red wool on desert, its daylight cycle off;
  test_f stands on its red wool.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import math

from worktoy.desc import FixBox

from mcdex import MCBiomes, MCBlocks, MCGameRules

from ports import V1_7_10, V26_3, start, version
from unittas._test_world import World
from unittas.testcase import GameTestCase
from unittas.values import Block, Vec3
from unittas.worldkind import WorldKind


def leaves():
  """
  Leaves for the ground's test: 1.7.10's that never decay (meta 4), oak
  leaves from 1.13 on.
  """
  if version() == V1_7_10:
    return Block('minecraft:leaves', 4)
  return MCBlocks.OakLeaves


def flatFeet() -> float:
  """The height a player stands at in the port's flat test world."""
  return start()[1]


def daylight() -> str:
  """The day's cycle's rule, as the version names it (AdvanceTime)."""
  return 'advance_time' if version() == V26_3 else 'doDaylightCycle'


def near(start: Vec3) -> tuple:
  """Two blocks east of where the world's start is, at the feet."""
  return (int(math.floor(start.x)) + 2, int(math.floor(start.y)),
          int(math.floor(start.z)))


class Terrain(World):
  """Default terrain from a seed."""

  seed = FixBox[int](8675309)


class Arena(World):
  """A world whose tests each enter it as its setUp left it."""

  fresh = FixBox[bool](True)

  def setUp(self) -> None:
    self.game.setBlock(near(self.start), MCBlocks.GoldBlock)


class Layered(World):
  """A flat world of the version's own blocks for mcdex's."""

  kind = FixBox[WorldKind](WorldKind.Flat)
  layers = FixBox[tuple](((MCBlocks.Bedrock, 1), (MCBlocks.Stone, 2),
                          (MCBlocks.RedWool, 1)))
  flatBiome = FixBox[MCBiomes](MCBiomes.Desert)
  rules = FixBox[dict]({MCGameRules.AdvanceTime: False})


class EWorldTests(GameTestCase):
  """Each test in its world."""

  terrain = Terrain()
  arena = Arena()
  layered = Layered()

  def test_a_in_the_run_s_flat_world(self) -> None:
    under = self.start.block().below()
    self.assertThing(self.game.block(under), MCBlocks.GrassBlock)
    self.assertEqual(under, self.game.ground(under.x, under.z))
    #  tall grass doesn't stop movement; leaves do (SPEC.md 14.5 step 7)
    grass = under.offset(3, 1, 0)
    self.game.setBlock(grass, MCBlocks.ShortGrass)
    self.assertEqual(under.offset(3, 0, 0),
                     self.game.ground(grass.x, grass.z))
    above = under.offset(4, 3, 0)
    self.game.setBlock(above, leaves())
    self.assertEqual(above, self.game.ground(above.x, above.z))

  @terrain
  def test_b_leaves_wool(self) -> None:
    #  default terrain: the game put the player well above the flat world,
    #  on its ground
    start = self.terrain.start
    self.assertGreater(start.y, flatFeet() + 6.0)
    self.assertEqual(self.start, start)
    ground = self.game.ground(start.block().x, start.block().z)
    self.assertEqual(start.block().below().y, ground.y)
    self.game.setBlock(near(self.terrain.start), MCBlocks.RedWool)
    self.assertThing(self.game.block(near(self.terrain.start)),
                     MCBlocks.RedWool)

  @terrain
  def test_c_finds_the_wool(self) -> None:
    self.assertThing(self.game.block(near(self.terrain.start)),
                     MCBlocks.RedWool)

  @arena
  def test_d_breaks_the_gold(self) -> None:
    pos = near(self.arena.start)
    self.assertThing(self.game.block(pos), MCBlocks.GoldBlock)
    self.game.setBlock(pos, 'minecraft:air')
    self.assertEqual('minecraft:air', self.game.block(pos).id)

  @arena
  def test_e_finds_the_gold_again(self) -> None:
    self.assertThing(self.game.block(near(self.arena.start)),
                     MCBlocks.GoldBlock)

  @layered
  def test_f_on_its_own_layers(self) -> None:
    under = self.start.block().below()
    self.assertThing(self.game.block(under), MCBlocks.RedWool)
    self.assertEqual(under, self.game.ground(under.x, under.z))
    self.assertThing(self.game.block(under.below()), MCBlocks.Stone)
    rules = self.game.request('world.get')['rules']
    self.assertEqual('false', rules[daylight()])

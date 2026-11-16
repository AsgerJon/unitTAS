"""
GameTestCases in worlds of their own (SPEC.md 17.3, 17.8), for
test_worldruns.py to run in the development client: not a test module
(the probe's discovery doesn't load it).

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

from unittas._test_world import World
from unittas.testcase import GameTestCase
from unittas.values import Block, Vec3
from unittas.worldkind import WorldKind

WOOL = Block('minecraft:wool', 14)
GOLD = Block('minecraft:gold_block', 0)


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
    self.game.setBlock(near(self.start), 'minecraft:gold_block')


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
    self.assertEqual(Block('minecraft:grass', 0), self.game.block(under))
    self.assertEqual(under, self.game.ground(under.x, under.z))
    #  tall grass doesn't stop movement; leaves do (SPEC.md 14.5 step 7)
    grass = under.offset(3, 1, 0)
    self.game.setBlock(grass, Block('minecraft:tallgrass', 1))
    self.assertEqual(under.offset(3, 0, 0),
                     self.game.ground(grass.x, grass.z))
    leaves = under.offset(4, 3, 0)
    self.game.setBlock(leaves, Block('minecraft:leaves', 4))
    self.assertEqual(leaves, self.game.ground(leaves.x, leaves.z))

  @terrain
  def test_b_leaves_wool(self) -> None:
    #  default terrain: the game put the player well above the flat world,
    #  on its ground
    start = self.terrain.start
    self.assertGreater(start.y, 10.0)
    self.assertEqual(self.start, start)
    ground = self.game.ground(start.block().x, start.block().z)
    self.assertEqual(start.block().below().y, ground.y)
    self.game.setBlock(near(self.terrain.start), WOOL)
    self.assertEqual(WOOL, self.game.block(near(self.terrain.start)))

  @terrain
  def test_c_finds_the_wool(self) -> None:
    self.assertEqual(WOOL, self.game.block(near(self.terrain.start)))

  @arena
  def test_d_breaks_the_gold(self) -> None:
    pos = near(self.arena.start)
    self.assertEqual(GOLD, self.game.block(pos))
    self.game.setBlock(pos, 'minecraft:air')
    self.assertEqual(Block('minecraft:air', 0), self.game.block(pos))

  @arena
  def test_e_finds_the_gold_again(self) -> None:
    self.assertEqual(GOLD, self.game.block(near(self.arena.start)))

  @layered
  def test_f_on_its_own_layers(self) -> None:
    under = self.start.block().below()
    self.assertThing(self.game.block(under), MCBlocks.RedWool)
    self.assertEqual(under, self.game.ground(under.x, under.z))
    self.assertThing(self.game.block(under.below()), MCBlocks.Stone)
    rules = self.game.request('world.get')['rules']
    self.assertEqual('false', rules['doDaylightCycle'])

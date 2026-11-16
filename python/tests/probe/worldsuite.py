"""
GameTestCases in worlds of their own (SPEC.md 17.3, 17.8), for
test_worldruns.py to run in the development client: not a test module
(the probe's discovery doesn't load it).

- test_a, decorated by no world, runs in the run's flat world;
- Terrain, a seeded world of default terrain: test_b leaves wool, and
  test_c finds it, since a world's tests share it;
- Arena, fresh: its setUp places gold once; test_d finds it and breaks
  it, and test_e finds it again, in the copy kept after setUp.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import math

from worktoy.desc import FixBox

from unittas._test_world import World
from unittas.testcase import GameTestCase
from unittas.values import Block, Vec3

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


class EWorldTests(GameTestCase):
  """Each test in its world."""

  terrain = Terrain()
  arena = Arena()

  def test_a_in_the_run_s_flat_world(self) -> None:
    self.assertEqual(Block('minecraft:grass', 0), self.game.block((0, 3, 0)))

  @terrain
  def test_b_leaves_wool(self) -> None:
    #  default terrain: the game put the player well above the flat world
    self.assertGreater(self.terrain.start.y, 10.0)
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

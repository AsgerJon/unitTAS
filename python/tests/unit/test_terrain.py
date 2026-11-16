"""
Terrain (SPEC.md 15.6 step 7): what the agent knows of the ground around
it from what it perceives. Where a player stands in each column (on a
block, a slab, a stair's top, not in water, not under a low ceiling),
and the ways between columns: walking up half a block as the game steps,
jumping up a block with room above, dropping down three; up a ladder
to a ledge no higher than its top, and down one; into water, across it
at its top and out onto a bank level with it, never into lava. A path
from
where it stands to a place, straightened where a straight line is clear,
around what is in the way; to the edge of what it sees, towards a place
further off; none to a place it can't get to.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import math
import unittest

from unittas.box import Box
from unittas.nearblock import NearBlock
from unittas.perception import Perception
from unittas.terrain import Terrain
from unittas.values import BlockPos, Vec3


def block(x: int, y: int, z: int, top: float = 1.0,
          liquid: bool = False) -> NearBlock:
  """A block at (x, y, z), its box 'top' high; a liquid has none."""
  boxes = () if liquid else (Box(x, y, z, x + 1, y + top, z + 1),)
  return NearBlock(BlockPos(x, y, z), 'minecraft:stone', 0, boxes, liquid,
                   False, False)


def door(x: int, z: int, opens: bool = True) -> list:
  """A door's two halves at (x, 4, z) and (x, 5, z), shut along z's edge."""
  return [NearBlock(BlockPos(x, y, z), 'minecraft:wooden_door', 0,
                    (Box(x, y, z, x + 1, y + 1, z + 0.1875),), False, False,
                    opens) for y in (4, 5)]


#  A ladder's box along each edge of its block, and the meta that says so
EDGES = {'south': (2, (0.0, 0.875, 1.0, 1.0)),
         'north': (3, (0.0, 0.0, 1.0, 0.125)),
         'east': (4, (0.875, 0.0, 1.0, 1.0)),
         'west': (5, (0.0, 0.0, 0.125, 1.0))}


def liquid(x: int, y: int, z: int, kind: str = 'water') -> NearBlock:
  """A liquid's block (no box): water, or lava."""
  return NearBlock(BlockPos(x, y, z), 'minecraft:%s' % kind, 0, (), True,
                   False, False)


def ladder(x: int, z: int, ys: range, edge: str = 'south') -> list:
  """A ladder's blocks at (x, y, z) for each y, along the edge named."""
  meta, (x0, z0, x1, z1) = EDGES[edge]
  return [NearBlock(BlockPos(x, y, z), 'minecraft:ladder', meta,
                    (Box(x + x0, y, z + z0, x + x1, y + 1, z + z1),),
                    False, True, False) for y in ys]


def seen(blocks: list, feet: Vec3 = Vec3(0.5, 4.0, 0.5),
         around: int = 8) -> Perception:
  """A perception on flat ground (its top at y 4), and these blocks."""
  taken = {each.pos for each in blocks}
  ground = [block(x, 3, z) for x in range(-around, around + 1)
            for z in range(-around, around + 1)
            if BlockPos(x, 3, z) not in taken]
  return Perception(pos=feet, eye=feet.above(1.62), blocks=tuple(
    ground + list(blocks)))


def terrain(blocks: list = (), feet: Vec3 = Vec3(0.5, 4.0, 0.5)) -> Terrain:
  return Terrain(seen(list(blocks), feet), around=8, below=3, above=3)


def wall(z: int, xs: range, high: int = 2) -> list:
  return [block(x, 4 + y, z) for x in xs for y in range(high)]


class FloorTests(unittest.TestCase):

  def test_where_a_player_stands(self) -> None:
    here = terrain([block(2, 4, 2, 0.5), block(3, 4, 3),
                    block(4, 3, 4, liquid=True), block(5, 4, 5),
                    block(5, 5, 5), block(6, 5, 6)])
    self.assertEqual((4.0,), here.floors(0, 0))
    self.assertEqual((4.5,), here.floors(2, 2), 'a slab')
    self.assertEqual((5.0,), here.floors(3, 3), 'on a block')
    self.assertEqual((), here.floors(4, 4), 'not in water')
    self.assertEqual((6.0,), here.floors(5, 5), 'on a pillar of two')
    self.assertEqual((6.0,), here.floors(6, 6),
                     'on a block a head high, not under it')
    self.assertEqual((), here.floors(20, 0), 'nothing seen there')


class PathTests(unittest.TestCase):

  def assertStandable(self, here: Terrain, path: list) -> None:
    for point in path:
      floors = here.floors(math.floor(point.x), math.floor(point.z))
      self.assertIn(point.y, floors, point)

  def test_straight_on_open_ground(self) -> None:
    path, whole = terrain().path(Vec3(0.5, 4.0, 0.5), Vec3(5.5, 4.0, 3.5))
    self.assertTrue(whole)
    self.assertEqual([Vec3(5.5, 4.0, 3.5)], path)

  def test_around_a_wall(self) -> None:
    here = terrain(wall(3, range(-3, 4)))
    path, whole = here.path(Vec3(0.5, 4.0, 0.5), Vec3(0.5, 4.0, 6.5))
    self.assertTrue(whole)
    self.assertGreater(len(path), 1)
    self.assertStandable(here, path)
    #  past one end of the wall
    self.assertTrue(any(abs(point.x - 0.5) > 3 for point in path), path)
    self.assertEqual(Vec3(0.5, 4.0, 6.5), path[-1])

  def test_up_a_slab_and_a_step(self) -> None:
    here = terrain([block(0, 4, 3, 0.5), block(0, 4, 5)])
    path, whole = here.path(Vec3(0.5, 4.0, 0.5), Vec3(0.5, 5.0, 5.5))
    self.assertTrue(whole)
    self.assertStandable(here, path)
    self.assertEqual(Vec3(0.5, 5.0, 5.5), path[-1])
    #  onto the block by a jump: the waypoint before it kept, beside it
    before = path[-2]
    self.assertEqual(4.0, before.y)
    self.assertEqual(1.0, abs(before.x - 0.5) + abs(before.z - 5.5))

  def test_not_up_two(self) -> None:
    here = terrain([block(0, 4, 3), block(0, 5, 3)])
    path, whole = here.path(Vec3(0.5, 4.0, 0.5), Vec3(0.5, 6.0, 3.5))
    self.assertIsNone(path)

  def test_no_room_to_jump(self) -> None:
    """A block over the head: no jump onto the step beside it."""
    here = terrain([block(0, 4, 1), block(0, 6, 0)] +
                   wall(1, [x for x in range(-8, 9) if x != 0], 3))
    path, whole = here.path(Vec3(0.5, 4.0, 0.5), Vec3(0.5, 5.0, 1.5))
    self.assertIsNone(path)

  def test_down_a_drop(self) -> None:
    pillar = [block(0, 4, 0), block(0, 5, 0)]
    here = terrain(pillar, feet=Vec3(0.5, 6.0, 0.5))
    path, whole = here.path(Vec3(0.5, 6.0, 0.5), Vec3(3.5, 4.0, 0.5))
    self.assertTrue(whole)
    self.assertStandable(here, path)
    self.assertEqual(Vec3(3.5, 4.0, 0.5), path[-1])

  def test_not_down_four(self) -> None:
    here = Terrain(Perception(pos=Vec3(0.5, 8.0, 0.5), blocks=tuple(
      [block(0, y, 0) for y in range(4, 8)] +
      [block(x, 3, z) for x in range(-8, 9) for z in range(-8, 9)])),
      around=8, below=5, above=1)
    path, whole = here.path(Vec3(0.5, 8.0, 0.5), Vec3(3.5, 4.0, 0.5))
    self.assertIsNone(path)

  def test_not_between_two_corners(self) -> None:
    """A place got to only across two walls' touching corners: no way."""
    shut = [(1, 0), (0, 1), (2, 1), (1, 2), (2, 0), (0, 2), (2, 2)]
    here = terrain([block(x, 4 + y, z) for x, z in shut for y in range(2)])
    path, whole = here.path(Vec3(0.5, 4.0, 0.5), Vec3(1.5, 4.0, 1.5))
    self.assertIsNone(path)

  def test_through_a_door(self) -> None:
    """A door's column is passable, by opening it: its waypoint kept."""
    here = terrain(wall(3, [x for x in range(-8, 9) if x != 0]) +
                   door(0, 3))
    self.assertEqual(2, len(here.doors(0, 3)))
    path, whole = here.path(Vec3(0.5, 4.0, 0.5), Vec3(0.5, 4.0, 6.5))
    self.assertTrue(whole)
    self.assertIn(Vec3(0.5, 4.0, 3.5), path)
    #  and the waypoint before it, beside it
    before = path[path.index(Vec3(0.5, 4.0, 3.5)) - 1]
    self.assertEqual(1.0, abs(before.x - 0.5) + abs(before.z - 3.5))

  def test_not_straight_through_a_door_beside_the_way(self) -> None:
    """A door standing on open ground: the way keeps out of its column."""
    here = terrain(door(2, 3))
    path, whole = here.path(Vec3(0.5, 4.0, 0.5), Vec3(4.5, 4.0, 6.5))
    here_ = Vec3(0.5, 4.0, 0.5)
    for there in path:
      for k in range(101):
        x = here_.x + (there.x - here_.x) * k / 100
        z = here_.z + (there.z - here_.z) * k / 100
        self.assertNotEqual((2, 3), (math.floor(x), math.floor(z)), path)
      here_ = there

  def test_not_through_an_iron_door(self) -> None:
    here = terrain(wall(3, [x for x in range(-8, 9) if x != 0]) +
                   door(0, 3, opens=False))
    self.assertEqual((), here.doors(0, 3))
    path, whole = here.path(Vec3(0.5, 4.0, 0.5), Vec3(0.5, 4.0, 6.5))
    self.assertIsNone(path)

  def test_shut_in(self) -> None:
    box = (wall(4, range(2, 7)) + wall(8, range(2, 7)) +
           [block(x, 4 + y, z) for x in (2, 6) for z in range(5, 8)
            for y in range(2)])
    path, whole = terrain(box).path(Vec3(0.5, 4.0, 0.5),
                                    Vec3(4.5, 4.0, 6.5))
    self.assertIsNone(path)

  def test_towards_a_place_further_off(self) -> None:
    """On the straight line to it, just inside what it sees."""
    here = terrain()
    path, whole = here.path(Vec3(0.5, 4.0, 0.5), Vec3(30.5, 4.0, 0.5))
    self.assertFalse(whole)
    self.assertEqual([Vec3(8.0, 4.0, 0.5)], path)

  def test_towards_it_around_a_wall(self) -> None:
    """The line blocked: to the seen place nearest it, round the wall."""
    here = terrain([block(5, 4 + y, z) for z in range(-8, 9) if z != 6
                    for y in range(2)])
    path, whole = here.path(Vec3(0.5, 4.0, 0.5), Vec3(30.5, 4.0, 0.5))
    self.assertFalse(whole)
    self.assertStandable(here, path)
    self.assertEqual(8, math.floor(path[-1].x))

  def test_where_it_stands(self) -> None:
    path, whole = terrain().path(Vec3(0.5, 4.0, 0.5), Vec3(0.8, 4.0, 0.2))
    self.assertEqual(([Vec3(0.8, 4.0, 0.2)], True), (path, whole))


class LadderTests(unittest.TestCase):
  """
  A wall four high across z 3, and a ladder on its north face at x 0
  (its blocks at z 2, their boxes along their south edge).
  """

  def high(self, ys: range = range(4, 8), feet: Vec3 = Vec3(0.5, 4.0, 0.5),
           below: int = 3) -> Terrain:
    blocks = (wall(3, range(-8, 9), 4) + ladder(0, 2, ys) +
              [block(x, 3, z) for x in range(-8, 9) for z in range(-8, 9)
               if z != 3])
    return Terrain(Perception(pos=feet, eye=feet.above(1.62),
                              blocks=tuple(blocks)),
                   around=8, below=below, above=4)

  def test_a_ladder_is_no_wall(self) -> None:
    """Its thin box doesn't fill its column: a player stands under it."""
    here = self.high()
    self.assertEqual((4.0,), here.floors(0, 2))
    self.assertEqual([4, 5, 6, 7],
                     [near.pos.y for near in here.ladders(0, 2)])
    self.assertTrue(here.climbable(0, 2, 7))
    self.assertFalse(here.climbable(0, 2, 8))
    self.assertEqual((8.0,), here.floors(0, 3), 'the wall\'s top')

  def test_up_a_ladder(self) -> None:
    here = self.high()
    path, whole = here.path(Vec3(0.5, 4.0, 0.5), Vec3(0.5, 8.0, 3.5))
    self.assertTrue(whole)
    #  to its foot, then up it onto the wall
    self.assertEqual([Vec3(0.5, 4.0, 2.5), Vec3(0.5, 8.0, 3.5)], path[-2:])

  def test_not_above_its_top(self) -> None:
    here = self.high(ys=range(4, 6))
    path, whole = here.path(Vec3(0.5, 4.0, 0.5), Vec3(0.5, 8.0, 3.5))
    self.assertIsNone(path)

  def test_down_a_ladder(self) -> None:
    here = self.high(feet=Vec3(0.5, 8.0, 3.5), below=5)
    path, whole = here.path(Vec3(0.5, 8.0, 3.5), Vec3(0.5, 4.0, 0.5))
    self.assertTrue(whole)
    self.assertEqual([Vec3(0.5, 4.0, 2.5), Vec3(0.5, 4.0, 0.5)], path)

  def test_not_down_four_without_one(self) -> None:
    here = self.high(ys=range(0), feet=Vec3(0.5, 8.0, 3.5), below=5)
    path, whole = here.path(Vec3(0.5, 8.0, 3.5), Vec3(0.5, 4.0, 0.5))
    self.assertIsNone(path)


class WaterTests(unittest.TestCase):
  """
  A trench across the way, z 2 to 4 from x -8 to 8, filled with water
  (or lava) to the ground's top: its blocks at y 3, 'deep' of them.
  """

  def trench(self, kind: str = 'water', deep: int = 1,
             feet: Vec3 = Vec3(0.5, 4.0, 0.5), more: list = ()) -> Terrain:
    wet = {(x, y, z) for x in range(-8, 9) for z in (2, 3, 4)
           for y in range(4 - deep, 4)}
    blocks = ([liquid(x, y, z, kind) for x, y, z in sorted(wet)] +
              [block(x, y, z) for x in range(-8, 9) for z in range(-8, 9)
               for y in range(3 - deep, 4) if (x, y, z) not in wet] +
              list(more))
    return Terrain(Perception(pos=feet, eye=feet.above(1.62),
                              blocks=tuple(blocks)),
                   around=8, below=3, above=3)

  def test_its_top(self) -> None:
    """A player swims at the water's top, and stands nowhere in it."""
    here = self.trench(deep=2)
    self.assertEqual((4.0,), here.surfaces(0, 3))
    self.assertEqual((), here.floors(0, 3))
    self.assertTrue(here.wet(0, 3, 4.0))
    self.assertFalse(here.wet(0, 1, 4.0))
    self.assertEqual((), here.surfaces(0, 1))

  def test_across_water(self) -> None:
    """In, across (straight on), out: each change of way kept."""
    here = self.trench()
    path, whole = here.path(Vec3(0.5, 4.0, 0.5), Vec3(0.5, 4.0, 6.5))
    self.assertTrue(whole)
    self.assertEqual([Vec3(0.5, 4.0, z + 0.5) for z in (1, 2, 4, 5, 6)],
                     path)

  def test_from_in_the_water(self) -> None:
    here = self.trench(deep=2, feet=Vec3(0.5, 3.6, 3.5))
    path, whole = here.path(Vec3(0.5, 3.6, 3.5), Vec3(0.5, 4.0, 6.5))
    self.assertTrue(whole)
    self.assertEqual(Vec3(0.5, 4.0, 6.5), path[-1])

  def test_not_out_onto_a_higher_bank(self) -> None:
    here = self.trench(more=[block(x, 4, 5) for x in range(-8, 9)])
    path, whole = here.path(Vec3(0.5, 4.0, 0.5), Vec3(0.5, 5.0, 5.5))
    self.assertIsNone(path)

  def test_not_under_a_lid(self) -> None:
    """Water with a block on it: no top to swim at, no way across."""
    here = self.trench(more=[block(x, 4, 3) for x in range(-8, 9)])
    self.assertEqual((), here.surfaces(0, 3))
    path, whole = here.path(Vec3(0.5, 4.0, 0.5), Vec3(0.5, 4.0, 6.5))
    self.assertIsNone(path)

  def test_never_into_lava(self) -> None:
    here = self.trench(kind='lava')
    self.assertEqual((), here.surfaces(0, 3))
    path, whole = here.path(Vec3(0.5, 4.0, 0.5), Vec3(0.5, 4.0, 6.5))
    self.assertIsNone(path)


if __name__ == '__main__':
  unittest.main()

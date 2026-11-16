"""
Terrain (SPEC.md 15.6 step 7): what the agent knows of the ground around
it from what it perceives. Where a player stands in each column (on a
block, a slab, a stair's top, not in water, not under a low ceiling),
and the ways between columns: walking up half a block as the game steps,
jumping up a block with room above, dropping down three. A path from
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
                   False)


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


if __name__ == '__main__':
  unittest.main()

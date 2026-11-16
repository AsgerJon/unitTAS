"""
Terrain: what the agent knows of the ground around it, from what it
perceives (SPEC.md 15.6 step 7): where a player stands, and the ways
between where it stands and a place.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import heapq
import math
from typing import TYPE_CHECKING

from worktoy.mcls import BaseObject

from .values import Vec3

if TYPE_CHECKING:  # pragma: no cover
  from typing import Iterator, Optional

  from .perception import Perception

_EPS = 1e-6
_AROUND = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1),
           (-1, -1))


class Terrain(BaseObject):
  """
  The ground within 'around' columns of where the player stands, from
  'below' blocks under its feet to 'above' over its head, as one
  perception showed it: each column's blocks by their collision boxes,
  and its liquids. A player stands on a box's top with its height free
  above, and not in a liquid. Between columns it walks (up or down as
  much as the game steps it), jumps up to JUMP with room above where it
  jumps from, or drops down to DROP; across a corner only walking, with
  both sides passable.

    path, whole = Terrain(seen, 8, 3, 3).path(seen.pos, place)
  """

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  NAMESPACE  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  #  Class Variables
  #  How far the game steps a player up as it walks (1.7.10's stepHeight)
  STEP = 0.5
  #  How far a jump lifts the feet: 0.42 up, 0.08 less a tick, 0.98 kept
  JUMP = 1.25
  #  How far a player drops unhurt
  DROP = 3.0
  #  A player's height
  HEIGHT = 1.8

  #  Fallback Variables

  #  Private Variables
  #  Each column's intervals, (bottom, top, liquid), by (x, z)
  __columns__: dict = None
  #  Each column's floors, once asked for
  __floors__: dict = None
  #  The column the player stood in, and how far around it is known
  __centre__: tuple = None
  __around__: int = 0

  #  Public Variables

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  CONSTRUCTORS   # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  def __init__(self, seen: Perception, around: int, below: int,
               above: int) -> None:
    """The ground 'seen' showed: perceived with around, below, above."""
    BaseObject.__init__(self)
    columns = {}
    for near in seen.blocks:
      column = columns.setdefault((near.pos.x, near.pos.z), [])
      if near.liquid:
        column.append((float(near.pos.y), near.pos.y + 1.0, True))
      for box in near.boxes:
        column.append((box.minY, box.maxY, False))
    self.__columns__ = columns
    self.__floors__ = {}
    self.__centre__ = (math.floor(seen.pos.x), math.floor(seen.pos.z))
    self.__around__ = around

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  DOMAIN SPECIFIC  # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  def inside(self, x: int, z: int) -> bool:
    """Whether the column (x, z) was seen."""
    cx, cz = self.__centre__
    return (abs(x - cx) <= self.__around__ and
            abs(z - cz) <= self.__around__)

  def floors(self, x: int, z: int) -> tuple:
    """The heights a player stands at in the column (x, z), lowest first."""
    if (x, z) not in self.__floors__:
      tops = sorted(set(top for _, top, liquid in
                        self.__columns__.get((x, z), ()) if not liquid))
      self.__floors__[(x, z)] = tuple(
        top for top in tops if self._clear(x, z, top, top + self.HEIGHT))
    return self.__floors__[(x, z)]

  def path(self, start: Vec3, goal: Vec3) -> tuple:
    """
    The way from 'start' to 'goal': (waypoints, whole). The waypoints
    are where to go in turn, each on a floor, the last 'goal' itself;
    straight on where a straight line is clear, kept before and after
    each jump and drop. For a goal outside what was seen, the way to the
    seen place nearest it, and 'whole' False. (None, True) when the goal
    was seen and can't be got to.
    """
    sx, sz = math.floor(start.x), math.floor(start.z)
    near = [f for f in self.floors(sx, sz) if abs(f - start.y) <= self.STEP]
    first = (sx, sz, min(near, key=lambda f: abs(f - start.y))
             if near else start.y)
    cost, came = self._search(first)
    gx, gz = math.floor(goal.x), math.floor(goal.z)
    whole = self.inside(gx, gz)
    if whole:
      ends = [node for node in cost if (node[0], node[1]) == (gx, gz) and
              abs(node[2] - goal.y) <= self.STEP + _EPS]
      if not ends:
        return None, True
      end = min(ends, key=lambda node: (abs(node[2] - goal.y), cost[node]))
    else:
      ahead = self._ahead(first, start, goal, cost)
      if ahead is not None:
        return [ahead], False
      end = min(cost, key=lambda node: (math.hypot(
        node[0] + 0.5 - goal.x, node[1] + 0.5 - goal.z) + abs(
        node[2] - goal.y), cost[node]))
    chain, kinds = [end], []
    while chain[-1] != first:
      before, kind = came[chain[-1]]
      kinds.append(kind)
      chain.append(before)
    chain.reverse()
    kinds.reverse()
    points = [Vec3(x + 0.5, h, z + 0.5) for x, z, h in self._straighten(
      chain, kinds)]
    if whole:
      #  the goal itself last; the only waypoint when it is where it stands
      floor = points[-1].y if points else end[2]
      points[-1:] = [Vec3(goal.x, floor, goal.z)]
    return points, whole

  # ---------------------------------------------------------------- inside

  def _ahead(self, first: tuple, start: Vec3, goal: Vec3,
             cost: dict) -> Optional[Vec3]:
    """
    The point on the straight line towards a goal further off, just
    inside what was seen, when that line is clear on the level; None.
    """
    dx, dz = goal.x - start.x, goal.z - start.z
    length = math.hypot(dx, dz)
    if length < _EPS:
      return None
    ux, uz = dx / length, dz / length
    cx, cz = self.__centre__
    t = (self.__around__ - 0.5) / max(abs(ux), abs(uz))
    px, pz = start.x + ux * t, start.z + uz * t
    x, z = math.floor(px), math.floor(pz)
    for node in cost:
      if (node[0], node[1]) == (x, z) and abs(
          node[2] - first[2]) <= self.STEP + _EPS and self._straight(
          first, node):
        return Vec3(px, node[2], pz)
    return None

  def _clear(self, x: int, z: int, low: float, high: float) -> bool:
    """Whether nothing in the column (x, z) is between low and high."""
    return not any(bottom < high - _EPS and top > low + _EPS
                   for bottom, top, _ in self.__columns__.get((x, z), ()))

  def _moves(self, node: tuple) -> Iterator[tuple]:
    """Where a player goes from 'node' in a step: (node, cost, kind)."""
    x, z, h = node
    for dx, dz in _AROUND:
      nx, nz = x + dx, z + dz
      if not self.inside(nx, nz):
        continue
      floors = self.floors(nx, nz)
      if dx and dz:
        for f in floors:
          if abs(f - h) <= self.STEP + _EPS and self._side(
              x + dx, z, h, f) and self._side(x, z + dz, h, f):
            yield (nx, nz, f), math.sqrt(2.0), 'walk'
        continue
      land = [f for f in floors if f <= h + self.STEP + _EPS]
      if land:
        f = max(land)
        if f >= h - self.STEP - _EPS:
          if self._clear(nx, nz, f, max(f, h) + self.HEIGHT):
            yield (nx, nz, f), 1.0, 'walk'
        elif h - f <= self.DROP + _EPS and self._clear(nx, nz, f,
                                                       h + self.HEIGHT):
          yield (nx, nz, f), 1.5, 'drop'
      for f in floors:
        if (self.STEP + _EPS < f - h <= self.JUMP + _EPS and
            self._clear(x, z, h + self.HEIGHT, f + self.HEIGHT)):
          yield (nx, nz, f), 2.0, 'jump'

  def _side(self, x: int, z: int, h: float, f: float) -> bool:
    """Whether a corner's side column is passable between h and f."""
    return any(abs(g - h) <= self.STEP + _EPS and
               abs(g - f) <= self.STEP + _EPS for g in self.floors(x, z))

  def _search(self, first: tuple) -> tuple:
    """Every node got to from 'first': its cost, and how it was got to."""
    cost, came = {first: 0.0}, {}
    queue = [(0.0, first)]
    while queue:
      spent, node = heapq.heappop(queue)
      if spent > cost[node]:
        continue
      for after, step, kind in self._moves(node):
        total = spent + step
        if total < cost.get(after, math.inf):
          cost[after] = total
          came[after] = (node, kind)
          heapq.heappush(queue, (total, after))
    return cost, came

  def _straighten(self, chain: list, kinds: list) -> list:
    """The chain's nodes to go to, straight on where the line is clear."""
    out, i = [], 0
    while i < len(chain) - 1:
      j = i + 1
      if kinds[i] == 'walk':
        while (j + 1 < len(chain) and kinds[j] == 'walk' and
               self._straight(chain[i], chain[j + 1])):
          j += 1
      out.append(chain[j])
      i = j
    return out

  def _straight(self, a: tuple, b: tuple) -> bool:
    """Whether a player walks straight from node a to node b, on floors."""
    ax, az, bx, bz = a[0] + 0.5, a[1] + 0.5, b[0] + 0.5, b[1] + 0.5
    length = math.hypot(bx - ax, bz - az)
    steps = max(1, int(math.ceil(length / 0.2)))
    side = (-(bz - az) / length * 0.3, (bx - ax) / length * 0.3)
    for k in range(steps + 1):
      t = k / steps
      px, pz = ax + (bx - ax) * t, az + (bz - az) * t
      for ox, oz in ((0.0, 0.0), side, (-side[0], -side[1])):
        x, z = math.floor(px + ox), math.floor(pz + oz)
        if not self.inside(x, z) or not any(
            abs(f - a[2]) <= self.STEP + _EPS and
            abs(f - b[2]) <= self.STEP + _EPS for f in self.floors(x, z)):
          return False
    return True

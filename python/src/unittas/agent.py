"""
Agent: a player and nothing more (SPEC.md 15.2), carrying out a
scenario's steps by a player's means alone: the keys, the look, and what
it perceives (player.perceive). Its brain is here; the probe only says
what is there and takes the inputs.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from worktoy.desc import Field
from worktoy.mcls import BaseObject

from .errors import TesttimeError
from .values import BlockPos, Vec3

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Callable, Optional, Union

  from .api import Game
  from .perception import Perception
  from .target import Target


def _place(pos: Any) -> str:
  """A position as a report line gives it."""
  if isinstance(pos, BlockPos):
    return '(%d, %d, %d)' % (pos.x, pos.y, pos.z)
  return '(%.2f, %.2f, %.2f)' % (pos.x, pos.y, pos.z)


def _met(target: Target) -> str:
  """What the crosshair met, as a report line names it."""
  if target.kind == 'block':
    return '%s at %s' % (target.id, _place(target.pos))
  if target.kind == 'entity':
    return '%s (entity %d)' % (target.type, target.entity)
  return 'nothing within reach'


def _turn(a: float, b: float) -> float:
  """How far the yaw b is from a, either way, in degrees."""
  return abs((b - a + 180.0) % 360.0 - 180.0)


class Agent(BaseObject):
  """
  The agent, in one game. Each step closes the loop on what it perceives:
  it looks, holds or lets go of keys, lets the game tick and perceives
  again, and it lets go of every key it held when the step ends. A step it
  can't complete raises TesttimeError, naming what it did and saw.

    agent = Agent(self.game)
    agent.walkTo(self.start.offset(6, 0, 4))
    agent.reach(lever)
    agent.lookAt(lever)
  """

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  NAMESPACE  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  #  Class Variables
  #  Where the agent sneaks, slow enough to stop where it means to: this
  #  near its goal. Each input takes a tick or two to hold (the probe runs
  #  a step at the end of the client's next tick, PROTOCOL.md 4), and a
  #  player coasts after letting go; sneaking keeps both short.
  CREEP = 1.0
  #  Stopped below this speed, in blocks a tick
  STOPPED = 0.003
  #  Nudged by one sneaking tap when stopped this near and not there
  NUDGE = 0.3
  #  The least margin walkTo takes: a tap moves about 0.065 blocks
  LEAST = 0.05
  #  Blocked when it gained less than 0.05 blocks in this many ticks
  #  pushing into something
  STUCK = 10
  #  How much nearer than its reach the agent goes, to use it surely
  REACH_MARGIN = 1.0

  #  Fallback Variables

  #  Private Variables
  #  The game the agent plays in
  __game__: Game = None
  #  The keys this agent holds down
  __held__: set = None

  #  Public Variables
  game = Field()

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  GETTERS  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  @game.GET
  def _getGame(self) -> Game:
    """The game the agent plays in."""
    return self.__game__

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  SETTERS  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  CONSTRUCTORS   # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  def __init__(self, game: Game) -> None:
    """The agent playing the client player of 'game'."""
    BaseObject.__init__(self)
    self.__game__ = game
    self.__held__ = set()

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  PARENT METHODS   # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  DOMAIN SPECIFIC  # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  def perceive(self, around: int = 2) -> Perception:
    """What the player perceives now."""
    return self.__game__.perceive(around)

  def letGo(self) -> None:
    """Every key this agent holds, let go."""
    for key in sorted(self.__held__):
      self.__game__.keyUp(key)
    self.__held__.clear()

  def walkTo(self, place: Union[Vec3, BlockPos], within: float = 0.25,
             ticks: Optional[int] = None) -> Perception:
    """
    Walks to 'place' on the level it stands on, and stops there: within
    'within' blocks across, and still. A BlockPos is its floor's middle.
    What it perceives there.

    Parameters
    ----------
    place : Vec3 or BlockPos
      Where to stand.
    within : float
      How near is there, across.
    ticks : int, optional
      The step's tick budget; 100 and 12 a block across, left out.

    Raises
    ------
    TesttimeError
      Something blocks the way, the place is on another level (terrain
      is SPEC.md 15.6 step 7's), or the tick budget is spent.
    """
    if isinstance(place, BlockPos):
      place = place.center()
    if not isinstance(place, Vec3):
      raise TypeError('walkTo goes to a Vec3 or a BlockPos, not %r' % (
        place,))
    if within < self.LEAST:
      infoSpec = """walkTo's margin is %r: a player's least step, one
      sneaking tap, is about 0.065 blocks, so the least it can be sure of
      is %r"""
      raise ValueError(' '.join((infoSpec % (within, self.LEAST)).split()))
    seen = self.perceive()
    rise = place.y - seen.pos.y
    if abs(rise) > 0.5:
      infoSpec = """%s is %.2f blocks %s the feet, at %s: walking climbs
      nothing yet (terrain is SPEC.md 15.6 step 7's)"""
      where = 'above' if rise > 0 else 'below'
      info = infoSpec % (_place(place), abs(rise), where, _place(seen.pos))
      raise TesttimeError('walkTo', seen, ' '.join(info.split()))

    def arrived(x: float, z: float) -> bool:
      return math.hypot(place.x - x, place.z - z) <= within

    return self._walk('walkTo', place, arrived, ticks, seen)

  def reach(self, pos: BlockPos, ticks: Optional[int] = None) -> Perception:
    """
    Walks towards the block at 'pos' until it is within reach, by the
    agent's margin, and stops. What it perceives there.

    Raises
    ------
    TesttimeError
      The block is out of reach from this level, something blocks the
      way, or the tick budget is spent.
    """
    if not isinstance(pos, BlockPos):
      raise TypeError('reach takes a BlockPos, not %r' % (pos,))
    seen = self.perceive()
    centre = pos.center().above(0.5)
    limit = seen.blockReach - self.REACH_MARGIN
    eyeY = seen.eye.y
    if abs(centre.y - eyeY) > limit:
      infoSpec = """the block at %s is %.2f blocks %s the eye: out of
      reach from this level"""
      where = 'above' if centre.y > eyeY else 'below'
      info = infoSpec % (_place(pos), abs(centre.y - eyeY), where)
      raise TesttimeError('reach', seen, ' '.join(info.split()))

    def arrived(x: float, z: float) -> bool:
      far = math.dist((x, eyeY, z), (centre.x, centre.y, centre.z))
      return far <= limit

    goal = Vec3(centre.x, seen.pos.y, centre.z)
    return self._walk('reach', goal, arrived, ticks, seen)

  def lookAt(self, pos: BlockPos) -> Perception:
    """
    Turns until the crosshair targets the block at 'pos': at its middle,
    or else the middle of a face turned towards the eye. What it
    perceives then.

    Raises
    ------
    TesttimeError
      The block is out of reach, or something else meets the crosshair
      wherever it looks at it from here.
    """
    if not isinstance(pos, BlockPos):
      raise TypeError('lookAt takes a BlockPos, not %r' % (pos,))
    seen = self.perceive()
    eye = seen.eye
    centre = pos.center().above(0.5)
    far = math.dist((eye.x, eye.y, eye.z), (centre.x, centre.y, centre.z))
    if far - 0.5 > seen.blockReach:
      infoSpec = """the block at %s is out of reach: %.2f blocks from the
      eye at %s, and the reach is %.1f"""
      info = infoSpec % (_place(pos), far, _place(eye), seen.blockReach)
      raise TesttimeError('lookAt', seen, ' '.join(info.split()))
    met = []
    for point in [centre] + self._faces(pos, eye):
      across = math.hypot(point.x - eye.x, point.z - eye.z)
      yaw = math.degrees(math.atan2(-(point.x - eye.x), point.z - eye.z))
      pitch = math.degrees(math.atan2(-(point.y - eye.y), across))
      self.__game__.look(yaw, pitch)
      seen = self.perceive()
      if seen.target.kind == 'block' and seen.target.pos == pos:
        return seen
      if _met(seen.target) not in met:
        met.append(_met(seen.target))
    info = 'the block at %s isn\'t targeted from %s: the crosshair meets %s'
    raise TesttimeError('lookAt', seen, info % (_place(pos), _place(eye),
                                                ', '.join(met)))

  # ---------------------------------------------------------------- the loop

  def _hold(self, key: str, down: bool) -> None:
    """The key held down or let go, unless it is so already."""
    if down and key not in self.__held__:
      self.__game__.keyDown(key)
      self.__held__.add(key)
    elif not down and key in self.__held__:
      self.__game__.keyUp(key)
      self.__held__.discard(key)

  def _face(self, seen: Perception, goal: Vec3) -> None:
    """Turns towards the goal if it isn't, else lets a tick pass."""
    yaw = math.degrees(math.atan2(-(goal.x - seen.pos.x),
                                  goal.z - seen.pos.z))
    if _turn(seen.look.yaw, yaw) > 1.0:
      self.__game__.look(yaw, seen.look.pitch)
    else:
      self.__game__.ticks(1)

  def _walk(self, step: str, goal: Vec3,
            arrived: Callable[[float, float], bool], ticks: Optional[int],
            seen: Perception) -> Perception:
    """
    Walks towards the goal until 'arrived' holds where it stands, still.
    Far off it walks; near, it sneaks; there, or a little short, it lets
    go, and once stopped short, it nudges.
    """
    across = math.hypot(goal.x - seen.pos.x, goal.z - seen.pos.z)
    if ticks is None:
      ticks = 100 + int(math.ceil(12 * across))
    if ticks <= 0:
      raise ValueError('a tick budget is above 0, not %r' % ticks)
    first = seen.tick
    pushed = []
    try:
      while True:
        short = math.hypot(goal.x - seen.pos.x, goal.z - seen.pos.z)
        speed = math.hypot(seen.motion.x, seen.motion.z)
        if speed < self.STOPPED and arrived(seen.pos.x, seen.pos.z):
          return seen
        if seen.tick - first > ticks:
          infoSpec = """the tick budget (%d) is spent, %.2f blocks short,
          at %s"""
          info = infoSpec % (ticks, short, _place(seen.pos))
          raise TesttimeError(step, seen, ' '.join(info.split()))
        if arrived(seen.pos.x, seen.pos.z) or short < self.NUDGE:
          #  there, or a little short: let it stop; then, if short, one
          #  sneaking tap towards it
          pushed.clear()
          self._hold('key.forward', False)
          if speed < self.STOPPED:
            self._hold('key.sneak', True)
            self._face(seen, goal)
            self._hold('key.forward', True)
            self._hold('key.forward', False)
          else:
            self.__game__.ticks(1)
        else:
          pushed.append((seen.tick, short))
          self._blocked(step, seen, goal, short, pushed, first)
          self._hold('key.sneak', short < self.CREEP)
          self._hold('key.forward', True)
          self._face(seen, goal)
        seen = self.perceive()
    finally:
      self.letGo()

  def _blocked(self, step: str, seen: Perception, goal: Vec3, short: float,
               pushed: list, first: int) -> None:
    """TesttimeError when pushing on has gained nothing for a while."""
    if not seen.collidedHorizontally:
      return
    before = [was for tick, was in pushed if seen.tick - tick >= self.STUCK]
    if not before or before[-1] - short >= 0.05:
      return
    names = ['%s at %s' % (near.id, _place(near.pos)) for near in
             self._blockers(seen, goal)] or ['something it can\'t see']
    infoSpec = """blocked by %s after %d ticks, %.2f blocks short, at %s"""
    info = infoSpec % (', '.join(names), seen.tick - first, short,
                       _place(seen.pos))
    raise TesttimeError(step, seen, ' '.join(info.split()))

  @staticmethod
  def _blockers(seen: Perception, goal: Vec3) -> list:
    """The blocks against the player's box on the goal's side."""
    box, grow = seen.box, 0.1
    gx, gz = goal.x - seen.pos.x, goal.z - seen.pos.z
    found = []
    for near in seen.blocks:
      for each in near.boxes:
        if each.maxY <= box.minY + 1e-6 or each.minY >= box.maxY:
          continue
        if each.minX > box.maxX + grow or each.maxX < box.minX - grow:
          continue
        if each.minZ > box.maxZ + grow or each.maxZ < box.minZ - grow:
          continue
        cx = (each.minX + each.maxX) / 2 - seen.pos.x
        cz = (each.minZ + each.maxZ) / 2 - seen.pos.z
        if cx * gx + cz * gz > 0:
          found.append(near)
          break
    return found

  @staticmethod
  def _faces(pos: BlockPos, eye: Vec3) -> list:
    """The middles of the block's faces turned towards the eye, just in."""
    inset = 0.05
    centre = pos.center().above(0.5)
    faces = []
    for axis, low, high in (('x', pos.x, pos.x + 1), ('y', pos.y, pos.y + 1),
                            ('z', pos.z, pos.z + 1)):
      at = getattr(eye, axis)
      if at < low:
        side = low + inset
      elif at > high:
        side = high - inset
      else:
        continue
      faces.append(Vec3(**dict(centre.asDict(), **{axis: side})))
    return faces

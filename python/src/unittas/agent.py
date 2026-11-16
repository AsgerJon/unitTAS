"""
Agent: a player and nothing more (SPEC.md 15.2), carrying out a
scenario's steps by a player's means alone: the keys, the look, and what
it perceives (player.perceive). Its brain is here; the probe only says
what is there and takes the inputs.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import json
import math
import os
import tempfile
from typing import TYPE_CHECKING

from worktoy.desc import Field
from worktoy.mcls import BaseObject

from .errors import Missing, TesttimeError
from .likeness import likeness
from .terrain import Terrain
from .values import Block, BlockPos, Item, Vec3

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Callable, Optional, Union

  from .api import Game
  from .blockview import BlockView
  from .container import Container
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


def _note(text: str) -> None:
  """A line under the running test's own, when there is a run."""
  from .run import Run
  if Run.current is not None:
    Run.current.note(text)


def _shown(path: str) -> str:
  """A file as a report line names it: from the run's results, if in them."""
  from .run import Run
  results = getattr(Run.current, 'results', '')
  if results and path.startswith(os.path.join(results, '')):
    return os.path.relpath(path, results)
  return path


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
  #  How walkTo looks around for its way: blocks across, below, above
  #  (further up or down to a place's level); and how many looks it takes
  #  at most to get to a place further off
  LOOK = (8, 3, 3)
  LOOKS = 12
  #  In the air a player keeps 0.91 of its motion a tick: what it moves
  #  yet, by its motion; and how far from a place it lets that drift
  #  take it on, coming down a ladder, before it pushes against it
  DRIFT = 1.0 / (1.0 - 0.91)
  HOVER = 0.1
  #  Jump pressed again within 7 ticks makes a creative player fly (its
  #  double tap): the agent presses it no sooner than this
  JUMP_AGAIN = 9
  #  Blocked when it gained less than 0.05 blocks in this many ticks
  #  pushing into something; swimming, two of its bobs at the water's top
  #  (a bank is got onto rising through a band 0.2 high, once a bob)
  STUCK = 10
  STUCK_SWIMMING = 40
  #  How much nearer than its reach the agent goes, to use it surely
  REACH_MARGIN = 1.0
  #  How far identify's best look must beat the next to be the answer,
  #  and how alike it must be at least
  MARGIN = 0.1
  LIKENESS = 0.5

  #  Fallback Variables

  #  Private Variables
  #  The game the agent plays in
  __game__: Game = None
  #  The keys this agent holds down
  __held__: set = None
  #  Where its views' frames are kept, and how many it has taken
  __frames__: str = None
  __taken__: int = 0
  #  The game's textures it has asked for, by icon: (size, pixels) or None
  __textures__: dict = None
  #  The tick it last perceived, and the one it last pressed jump at
  __now__: int = 0
  __jumped__: int = None

  #  Public Variables
  game = Field()
  frames = Field()

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  GETTERS  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  @game.GET
  def _getGame(self) -> Game:
    """The game the agent plays in."""
    return self.__game__

  @frames.GET
  def _getFrames(self) -> str:
    """The folder its views' frames are kept in."""
    return self.__frames__

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  SETTERS  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  CONSTRUCTORS   # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  def __init__(self, game: Game, frames: str = '') -> None:
    """
    The agent playing the client player of 'game', keeping its views'
    frames in 'frames' (an absolute folder; unittas-frames in the system's
    temporary folder, left out).
    """
    BaseObject.__init__(self)
    self.__game__ = game
    self.__held__ = set()
    if not frames:
      frames = os.path.join(tempfile.gettempdir(), 'unittas-frames')
    if not os.path.isabs(frames):
      raise ValueError('an agent\'s frames folder is absolute, not %r' % (
        frames,))
    self.__frames__ = frames
    self.__textures__ = {}

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  PARENT METHODS   # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  DOMAIN SPECIFIC  # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  def perceive(self, around: int = 2, below: int = 1,
               above: int = 1) -> Perception:
    """What the player perceives now."""
    seen = self.__game__.perceive(around, below, above)
    self.__now__ = seen.tick
    return seen

  def wait(self, ticks: int) -> None:
    """Waits 'ticks' of the game's ticks, doing nothing."""
    self.__game__.ticks(ticks)

  def letGo(self) -> None:
    """Every key this agent holds, let go."""
    for key in sorted(self.__held__):
      self.__game__.keyUp(key)
    self.__held__.clear()

  def walkTo(self, place: Union[Vec3, BlockPos], within: float = 0.25,
             ticks: Optional[int] = None) -> Perception:
    """
    Walks to 'place' and stops there: within 'within' blocks across, and
    still. A BlockPos is its floor's middle. Its way goes around what is
    in it, up steps and slabs, jumps up a block, drops down three, opens
    doors, and goes up and down ladders (SPEC.md 15.6 step 7). What it
    perceives there.

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
      There is no way to the place in what the agent sees, something it
      didn't see blocks the way, or the tick budget is spent.
    """
    if isinstance(place, BlockPos):
      place = place.center()
    if not isinstance(place, Vec3):
      raise TypeError('walkTo goes to a Vec3 or a BlockPos, not %r' % (
        place,))
    return self._walkTo('walkTo', place, within, ticks)

  def _walkTo(self, step: str, place: Vec3, within: float,
              ticks: Optional[int]) -> Perception:
    """walkTo, as the step named."""
    if within < self.LEAST:
      infoSpec = """walkTo's margin is %r: a player's least step, one
      sneaking tap, is about 0.065 blocks, so the least it can be sure of
      is %r"""
      raise ValueError(' '.join((infoSpec % (within, self.LEAST)).split()))
    if ticks is not None and ticks <= 0:
      raise ValueError('a tick budget is above 0, not %r' % ticks)

    def arrived(x: float, z: float) -> bool:
      return math.hypot(place.x - x, place.z - z) <= within

    seen = self.perceive(*self.LOOK)
    look = self._look(seen.pos, place)
    if look != self.LOOK:
      seen = self.perceive(*look)
    first = seen.tick
    if ticks is None:
      ticks = 100 + int(math.ceil(12 * math.hypot(place.x - seen.pos.x,
                                                 place.z - seen.pos.z) +
                                  30 * abs(place.y - seen.pos.y)))
    for _ in range(self.LOOKS):
      terrain = Terrain(seen, *look)
      path, whole = terrain.path(seen.pos, place)
      if path is None:
        infoSpec = """no way to %s from %s in what the agent sees (%d blocks
        around, %d below, %d above)"""
        info = infoSpec % ((_place(place), _place(seen.pos)) + look)
        raise TesttimeError(step, seen, ' '.join(info.split()))
      try:
        before = seen.pos
        for at, point in enumerate(path):
          #  the place on its level is the stop's, after
          if (whole and at == len(path) - 1 and
              abs(point.y - seen.pos.y) <= Terrain.STEP):
            break
          column = (math.floor(point.x), math.floor(point.z))
          if terrain.doors(*column):
            after = path[at + 1] if at + 1 < len(path) else place
            self._throughDoor(step, terrain.doors(*column)[0].pos, point,
                              after)
          seen = self._toward(step, terrain, before, point, first, ticks,
                              seen)
          before = point
      finally:
        self.letGo()
      if whole:
        left = ticks - (seen.tick - first)
        return self._walk(step, place, arrived, max(1, left), seen)
      look = self._look(seen.pos, place)
      seen = self.perceive(*look)
    infoSpec = """%s is further than %d looks around took the agent, at
    %s"""
    info = infoSpec % (_place(place), self.LOOKS, _place(seen.pos))
    raise TesttimeError(step, seen, ' '.join(info.split()))

  def _look(self, pos: Vec3, place: Vec3) -> tuple:
    """
    How far walkTo looks from 'pos' for its way to 'place': LOOK's, and
    up or down to the place's floor and the room over it (8 at most).
    """
    around, below, above = self.LOOK
    feet = math.floor(pos.y + 1e-6)
    below = min(8, max(below, feet - math.floor(place.y) + 1))
    above = min(8, max(above, math.ceil(place.y) - feet))
    return around, below, above

  def _toward(self, step: str, terrain: Terrain, before: Vec3,
              point: Vec3, first: int, ticks: int,
              seen: Perception) -> Perception:
    """
    On to the waypoint 'point' from 'before', the one passed last: into,
    across or out of water, swimming; up a ladder its feet are in, down
    a ladder in the point's column; else walking (jumping, dropping) on.
    """
    here = (math.floor(before.x), math.floor(before.z))
    there = (math.floor(point.x), math.floor(point.z))
    feet = seen.pos.y
    wet = terrain.wet(there[0], there[1], point.y)
    if wet or seen.inWater:
      return self._swim(step, point, wet, first, ticks)
    if point.y > feet + Terrain.STEP and terrain.climbable(
        here[0], here[1], math.floor(feet + 1e-6)):
      return self._upLadder(step, before, point, first, ticks)
    if point.y < feet - Terrain.STEP and terrain.climbable(
        there[0], there[1], math.ceil(feet - 1e-6) - 1):
      return self._downLadder(step, terrain, before, point, first, ticks)
    return self._pass(step, point, first, ticks)

  def _swim(self, step: str, point: Vec3, wet: bool, first: int,
            ticks: int) -> Perception:
    """
    Swims to the waypoint 'point': on the water ('wet'), on to the next
    once in the water over it; else onto the bank there, on to the next
    once on it. Jump is held in the water, and below the point's level
    (a player bobbing at the top leaves the water a tick at a time, and
    jump let go and pressed again within 7 ticks makes a creative player
    fly): in water it lifts a player, its head out, and pushing into a
    bank with nothing 0.6 over its feet lifts it out (1.7.10: 0.3 up).
    Rising counts as getting on.
    """
    pushed = []
    seen = self.perceive()
    while True:
      across = math.hypot(point.x - seen.pos.x, point.z - seen.pos.z)
      if across < 0.45 and (seen.inWater if wet else (
          seen.onGround and not seen.inWater and
          abs(point.y - seen.pos.y) < 0.3)):
        return seen
      self._spent(step, seen, point, first, ticks)
      left = across + max(0.0, point.y - 0.6 - seen.pos.y)
      pushed.append((seen.tick, left))
      self._blocked(step, seen, point, left, pushed, first,
                    self.STUCK_SWIMMING)
      self._hold('key.sneak', False)
      self._hold('key.jump', seen.inWater or
                 seen.pos.y < point.y - 0.05)
      self._hold('key.forward', True)
      self._face(seen, point)
      seen = self.perceive()

  def _upLadder(self, step: str, foot: Vec3, point: Vec3, first: int,
                ticks: int) -> Perception:
    """
    Up a ladder to the ledge 'point', as a player climbs: still at the
    middle of its foot's block first (a player drifting across as it
    climbs slips off), then pushing towards the ledge (1.7.10 lifts a
    player on a ladder pushing into anything).
    """
    middle = Vec3(math.floor(foot.x) + 0.5, foot.y,
                  math.floor(foot.z) + 0.5)
    seen = self.perceive()

    def lined(x: float, z: float) -> bool:
      return math.hypot(middle.x - x, middle.z - z) <= 0.15

    self._walk(step, middle, lined, max(1, ticks - (seen.tick - first)),
               seen)
    return self._pass(step, point, first, ticks)

  def _downLadder(self, step: str, terrain: Terrain, top: Vec3,
                  point: Vec3, first: int, ticks: int) -> Perception:
    """
    Down a ladder to 'point', as a player goes: still at the middle of
    the ledge 'top' beside it; sneaking straight towards it until the
    game holds it at the edge; still, then one step off; then held over
    the room the ladder leaves in its column, against its drift, as it
    slides down. In the air off the ladder beside it: TesttimeError, it
    slipped off.
    """
    middle = Vec3(math.floor(top.x) + 0.5, top.y, math.floor(top.z) + 0.5)
    column = (math.floor(point.x), math.floor(point.z))
    #  a point far off straight on: its look doesn't wander near the edge
    ahead = Vec3(middle.x + 100.0 * (column[0] + 0.5 - middle.x), top.y,
                 middle.z + 100.0 * (column[1] + 0.5 - middle.z))
    seen = self.perceive()

    def lined(x: float, z: float) -> bool:
      return math.hypot(middle.x - x, middle.z - z) <= 0.15

    seen = self._walk(step, middle, lined,
                      max(1, ticks - (seen.tick - first)), seen)
    try:
      #  towards it sneaking: the game holds a sneaking player at an edge
      still = 0
      self._hold('key.sneak', True)
      while seen.onGround and still < 2:
        self._spent(step, seen, point, first, ticks)
        self._hold('key.forward', True)
        self._face(seen, ahead)
        was, seen = seen, self.perceive()
        moved = math.hypot(seen.pos.x - was.pos.x, seen.pos.z - was.pos.z)
        gone = math.hypot(seen.pos.x - middle.x, seen.pos.z - middle.z)
        still = still + 1 if moved < 0.002 and gone > 0.2 else 0
      if seen.onGround:
        #  held there: still, then a step off it, not sneaking
        self._hold('key.forward', False)
        while math.hypot(seen.motion.x, seen.motion.z) >= self.STOPPED:
          self._spent(step, seen, point, first, ticks)
          self.__game__.ticks(1)
          seen = self.perceive()
        self._hold('key.sneak', False)
        self._hold('key.forward', True)
        self._hold('key.forward', False)
        seen = self.perceive()
      self._hold('key.sneak', False)
      room = self._room(seen, column, point.y)
      while not (seen.onGround and abs(point.y - seen.pos.y) < 0.3):
        self._spent(step, seen, point, first, ticks)
        feet = math.floor(seen.pos.y + 1e-6)
        if not (seen.onLadder or seen.onGround) and terrain.climbable(
            column[0], column[1], feet):
          infoSpec = """slipped off the ladder at %s: in the air at %s"""
          info = infoSpec % (_place(BlockPos(column[0], feet, column[1])),
                             _place(seen.pos))
          raise TesttimeError(step, seen, info)
        self._steer(seen, room)
        seen = self.perceive()
    finally:
      self.letGo()
    return seen

  @staticmethod
  def _room(seen: Perception, column: tuple, y: float) -> Vec3:
    """
    The middle of where a player's middle is in the column, its box
    clear of the boxes of the ladder there (along an edge each), at y.
    """
    x, z = column
    low, high = [float(x), float(z)], [x + 1.0, z + 1.0]
    for near in seen.blocks:
      if not near.climbable or (near.pos.x, near.pos.z) != column:
        continue
      for box in near.boxes:
        for axis, (lo, hi) in enumerate(((box.minX, box.maxX),
                                         (box.minZ, box.maxZ))):
          middle = column[axis] + 0.5
          if lo > middle:
            high[axis] = min(high[axis], lo - 0.3)
          elif hi < middle:
            low[axis] = max(low[axis], hi + 0.3)
    return Vec3((low[0] + high[0]) / 2, y, (low[1] + high[1]) / 2)

  def _steer(self, seen: Perception, point: Vec3) -> None:
    """
    Holds the keys that bring the player to rest over 'point' in the air,
    by where its drift would take it: towards it, or against the drift,
    along its look and across it. A tick passes when nothing changes.
    """
    ex = point.x - (seen.pos.x + seen.motion.x * self.DRIFT)
    ez = point.z - (seen.pos.z + seen.motion.z * self.DRIFT)
    yaw = math.radians(seen.look.yaw)
    along = -math.sin(yaw) * ex + math.cos(yaw) * ez
    across = math.cos(yaw) * ex + math.sin(yaw) * ez
    keys = {'key.forward': along > self.HOVER,
            'key.back': along < -self.HOVER,
            'key.left': across > self.HOVER,
            'key.right': across < -self.HOVER}
    if all(down == (key in self.__held__) for key, down in keys.items()):
      self.__game__.ticks(1)
      return
    for key, down in sorted(keys.items()):
      self._hold(key, down)

  def _spent(self, step: str, seen: Perception, point: Vec3, first: int,
             ticks: int) -> None:
    """TesttimeError when the walk's tick budget is spent."""
    if seen.tick - first <= ticks:
      return
    across = math.hypot(point.x - seen.pos.x, point.z - seen.pos.z)
    infoSpec = """the tick budget (%d) is spent on the way, at %s, %.2f
    blocks from the waypoint %s"""
    info = infoSpec % (ticks, _place(seen.pos), across, _place(point))
    raise TesttimeError(step, seen, ' '.join(info.split()))

  def _throughDoor(self, step: str, door: BlockPos, point: Vec3,
                   after: Vec3) -> None:
    """
    A door on the way: used when its boxes cross the way through its
    column (to 'point', then 'after'), as a player opens one; looked at
    again after.
    """
    seen = self.perceive()
    if not self._crosses(seen, door, (point, after)):
      return
    self._use(step, door, None)
    seen = self.perceive()
    if self._crosses(seen, door, (point, after)):
      infoSpec = """the door at %s doesn't let the agent through, open or
      shut"""
      raise TesttimeError(step, seen, ' '.join((infoSpec % (
        _place(door),)).split()))

  @staticmethod
  def _crosses(seen: Perception, door: BlockPos, points: tuple) -> bool:
    """Whether the door's boxes meet the player's box on its way."""
    boxes = [box for near in seen.blocks if near.opens and
             (near.pos.x, near.pos.z) == (door.x, door.z)
             for box in near.boxes]
    feet, half = seen.pos.y, 0.3
    here = (seen.pos.x, seen.pos.z)
    for there in points:
      length = math.hypot(there.x - here[0], there.z - here[1])
      steps = max(1, int(math.ceil(length / 0.1)))
      for k in range(steps + 1):
        x = here[0] + (there.x - here[0]) * k / steps
        z = here[1] + (there.z - here[1]) * k / steps
        for box in boxes:
          if (box.minX < x + half and x - half < box.maxX and
              box.minZ < z + half and z - half < box.maxZ and
              box.minY < feet + 1.8 and feet < box.maxY):
            return True
      here = (there.x, there.z)
    return False

  def _pass(self, step: str, point: Vec3, first: int,
            ticks: int) -> Perception:
    """
    Walks to a waypoint without stopping there: on to the next once over
    it, on its level and on the ground. Holds jump while the waypoint is
    higher than a step, near it; on a ladder it pushes on instead, and
    climbs.
    """
    pushed = []
    seen = self.perceive()
    while True:
      across = math.hypot(point.x - seen.pos.x, point.z - seen.pos.z)
      rise = point.y - seen.pos.y
      if across < 0.45 and abs(rise) < 0.3 and seen.onGround:
        return seen
      self._spent(step, seen, point, first, ticks)
      #  what is left of the way: climbing gains it too
      left = across + max(0.0, rise)
      pushed.append((seen.tick, left))
      jump = rise > Terrain.STEP and not seen.onLadder
      if not jump:
        self._blocked(step, seen, point, left, pushed, first)
      self._hold('key.sneak', False)
      self._hold('key.jump', jump and across < 1.6)
      self._hold('key.forward', True)
      self._face(seen, point)
      seen = self.perceive()

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
    return self._reach('reach', pos, ticks)

  def _reach(self, step: str, pos: BlockPos,
             ticks: Optional[int]) -> Perception:
    """reach, as the step named."""
    seen = self.perceive()
    centre = pos.center().above(0.5)
    limit = seen.blockReach - self.REACH_MARGIN
    eyeY = seen.eye.y
    if abs(centre.y - eyeY) > limit:
      infoSpec = """the block at %s is %.2f blocks %s the eye: out of
      reach from this level"""
      where = 'above' if centre.y > eyeY else 'below'
      info = infoSpec % (_place(pos), abs(centre.y - eyeY), where)
      raise TesttimeError(step, seen, ' '.join(info.split()))

    def arrived(x: float, z: float) -> bool:
      far = math.dist((x, eyeY, z), (centre.x, centre.y, centre.z))
      return far <= limit

    goal = Vec3(centre.x, seen.pos.y, centre.z)
    return self._walk(step, goal, arrived, ticks, seen)

  def lookAt(self, pos: BlockPos) -> Perception:
    """
    Turns until the crosshair targets the block at 'pos': at its middle,
    or else the middle of a face turned towards the eye, or else low in
    it (a small block on its floor). What it perceives then.

    Raises
    ------
    TesttimeError
      The block is out of reach, or something else meets the crosshair
      wherever it looks at it from here.
    """
    if not isinstance(pos, BlockPos):
      raise TypeError('lookAt takes a BlockPos, not %r' % (pos,))
    return self._lookAt('lookAt', pos)

  def _lookAt(self, step: str, pos: BlockPos) -> Perception:
    """lookAt, as the step named."""
    seen = self.perceive()
    eye = seen.eye
    centre = pos.center().above(0.5)
    far = math.dist((eye.x, eye.y, eye.z), (centre.x, centre.y, centre.z))
    if far - 0.5 > seen.blockReach:
      infoSpec = """the block at %s is out of reach: %.2f blocks from the
      eye at %s, and the reach is %.1f"""
      info = infoSpec % (_place(pos), far, _place(eye), seen.blockReach)
      raise TesttimeError(step, seen, ' '.join(info.split()))
    met = []
    for point in [centre] + self._faces(pos, eye) + self._lows(pos):
      seen = self._aim(point, eye)
      if seen.target.kind == 'block' and seen.target.pos == pos:
        return seen
      if _met(seen.target) not in met:
        met.append(_met(seen.target))
    info = 'the block at %s isn\'t targeted from %s: the crosshair meets %s'
    raise TesttimeError(step, seen, info % (_place(pos), _place(eye),
                                            ', '.join(met)))

  # ------------------------------------------------------------------ verbs

  def use(self, pos: BlockPos, ticks: Optional[int] = None) -> Perception:
    """
    Uses the block at 'pos' (a right click: a lever flips, a door opens,
    a chest's screen opens), as a player does: into reach, looking at it,
    one click of the use key. What it perceives after.

    Raises
    ------
    TesttimeError
      As reach and lookAt do: no way into reach, the block not targeted.
    """
    return self._use('use', pos, ticks)

  def _use(self, step: str, pos: BlockPos,
           ticks: Optional[int]) -> Perception:
    """use, as the step named."""
    self._ready(step, pos, ticks)
    self.__game__.tap('key.use')
    return self.perceive()

  def breakBlock(self, pos: BlockPos,
                 ticks: Optional[int] = None) -> Perception:
    """
    Breaks the block at 'pos', as a player does: into reach, looking at
    it, the attack key held until the crosshair no longer meets that
    block, and let go at once (creative breaks the next block 5 ticks
    on). 'ticks' is the mining's budget: 600, left out. What it
    perceives after.

    Raises
    ------
    TesttimeError
      As reach and lookAt do, or the block is still there when the
      budget is spent.
    """
    budget = 600 if ticks is None else ticks
    if budget <= 0:
      raise ValueError('a tick budget is above 0, not %r' % budget)
    seen = self._ready('breakBlock', pos, None)
    block = seen.target.id
    first = seen.tick
    try:
      self._hold('key.attack', True)
      while True:
        seen = self.perceive()
        aim = seen.target
        if not (aim.kind == 'block' and aim.pos == pos and aim.id == block):
          return seen
        if seen.tick - first > budget:
          infoSpec = """%s at %s is still there after %d ticks of mining
          (the budget)"""
          info = infoSpec % (block, _place(pos), seen.tick - first)
          raise TesttimeError('breakBlock', seen, ' '.join(info.split()))
    finally:
      self.letGo()

  def place(self, pos: BlockPos, item: Any,
            ticks: Optional[int] = None) -> Perception:
    """
    Places 'item' (an MCItems member, in the hotbar) at 'pos', as a player
    does: its slot selected by its hotbar key, a step aside if the agent
    stands there, into reach, and a click on a face of a block beside the
    place, the one below first. What it perceives after: the crosshair on
    the new block.

    Raises
    ------
    TesttimeError
      The item isn't in the hotbar; something is at the place already; no
      block beside it shows the agent a face to click; the click placed
      nothing.
    """
    if not isinstance(pos, BlockPos):
      raise TypeError('place takes a BlockPos, not %r' % (pos,))
    self._select('place', item)
    seen = self.perceive()
    if self._standsIn(seen, pos):
      self._stepAside('place', seen, pos)
    seen = self._reach('place', pos, ticks)
    eye = seen.eye
    there = self._aim(pos.center().above(0.5), eye)
    if there.target.kind == 'block' and there.target.pos == pos:
      info = '%s is there already, at %s' % (there.target.id, _place(pos))
      raise TesttimeError('place', there, info)
    for support, face in self._supports(pos):
      if not self._shows(support, face, eye):
        continue
      looked = self._aim(self._faceMiddle(support, face), eye)
      aim = looked.target
      if not (aim.kind == 'block' and aim.pos == support and
              aim.face == face):
        continue
      self.__game__.tap('key.use')
      after = self.perceive()
      if after.target.kind == 'block' and after.target.pos == pos:
        return after
      infoSpec = """clicking the %s face of %s at %s placed nothing at %s;
      the crosshair meets %s"""
      info = infoSpec % (face, aim.id, _place(support), _place(pos),
                         _met(after.target))
      raise TesttimeError('place', after, ' '.join(info.split()))
    infoSpec = """nothing to place it against at %s: no block beside it
    shows a face to click from %s"""
    info = infoSpec % (_place(pos), _place(eye))
    raise TesttimeError('place', there, ' '.join(info.split()))

  # ------------------------------------------------------------- observing

  def examine(self, pos: BlockPos, side: Optional[str] = None) -> BlockView:
    """
    Looks at the block at 'pos' and sees it (SPEC.md 15.4): into reach
    looking at it, or, with 'side' (north, south, east or west), standing
    that way from it and looking at that face; then the frame the game
    draws, and the block's pixels on it, by the game's ray until parallax
    comes. The view is noted on the test's report line as observed. What
    the picture means is the test's computation on it.

    Raises
    ------
    TesttimeError
      As reach and lookAt do; the face asked for isn't targeted; nothing
      of the block is in the view.
    ValueError
      A side above or below: seeing a block from there needs climbing
      (SPEC.md 15.6 step 7).
    """
    if not isinstance(pos, BlockPos):
      raise TypeError('examine takes a BlockPos, not %r' % (pos,))
    if side is None:
      seen = self._ready('examine', pos, None)
    else:
      seen = self._fromSide(pos, side)
    os.makedirs(self.__frames__, exist_ok=True)
    self.__taken__ += 1
    name = 'examine-%d-%d-%d-%d.png' % (pos.x, pos.y, pos.z, self.__taken__)
    view = self.__game__.view(pos, os.path.join(self.__frames__, name))
    #  the view's camera and mask beside its frame, for review
    with open(view.file[:-4] + '.json', 'w', encoding='utf-8') as file:
      json.dump(view.answer, file)
    if not view.count:
      infoSpec = """nothing of the block at %s is in the view from %s
      (frame %s)"""
      info = infoSpec % (_place(pos), _place(seen.eye), view.file)
      raise TesttimeError('examine', seen, ' '.join(info.split()))
    faces = ', '.join('%s %d' % (face, count)
                      for face, count in sorted(view.faces.items()))
    infoSpec = """observed (pixels by the game's ray): the block at %s from
    %s, %d pixels (%s), frame %s"""
    _note(' '.join((infoSpec % (_place(pos), _place(view.eye), view.count,
                                faces, _shown(view.file))).split()))
    return view

  def identify(self, pos: BlockPos, among: Optional[Any] = None) -> Any:
    """
    Says what the block at 'pos' is from its looks alone (SPEC.md 15.4):
    views from each side the agent can see it from, each face squared up
    and compared with each candidate's faces as the running game draws
    them, from the resource pack it has loaded (block.faces, texture.get;
    every variant that drops as the candidate does, so a furnace's
    facings count). The candidates are the mcdex blocks 'among' names, or
    every full cube the game's version has. The best look must beat the
    next by MARGIN. Air, which shows nothing, is known by touch: the agent
    walks into its place. The one mcdex member it is.

    Raises
    ------
    TesttimeError
      No side shows the block and it can't be touched; no look beats the
      next by MARGIN (the scores said); two candidates look the same.
    NotImplementedError
      A candidate named isn't drawn as a full cube: identify knows full
      cubes so far.
    Missing
      A candidate named isn't in the game's version.
    """
    if not isinstance(pos, BlockPos):
      raise TypeError('identify takes a BlockPos, not %r' % (pos,))
    views, why = [], []
    for side in ('north', 'east', 'south', 'west'):
      try:
        views.append(self.examine(pos, side))
      except TesttimeError as error:
        why.append(str(error))
    if not views:
      return self._byTouch(pos, why)
    candidates = self._candidates(pos, among)
    self._fetch(icon for _, look in candidates
                for variant in look['variants']
                for icon in variant['faces'].values())
    squares = {}
    scored = []
    for member, look in candidates:
      best, seen = None, None
      for variant in look['variants']:
        score = self._likeness(views, variant['faces'], look['tint'],
                               squares)
        if score is not None and (best is None or score > best):
          best, seen = score, variant['faces']
      if best is not None:
        scored.append((best, member, self._signature(seen, look['tint'])))
    return self._decide(pos, scored, len(views))

  def _candidates(self, pos: BlockPos, among: Optional[Any]) -> list:
    """(member, look) for each candidate the game draws as a full cube."""
    from mcdex import MCBlocks

    from .errors import NoMcdexData
    from .things import blockOf
    game = self.__game__
    named = among is not None
    members, blocks = [], []
    for member in (list(among) if named else list(MCBlocks)):
      try:
        block, _ = blockOf(member, game.version, game.declared())
      except (Missing, NoMcdexData):
        if named:
          raise
        continue
      members.append(member)
      blocks.append(block)
    out = []
    for member, block, look in zip(members, blocks,
                                   game.blockFaces(blocks, pos)):
      label = '%s.%s' % (type(member).__name__, member.name)
      if 'error' in look:
        if named:
          raise TesttimeError('identify', self.perceive(), '%s: %s' % (
            label, look['error']))
        continue
      if not look['cube']:
        if named:
          raise NotImplementedError(
            "%s isn't drawn as a full cube: identify knows full cubes so "
            "far (SPEC.md 15.4)" % label)
        continue
      #  the member's variants: the metas mcdex reads back as it (a
      #  furnace's facings; not wool's other colours)
      variants = [variant for variant in look['variants']
                  if self._isIt(member, block.id, variant['metas'])]
      if variants:
        out.append((member, dict(look, variants=variants)))
    return out

  def _isIt(self, member: Any, kind: str, metas: list) -> bool:
    """Whether mcdex reads the block 'kind' at any of 'metas' as 'member'."""
    for meta in metas:
      try:
        if member in self.__game__.membersOf(Block(kind, meta)):
          return True
      except ValueError:  # mcdex needs its block entity's data to say
        continue
    return False

  def _fetch(self, icons: Any) -> None:
    """The game's textures for these icons, those not asked for yet."""
    wanted = sorted(set(icon for icon in icons if icon) -
                    set(self.__textures__))
    if not wanted:
      return
    for name, texture in self.__game__.textures(wanted).items():
      if 'error' in texture or texture['width'] != texture['height']:
        self.__textures__[name] = None
      else:
        self.__textures__[name] = (texture['width'],
                                   tuple(texture['pixels']))

  def _likeness(self, views: list, faces: dict, tint: int,
                squares: dict) -> Optional[float]:
    """A variant's likeness to the views: each face's, by its pixels."""
    total = weight = 0.0
    for at, view in enumerate(views):
      for face, count in view.faces.items():
        texture = self.__textures__.get(faces.get(face, ''))
        if texture is None:
          continue
        size, pixels = texture
        key = (at, face, size)
        if key not in squares:
          squares[key] = view.square(face, size)
        score = likeness(squares[key], pixels, tint)
        if score is not None:
          total += score * count
          weight += count
    return total / weight if weight else None

  @staticmethod
  def _signature(faces: dict, tint: int) -> str:
    """
    What a candidate looks like where it looks most like the views: its
    best variant's faces and its tint. Two candidates alike there look
    the same (1.7.10's infested stone has stone's look among its own).
    """
    return json.dumps([tint, faces], sort_keys=True)

  def _decide(self, pos: BlockPos, scored: list, views: int) -> Any:
    """The best look's member, if it beats the next look by MARGIN."""
    def named(member: Any) -> str:
      return '%s.%s' % (type(member).__name__, member.name)

    if not scored:
      raise TesttimeError('identify', self.perceive(),
                          'no candidate could be compared with the views')
    scored.sort(key=lambda each: -each[0])
    best, member, look = scored[0]
    same = sorted(named(each) for score, each, sign in scored
                  if sign == look)
    others = [(score, each) for score, each, sign in scored if sign != look]
    top = ', '.join('%s %.2f' % (named(each), score)
                    for score, each, _ in scored[:4])
    if len(same) > 1:
      raise TesttimeError('identify', self.perceive(), '%s look the same' % (
        ' and '.join(same),))
    if best < self.LIKENESS:
      infoSpec = """the block at %s looks like none of the candidates: the
      likest is %.2f, under %.2f (%s), from %d views"""
      info = infoSpec % (_place(pos), best, self.LIKENESS, top, views)
      raise TesttimeError('identify', self.perceive(), ' '.join(
        info.split()))
    if others and best - others[0][0] < self.MARGIN:
      infoSpec = """the block at %s: no look beats the next by %.2f (%s),
      from %d views"""
      info = infoSpec % (_place(pos), self.MARGIN, top, views)
      raise TesttimeError('identify', self.perceive(), ' '.join(
        info.split()))
    next_ = ('; next %s %.2f' % (named(others[0][1]), others[0][0])
             if others else '')
    _note('identified by observation: the block at %s as %s (%.2f%s), from '
          '%d views' % (_place(pos), named(member), best, next_, views))
    return member

  def _byTouch(self, pos: BlockPos, why: list) -> Any:
    """
    Nothing of the block shows from any side: air, if the agent can walk
    into its place. Climbing to touch one above is SPEC.md 15.6 step 7's.
    """
    from mcdex import MCBlocks
    seen = self.perceive()
    if pos.y != int(math.floor(seen.pos.y + 1e-6)):
      infoSpec = """no side shows the block at %s, and touching it needs
      climbing: %s"""
      raise TesttimeError('identify', seen, ' '.join((infoSpec % (
        _place(pos), '; '.join(why))).split()))
    try:
      self._walkTo('identify', pos.center(), 0.25, None)
    except TesttimeError as error:
      infoSpec = """no side shows the block at %s, and something stops the
      player stepping into it: %s"""
      raise TesttimeError('identify', error.seen, ' '.join((infoSpec % (
        _place(pos), error)).split())) from error
    _note('identified by touch: the block at %s as MCBlocks.Air (no side '
          'shows it, and the agent walked into it)' % (_place(pos),))
    return MCBlocks.Air

  def _fromSide(self, pos: BlockPos, side: str) -> Perception:
    """Stands 'side' of the block and looks at that face of it."""
    away = {'north': (0, -1), 'south': (0, 1), 'west': (-1, 0),
            'east': (1, 0)}
    if side not in away:
      infoSpec = """examine looks from the north, south, east or west, not
      %r: from above or below needs climbing (SPEC.md 15.6 step 7)"""
      raise ValueError(' '.join((infoSpec % (side,)).split()))
    dx, dz = away[side]
    seen = self.perceive()
    spot = Vec3(pos.x + 0.5 + 2.5 * dx, seen.pos.y, pos.z + 0.5 + 2.5 * dz)
    eye = self._walkTo('examine', spot, 0.25, None).eye
    looked = self._aim(self._faceMiddle(pos, side), eye)
    aim = looked.target
    if aim.kind == 'block' and aim.pos == pos and aim.face == side:
      return looked
    infoSpec = """the %s face of the block at %s isn't targeted from %s: the
    crosshair meets %s"""
    info = infoSpec % (side, _place(pos), _place(eye), _met(aim))
    raise TesttimeError('examine', looked, ' '.join(info.split()))

  # -------------------------------------------------------------- containers

  def open(self, pos: BlockPos, ticks: Optional[int] = None) -> Container:
    """
    Opens the container at 'pos' (a chest, a furnace), as a player does:
    uses it, and sees its screen open, within 10 ticks. The container as
    its screen shows it.

    Raises
    ------
    TesttimeError
      As use does, or no container's screen opens.
    """
    seen = self._use('open', pos, ticks)
    for _ in range(10):
      shown = self.__game__.container()
      if not shown.playerOwn:
        return shown
      self.__game__.ticks(1)
    infoSpec = """using %s at %s opened no container's screen in 10
    ticks"""
    info = infoSpec % (seen.target.id or 'the block', _place(pos))
    raise TesttimeError('open', self.perceive(), ' '.join(info.split()))

  def contents(self) -> tuple:
    """What the open container holds, as its screen shows it."""
    return self._opened('contents').contents

  def inventory(self) -> frozenset:
    """
    The mcdex members in its inventory (the hotbar and the rest), as a
    player knows its own: noted under the test's line, known to the
    agent (SPEC.md 15.2).
    """
    held = frozenset()
    for stack in self.__game__.inventory(side='client').main:
      if not stack.empty:
        held |= self.__game__.membersOf(stack)
    names = sorted('%s.%s' % (type(each).__name__, each.name)
                   for each in held)
    _note('known to the agent: its inventory: %s' % (
      ', '.join(names) or 'nothing'))
    return held

  def take(self, item: Any) -> Item:
    """
    Takes a stack of 'item' (an mcdex member) from the open container
    into the inventory, as a player does: a shift-click on its slot. What
    moved.

    Raises
    ------
    TesttimeError
      No container is open, none of the item is in it, or the click
      moved none of it (no room).
    """
    shown = self._opened('take')
    return self._shift('take', shown, shown.theirs, item, 'the container')

  def put(self, item: Any) -> Item:
    """
    Puts a stack of 'item' (an mcdex member) from the inventory into the
    open container, as a player does: a shift-click on its slot. What
    moved.

    Raises
    ------
    TesttimeError
      No container is open, none of the item is in the inventory, or the
      click moved none of it (no room).
    """
    shown = self._opened('put')
    return self._shift('put', shown, shown.own, item, 'the inventory')

  def close(self) -> None:
    """Closes the open screen, as Esc does."""
    self.__game__.closeScreen()

  def _opened(self, step: str) -> Container:
    """The open container; TesttimeError when none is."""
    shown = self.__game__.container()
    if shown.playerOwn:
      raise TesttimeError(step, self.perceive(), 'no container is open')
    return shown

  def _shift(self, step: str, shown: Container, among: tuple, item: Any,
             where: str) -> Item:
    """Shift-clicks the first slot among those holding 'item'."""
    held = []
    for slot in among:
      stack = shown.slots[slot]
      if stack.empty:
        continue
      if item not in self.__game__.membersOf(stack):
        if stack.id not in held:
          held.append(stack.id)
        continue
      self.__game__.click(slot, mode='quick_move')
      after = self.__game__.container().slots[slot]
      left = 0 if after.empty or after.id != stack.id else after.count
      if left >= stack.count:
        infoSpec = """shift-clicking slot %d (%d %s) moved none of it: no
        room on the other side"""
        info = infoSpec % (slot, stack.count, stack.id)
        raise TesttimeError(step, self.perceive(), ' '.join(info.split()))
      return Item(stack.id, stack.count - left, stack.meta, stack.snbt)
    info = 'no %s.%s in %s (%s)' % (type(item).__name__, item.name, where,
                                    ', '.join(held) or 'it is empty')
    raise TesttimeError(step, self.perceive(), info)

  # ------------------------------------------------------ the verbs' parts

  def _ready(self, step: str, pos: BlockPos,
             ticks: Optional[int]) -> Perception:
    """Into reach of the block at 'pos', looking at it."""
    if not isinstance(pos, BlockPos):
      raise TypeError('%s takes a BlockPos, not %r' % (step, pos))
    self._reach(step, pos, ticks)
    return self._lookAt(step, pos)

  def _aim(self, point: Vec3, eye: Vec3) -> Perception:
    """Looks from 'eye' at 'point'; what it perceives then."""
    across = math.hypot(point.x - eye.x, point.z - eye.z)
    yaw = math.degrees(math.atan2(-(point.x - eye.x), point.z - eye.z))
    pitch = math.degrees(math.atan2(-(point.y - eye.y), across))
    self.__game__.look(yaw, pitch)
    return self.perceive()

  def _select(self, step: str, item: Any) -> int:
    """
    The hotbar slot holding 'item', selected by its key, as a player
    knows its own inventory.
    """
    inventory = self.__game__.inventory(side='client')
    held = []
    for slot in range(9):
      stack = inventory.main[slot]
      if stack.empty:
        continue
      held.append('%s in %d' % (stack.id, slot + 1))
      if item not in self.__game__.membersOf(stack):
        continue
      if inventory.selected != slot:
        self.__game__.tap('key.hotbar.%d' % (slot + 1))
        selected = self.__game__.inventory(side='client').selected
        if selected != slot:
          info = 'the hotbar key %d selected slot %d' % (slot + 1,
                                                         selected + 1)
          raise TesttimeError(step, self.perceive(), info)
      return slot
    info = 'no %s.%s in the hotbar (%s)' % (
      type(item).__name__, item.name, ', '.join(held) or 'it is empty')
    raise TesttimeError(step, self.perceive(), info)

  @staticmethod
  def _standsIn(seen: Perception, pos: BlockPos) -> bool:
    """Whether the player's box takes up some of the block at 'pos'."""
    box = seen.box
    return (pos.x < box.maxX and box.minX < pos.x + 1 and
            pos.y < box.maxY and box.minY < pos.y + 1 and
            pos.z < box.maxZ and box.minZ < pos.z + 1)

  def _stepAside(self, step: str, seen: Perception, pos: BlockPos) -> None:
    """Two blocks away from 'pos', on the side the agent stands."""
    middle = pos.center()
    dx, dz = seen.pos.x - middle.x, seen.pos.z - middle.z
    length = math.hypot(dx, dz)
    if length < 1e-3:
      dx, dz, length = 0.0, 1.0, 1.0
    aside = Vec3(middle.x + 2 * dx / length, seen.pos.y,
                 middle.z + 2 * dz / length)
    self._walkTo(step, aside, 0.25, None)

  @staticmethod
  def _supports(pos: BlockPos) -> list:
    """The blocks beside 'pos', each with its face towards it."""
    x, y, z = pos.x, pos.y, pos.z
    return [(BlockPos(x, y - 1, z), 'up'),
            (BlockPos(x, y, z - 1), 'south'),
            (BlockPos(x, y, z + 1), 'north'),
            (BlockPos(x - 1, y, z), 'east'),
            (BlockPos(x + 1, y, z), 'west'),
            (BlockPos(x, y + 1, z), 'down')]

  @staticmethod
  def _shows(block: BlockPos, face: str, eye: Vec3) -> bool:
    """Whether the eye is on the face's outer side."""
    return {'up': eye.y > block.y + 1, 'down': eye.y < block.y,
            'south': eye.z > block.z + 1, 'north': eye.z < block.z,
            'east': eye.x > block.x + 1, 'west': eye.x < block.x}[face]

  @staticmethod
  def _faceMiddle(block: BlockPos, face: str) -> Vec3:
    """The middle of the block's face, just inside it."""
    dx, dy, dz = {'up': (0, 1, 0), 'down': (0, -1, 0), 'south': (0, 0, 1),
                  'north': (0, 0, -1), 'east': (1, 0, 0),
                  'west': (-1, 0, 0)}[face]
    return Vec3(block.x + 0.5 + 0.45 * dx, block.y + 0.5 + 0.45 * dy,
                block.z + 0.5 + 0.45 * dz)

  # ---------------------------------------------------------------- the loop

  def _hold(self, key: str, down: bool) -> None:
    """
    The key held down or let go, unless it is so already. Jump isn't
    pressed again within JUMP_AGAIN ticks of its last press (a creative
    player would fly): not yet, it is left up.
    """
    if down and key not in self.__held__:
      if key == 'key.jump':
        if (self.__jumped__ is not None and
            self.__now__ - self.__jumped__ < self.JUMP_AGAIN):
          return
        self.__jumped__ = self.__now__
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
               pushed: list, first: int,
               stuck: Optional[int] = None) -> None:
    """
    TesttimeError when pushing on has gained nothing for 'stuck' ticks
    (STUCK, left out).
    """
    if not seen.collidedHorizontally:
      return
    stuck = self.STUCK if stuck is None else stuck
    before = [was for tick, was in pushed if seen.tick - tick >= stuck]
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
  def _lows(pos: BlockPos) -> list:
    """
    Points low in the block's middle column: a small block on its floor
    (26.3's lever, 0.375 high; a pressure plate, a carpet) is met there
    where a ray through its middle or its faces' passes over it.
    """
    return [Vec3(pos.x + 0.5, pos.y + height, pos.z + 0.5)
            for height in (0.25, 0.1, 0.04)]

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

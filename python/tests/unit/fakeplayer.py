"""
FakePlayer: a client player on flat ground without a game, for the
agent's tests (not a test module itself). It moves as 1.7.10's does on
grass, near enough for a controller: each tick the held keys push it
along its look or across it (0.1 a tick on the ground, 0.02 in the air,
0.98 of it, 0.3 of that sneaking), it moves by its motion, stopped by
walls (a sneaking player on the ground by an edge too), and keeps 0.546
of it on the ground, 0.91 in the air. On a ladder (its feet in one) its
motion is held within 0.15 across and 0.15 down, sneaking holds it up,
and pushing into anything lifts it (0.2 up, before gravity). In water
(a water block from 0.4 to 1.4 above its feet) it is pushed 0.02 a
tick, keeps 0.8 of its motion and sinks 0.02 more, holding jump lifts
it 0.04, and pushing into a bank with nothing 0.6 over its feet lifts it
0.3. Creative's double tap is kept: jump pressed twice within 7 ticks
would make it fly ('flew'). Its crosshair is a ray marched from the
eye. Every request waits for the end of the next tick first, as the
probe runs a client step there (Sides), so the agent meets the latency
it meets in the game.

Its clicks are 1.7.10's too, near enough: a key.use pressed right-clicks
what the crosshair targets (a lever toggles; a block held is placed
against the face hit, unless the player stands there); key.attack held
breaks the block targeted, at once in creative, after 'hardness' ticks
otherwise, and then waits 5 ticks before the next. The hotbar keys
select a slot, and the client's inventory is read as the probe gives it.
A chest used opens its screen: container.get shows its 27 slots, then
the player's 27 and its hotbar's 9, as 1.7.10's ContainerChest; a
quick_move click moves a stack across, merging first, as 1.7.10's
transferStackInSlot does; screen.close closes it. Commands read and set
blocks (block.get, block.set: a lever's meta is 5, and 8 more when on)
and a chest's slots (block.items). Its view (view.block) is a frame 64
by 48 written to the file asked for, the block's box 16 by 16 in its
middle: the block's pixels when the crosshair meets the block, none
when it doesn't or the player is 'blind'.

The ground's top is at y 4; walls are full blocks at whole positions.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import math
import random
from typing import Any

from fakeprobe import FakeError
from unittas import png

EYE = 1.62
HALF = 0.3
#  A ladder's box along each edge of its block: (x0, z0, x1, z1) in it
LADDER_EDGES = {'south': (0.0, 0.875, 1.0, 1.0),
                'north': (0.0, 0.0, 1.0, 0.125),
                'east': (0.875, 0.0, 1.0, 1.0),
                'west': (0.0, 0.0, 0.125, 1.0)}
LADDER_METAS = {'south': 2, 'north': 3, 'east': 4, 'west': 5}
HEIGHT = 1.8
GROUND = 4.0
FRICTION = 0.546
REACH = 5.0
#  what a click places: the blocks among the items (a stick places none)
BLOCK_ITEMS = {'minecraft:stone', 'minecraft:dirt'}


def _holds(value: Any, test: dict) -> bool:
  """wait.until's test on a value: path, eq, ge, le, all (PROTOCOL.md)."""
  if 'all' in test:
    return all(_holds(value, each) for each in test['all'])
  for step in test.get('path', ()):
    value = value[step]
  if 'eq' in test:
    return value == test['eq']
  if 'ge' in test:
    return value >= test['ge']
  if 'le' in test:
    return value <= test['le']
  raise ValueError('the fake knows no test %r' % (test,))


def _texture(name: str) -> list:
  """A 16 by 16 texture for an icon: its pattern and colour by its name."""
  chance = random.Random(name)
  colour = {'wool_colored_red': (170, 45, 45),
            'wool_colored_blue': (50, 60, 160)}.get(name, (
              chance.randrange(60, 200), chance.randrange(60, 200),
              chance.randrange(60, 200)))
  if name.startswith('wool_colored_'):
    chance = random.Random('wool')
  out = []
  for _ in range(256):
    shade = 0.45 + chance.random() * 0.55
    r, g, b = (int(c * shade) for c in colour)
    out.append((0xFF << 24) | (r << 16) | (g << 8) | b)
  return out


def _all(icon: str) -> dict:
  return {face: icon for face in ('down', 'up', 'north', 'south', 'west',
                                  'east')}


def _every(colour: int) -> dict:
  return {face: colour for face in ('down', 'up', 'north', 'south', 'west',
                                    'east')}


def _facing(top: str, side: str, front: str, meta: int) -> dict:
  """A furnace's or a dispenser's faces at a facing meta (2 to 5)."""
  faces = {'down': top, 'up': top}
  for number, face in ((2, 'north'), (3, 'south'), (4, 'west'), (5, 'east')):
    faces[face] = front if number == meta else side
  return faces


#  How the fake's blocks look, as block.faces answers: by (id, meta) asked
LOOKS = {
  ('minecraft:stone', 0): [(0, _all('stone'))],
  ('minecraft:cobblestone', 0): [(0, _all('cobblestone'))],
  ('minecraft:furnace', 0): [(m, _facing('furnace_top', 'furnace_side',
                                         'furnace_front_off', m))
                             for m in (2, 3, 4, 5)],
  ('minecraft:dispenser', 0): [(m, _facing('furnace_top', 'furnace_side',
                                           'dispenser_front_horizontal', m))
                               for m in (2, 3, 4, 5)],
  ('minecraft:crafting_table', 0): [(0, {
    'down': 'planks_oak', 'up': 'crafting_table_top',
    'north': 'crafting_table_front', 'south': 'crafting_table_side',
    'west': 'crafting_table_front', 'east': 'crafting_table_side'})],
  ('minecraft:wool', 14): [(14, _all('wool_colored_red'))],
  ('minecraft:wool', 11): [(11, _all('wool_colored_blue'))],
}


def _faced(top: str, side: str, front: str, facing: str) -> dict:
  """A furnace's faces, 26.3's textures, facing north, south, west or east."""
  faces = {'down': top, 'up': top}
  for face in ('north', 'south', 'west', 'east'):
    faces[face] = front if face == facing else side
  return faces


def _drawn(key: Any, faces: dict, states: tuple = ({},),
           tints: Any = None, mirrored: bool = False) -> dict:
  """One way 26.3 draws a block: its key here, for the fake's own walls."""
  return {'key': key, 'states': [dict(each) for each in states],
          'faces': faces, 'tints': dict(tints or {}), 'mirrored': mirrored}


_FURNACE = ('minecraft:block/furnace_top', 'minecraft:block/furnace_side',
            'minecraft:block/furnace_front')
#  How the fake's blocks look from 1.13 on, as 26.3's block.faces answers:
#  by id, each way the block is drawn (its key in the fake's metas, the
#  first unless one is set): its states, its faces' textures, the faces
#  drawn tinted and with what colour, and whether its textures are drawn
#  mirrored (26.3 draws stone one way or the other, at random)
LOOKS_26 = {
  'minecraft:stone': [
    _drawn('plain', _all('minecraft:block/stone')),
    _drawn('mirrored', _all('minecraft:block/stone'), mirrored=True)],
  'minecraft:cobblestone': [_drawn('plain',
                                   _all('minecraft:block/cobblestone'))],
  'minecraft:furnace': [
    _drawn(facing, _faced(*_FURNACE, facing),
           states=({'facing': facing, 'lit': 'false'},))
    for facing in ('north', 'south', 'west', 'east')],
  #  one texture, two tints: told apart by their colours alone
  'minecraft:oak_leaves': [_drawn('plain', _all('minecraft:block/leaves'),
                                  tints=_every(0x48B518))],
  'minecraft:spruce_leaves': [_drawn('plain',
                                     _all('minecraft:block/leaves'),
                                     tints=_every(0x619961))],
}


#  Where a texel (u, v) of each face is, from the block's least corner, as
#  1.7.10 draws it: a side face's texture upright and unmirrored to one
#  facing it, the top's and the bottom's along x and z.
FACE_POINT = {
  'down': lambda u, v: (u, 0.0, v), 'up': lambda u, v: (u, 1.0, v),
  'north': lambda u, v: (1.0 - u, 1.0 - v, 0.0),
  'south': lambda u, v: (u, 1.0 - v, 1.0),
  'west': lambda u, v: (0.0, 1.0 - v, u),
  'east': lambda u, v: (1.0, 1.0 - v, 1.0 - u)}


def corners(face: str, mirrored: bool = False) -> list:
  """
  A face's corners as 26.3's block.faces gives them, [x, y, z, u, v]
  each: where in the block, and where on its texture; mirrored, the
  texture's left and right the other way.
  """
  out = []
  for u, v in ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)):
    x, y, z = FACE_POINT[face](1.0 - u if mirrored else u, v)
    out.append([x, y, z, u, v])
  return out


def faceCamera(pos: tuple, face: str, eye: tuple, rect: tuple,
               width: int, height: int) -> dict:
  """
  A view.block camera that draws the face of the block at 'pos' square
  onto 'rect' of a width by height frame, one pixel a texel when the
  rect is 16 by 16: orthographic, its matrices as the probe sends them.
  """
  x0, y0, x1, y1 = rect
  origin = [float(p) for p in pos]
  corner = [o + c for o, c in zip(origin, FACE_POINT[face](0.0, 0.0))]
  along = [o + c - k for o, c, k in zip(origin, FACE_POINT[face](1.0, 0.0),
                                        corner)]
  down = [o + c - k for o, c, k in zip(origin, FACE_POINT[face](0.0, 1.0),
                                       corner)]
  #  u = along . (W - corner), v = down . (W - corner): along and down
  #  are axis-aligned unit vectors, so each is its own inverse
  rows = []
  for axis, start, size, flip in ((along, x0, x1 - x0, False),
                                  (down, y0, y1 - y0, True)):
    #  pixel = start + size * t, and the ndc from the pixel, GL's way up
    if flip:
      scale = -2.0 * size / height
      shift = 1.0 - 2.0 * start / height
    else:
      scale = 2.0 * size / width
      shift = 2.0 * start / width - 1.0
    coefficients = [scale * a for a in axis]
    constant = shift - sum(c * k for c, k in zip(coefficients, corner))
    #  relative to the eye, as the probe's camera is
    constant += sum(c * e for c, e in zip(coefficients, eye))
    rows.append(coefficients + [constant])
  rows.append([0.0, 0.0, 0.0, 0.0])
  rows.append([0.0, 0.0, 0.0, 1.0])
  projection = [rows[r][c] for c in range(4) for r in range(4)]
  identity = [1.0 if r == c else 0.0 for c in range(4) for r in range(4)]
  return {'pos': list(eye), 'look': {'yaw': 0.0, 'pitch': 0.0},
          'modelview': identity, 'projection': projection,
          'viewport': [0, 0, width, height]}


class FakePlayer:
  """One player, at x, z on the ground, looking yaw and pitch."""

  def __init__(self, x: float = 0.5, z: float = 0.5,
               yaw: float = 0.0) -> None:
    self.x = x
    self.z = z
    self.yaw = yaw
    self.pitch = 0.0
    self.mx = 0.0
    self.mz = 0.0
    self.tick = 100
    self.keys = set()
    self.walls = {}
    self.collided = False
    #  every request's op, as it came
    self.ops = []
    #  where it stood after each tick
    self.trail = []
    #  the ticks it ran into something
    self.bumps = 0
    #  the ground's blocks broken
    self.dug = set()
    #  the levers, by place: on or off
    self.levers = {}
    self.creative = True
    #  the ticks of mining a block takes out of creative
    self.hardness = 6
    self.mining = None
    #  a block that turns into another as it is mined (dirt grown to grass on a random tick): by its place, after how
    #  many ticks of mining, and what it becomes; its mining goes on, as the game's does
    self.becomes = {}
    self.hitDelay = 0
    #  the keys pressed since the last tick, which click once
    self.pressed = set()
    #  the nine hotbar slots, as inventory.get gives items, and the rest
    self.hotbar = [None] * 9
    self.rest = [None] * 27
    #  the chests, by place: 27 slots each; the one whose screen is open
    self.chests = {}
    self.screen = None
    self.selected = 0
    #  what its clicks did: ('use', pos), ('placed', pos), ('broke', pos)
    self.clicks = []
    #  whether its views see nothing; the light its views show faces in
    self.blind = False
    self.light = 0.8
    #  the blocks' metas, by place (a furnace's facing); how blocks look
    self.metas = {}
    self.looks = dict(LOOKS)
    #  whether its game is 1.13's or later: blocks without metas, drawn as
    #  LOOKS_26 says, a variant's key in metas
    self.flattened = False
    self.looks26 = dict(LOOKS_26)
    #  its feet's height and its motion up, whether it stands on something
    self.y = GROUND
    self.my = 0.0
    self.onGround = True
    #  the columns raised above the ground, by (x, z): their tops (4.5 a
    #  slab, 5 a block, 6 two)
    self.raised = {}
    #  every key asked for, down or tapped
    self.keysAsked = []
    #  the doors, two blocks high from the ground, by (x, z): whether
    #  open, and whether a hand opens it (an iron door doesn't); a stuck
    #  one blocks open or shut
    self.doors = {}
    #  the ladders' blocks, by (x, y, z): the edge their box is along
    self.ladders = {}
    #  blocks smaller than a block (26.3's floor lever), by (x, y, z): their
    #  shape, a box in the block (x0, y0, z0, x1, y1, z1); they stop
    #  nothing (in walls too, by their id)
    self.lows = {}
    #  how fast it came down each time it landed
    self.landed = []
    #  the water's blocks and lava's, by (x, y, z) (the ground's where they
    #  are dug); whether it was ever in water
    self.water = set()
    self.lava = set()
    self.swam = False
    #  creative's double tap on jump: ticks left to tap again; whether it
    #  flies, and whether it ever did
    self.flyToggle = 0
    self.flying = False
    self.flew = False

  # --------------------------------------------------------------- the world

  def solid(self, x: int, y: int, z: int) -> bool:
    if (x, y, z) in self.lows:
      return False
    if y < GROUND:
      return (x, y, z) not in self.dug
    if y < self.raised.get((x, z), GROUND):
      return True
    return (x, y, z) in self.walls

  def blockId(self, x: int, y: int, z: int) -> str:
    if (x, z) in self.doors and y in (4, 5):
      return ('minecraft:wooden_door' if self.doors[(x, z)].get('hand', True)
              else 'minecraft:iron_door')
    if y < GROUND:
      return 'minecraft:grass'
    if y < self.raised.get((x, z), GROUND):
      return 'minecraft:stone'
    return self.walls[(x, y, z)]

  def top(self, x: int, y: int, z: int) -> float:
    """A solid block's box's top: half a block for a raised slab."""
    return min(y + 1.0, self.raised.get((x, z), y + 1.0)) if (
      y >= GROUND and (x, z) in self.raised) else y + 1.0

  def cells(self, x: float, z: float) -> list:
    """The columns the player's box takes up at x, z."""
    return [(cx, cz)
            for cx in range(math.floor(x - HALF),
                            math.floor(x + HALF - 1e-9) + 1)
            for cz in range(math.floor(z - HALF),
                            math.floor(z + HALF - 1e-9) + 1)]

  def doorBoxes(self, x: int, z: int) -> list:
    """A door's boxes: along its north edge shut, its west edge open."""
    door = self.doors[(x, z)]
    if door['open'] and not door.get('stuck'):
      return [(x, z, x + 0.1875, z + 1)]
    return [(x, z, x + 1, z + 0.1875)]

  def ladderBoxes(self) -> list:
    """Each ladder block's box: (x0, y0, z0, x1, y1, z1)."""
    return [(x + x0, float(y), z + z0, x + x1, y + 1.0, z + z1)
            for (x, y, z), edge in self.ladders.items()
            for x0, z0, x1, z1 in (LADDER_EDGES[edge],)]

  def overlaps(self, x: float, z: float, box: tuple) -> bool:
    """Whether the player's box at x, z meets the box's across."""
    return (x - HALF < box[3] and box[0] < x + HALF and
            z - HALF < box[5] and box[2] < z + HALF)

  def onLadder(self) -> bool:
    """Whether its feet are in a ladder's block (1.7.10's isOnLadder)."""
    return (math.floor(self.x), math.floor(self.y),
            math.floor(self.z)) in self.ladders

  def floorOf(self, cx: int, cz: int) -> float:
    """A column's top: raised, or the ground's, lower where it is dug."""
    if (cx, cz) in self.raised:
      return self.raised[(cx, cz)]
    y = int(GROUND)
    while (cx, y - 1, cz) in self.dug:
      y -= 1
    return float(y)

  def inWater(self) -> bool:
    """Whether water is from 0.4 to 1.4 over its feet (1.7.10's test)."""
    return any((cx, cy, cz) in self.water
               for cx, cz in self.cells(self.x, self.z)
               for cy in range(math.floor(self.y + 0.4),
                               math.floor(self.y + 1.4) + 1))

  def hopClear(self) -> bool:
    """Whether its box 0.6 higher meets no block and no liquid."""
    for cx, cz in self.cells(self.x, self.z):
      if self.floorOf(cx, cz) > self.y + 0.6 + 1e-9:
        return False
      for cy in range(math.floor(self.y + 0.6),
                      math.floor(self.y + 0.6 + HEIGHT) + 1):
        if ((cx, cy, cz) in self.water or (cx, cy, cz) in self.lava or
            (cx, cy, cz) in self.walls):
          return False
    return True

  def under(self, x: float, z: float) -> float:
    """
    The floor under the player's box at x, z: its columns' highest, or a
    ladder's top it stands on.
    """
    floor = max(self.floorOf(*cell) for cell in self.cells(x, z))
    for box in self.ladderBoxes():
      if box[4] <= self.y + 0.5 + 1e-9 and self.overlaps(x, z, box):
        floor = max(floor, box[4])
    return floor

  def edged(self, d: float, alongX: bool) -> float:
    """
    A sneaking player's move on the ground, cut short of an edge as
    1.7.10's is: by 0.05 at a time while nothing is within 1 below.
    """
    while d != 0.0:
      x, z = (self.x + d, self.z) if alongX else (self.x, self.z + d)
      if self.under(x, z) > self.y - 1.0 + 1e-9:
        break
      d = 0.0 if abs(d) < 0.05 else d - math.copysign(0.05, d)
    return d

  def blocked(self, x: float, z: float) -> bool:
    """
    Whether the player's box at x, z meets a wall or a step too high: up
    half a block it steps on the ground, and nothing off it.
    """
    step = 0.5 if self.onGround else 0.0
    for box in self.ladderBoxes():
      if (box[1] < self.y + HEIGHT and box[4] > self.y + 0.5 + 1e-9 and
          self.overlaps(x, z, box)):
        return True
    for cx, cz in self.cells(x, z):
      for cy in (int(GROUND), int(GROUND) + 1):
        if (cx, cy, cz) in self.walls and (cx, cy, cz) not in self.lows:
          return True
      if self.floorOf(cx, cz) > self.y + step + 1e-9:
        return True
      if (cx, cz) in self.doors:
        for bx0, bz0, bx1, bz1 in self.doorBoxes(cx, cz):
          if (x - HALF < bx1 and bx0 < x + HALF and z - HALF < bz1 and
              bz0 < z + HALF):
            return True
    return False

  # ------------------------------------------------------------------- ticks

  def step(self) -> None:
    """One tick: the clicks, then movement, as 1.7.10's."""
    self.tick += 1
    self.click()
    forward = strafe = 0.0
    for key, along, across in (('key.forward', 0.98, 0.0),
                               ('key.back', -0.98, 0.0),
                               ('key.left', 0.0, 0.98),
                               ('key.right', 0.0, -0.98)):
      if key in self.keys:
        forward += along
        strafe += across
    if 'key.sneak' in self.keys:
      forward *= 0.3
      strafe *= 0.3
    size = math.hypot(forward, strafe)
    if size > 1.0:
      forward, strafe = forward / size, strafe / size
    yaw = math.radians(self.yaw)
    grounded = self.onGround
    water = self.inWater()
    self.swam = self.swam or water
    if water and 'key.jump' in self.keys:
      self.my += 0.04
    push = 0.1 if grounded and not water else 0.02
    self.mx += (strafe * math.cos(yaw) - forward * math.sin(yaw)) * push
    self.mz += (forward * math.cos(yaw) + strafe * math.sin(yaw)) * push
    ladder = self.onLadder() and not water
    if ladder:
      self.mx = max(-0.15, min(0.15, self.mx))
      self.mz = max(-0.15, min(0.15, self.mz))
      self.my = max(self.my, -0.15)
      if 'key.sneak' in self.keys and self.my < 0.0:
        self.my = 0.0
    sneaking = grounded and 'key.sneak' in self.keys
    self.collided = False
    dx = self.edged(self.mx, True) if sneaking else self.mx
    if self.blocked(self.x + dx, self.z):
      self.collided = True
      self.mx = 0.0
    else:
      self.x += dx
    dz = self.edged(self.mz, False) if sneaking else self.mz
    if self.blocked(self.x, self.z + dz):
      self.collided = True
      self.mz = 0.0
    else:
      self.z += dz
    #  up and down: a step up half a block as the game takes it; a jump,
    #  0.42 up, 0.08 less each tick and 0.98 kept; a fall; a climb
    ground = self.under(self.x, self.z)
    if self.onGround and self.y < ground <= self.y + 0.5 + 1e-9:
      self.y = ground
    if 'key.jump' in self.keys and self.onGround and not water:
      self.my = 0.42
    self.y += self.my
    if self.y <= ground:
      if not self.onGround:
        self.landed.append(-self.my)
      self.y, self.my, self.onGround = ground, 0.0, True
    else:
      self.onGround = False
    if water:
      self.mx *= 0.8
      self.mz *= 0.8
      self.my = self.my * 0.8 - 0.02
      if self.collided and self.hopClear():
        self.my = 0.3
    else:
      if self.collided and ladder:
        self.my = 0.2
      self.my = (self.my - 0.08) * 0.98
      #  what it keeps: as it stood when the tick began
      friction = FRICTION if grounded else 0.91
      self.mx *= friction
      self.mz *= friction
    self.trail.append((self.x, self.z))
    self.bumps += self.collided

  def ops_keys(self) -> set:
    """Every key it was asked to hold or tap."""
    return set(self.keysAsked)

  def run(self, n: int) -> None:
    for _ in range(n):
      self.step()

  # ------------------------------------------------------------------ clicks

  def click(self) -> None:
    pressed, self.pressed = self.pressed, set()
    if self.flyToggle > 0:
      self.flyToggle -= 1
    if 'key.jump' in pressed and self.creative:
      if self.flyToggle > 0:
        self.flying = not self.flying
        self.flew = True
        self.flyToggle = 0
      else:
        self.flyToggle = 7
    for key in pressed:
      if key.startswith('key.hotbar.'):
        self.selected = int(key.rsplit('.', 1)[1]) - 1
    if self.hitDelay > 0:
      self.hitDelay -= 1
    target = self.target()
    pos = tuple(target['block']) if target else None
    if 'key.use' in pressed and pos is not None:
      self.use(pos, target['face'])
    if 'key.attack' in self.keys and pos is not None:
      self.mine(pos)
    else:
      self.mining = None

  def standsIn(self, cell: tuple) -> bool:
    """Whether the player's box takes up some of the cell."""
    x, y, z = cell
    return (x < self.x + HALF and self.x - HALF < x + 1 and
            y < GROUND + HEIGHT and GROUND < y + 1 and
            z < self.z + HALF and self.z - HALF < z + 1)

  def use(self, pos: tuple, face: str) -> None:
    if (pos[0], pos[2]) in self.doors and pos[1] in (4, 5):
      door = self.doors[(pos[0], pos[2])]
      if door.get('hand', True):
        door['open'] = not door['open']
        self.clicks.append(('door', (pos[0], 4, pos[2])))
      return
    if self.walls.get(pos) == 'minecraft:chest':
      self.screen = pos
      self.clicks.append(('open', pos))
      return
    if self.walls.get(pos) == 'minecraft:lever':
      self.levers[pos] = not self.levers.get(pos, False)
      self.clicks.append(('use', pos))
      return
    held = self.hotbar[self.selected]
    if held is None or held['id'] not in BLOCK_ITEMS:
      return
    step = {'up': (0, 1, 0), 'down': (0, -1, 0), 'north': (0, 0, -1),
            'south': (0, 0, 1), 'west': (-1, 0, 0), 'east': (1, 0, 0)}[face]
    cell = tuple(p + d for p, d in zip(pos, step))
    if self.solid(*cell) or self.standsIn(cell):
      return
    self.walls[cell] = held['id']
    self.clicks.append(('placed', cell))

  def mine(self, pos: tuple) -> None:
    if self.hitDelay > 0:
      return
    if not self.creative:
      if self.mining is None or self.mining[0] != pos:
        self.mining = [pos, 0]
      self.mining[1] += 1
      change = self.becomes.get(pos)
      if change is not None and self.mining[1] == change[0]:
        self.walls[pos] = change[1]
      if self.mining[1] < self.hardness:
        return
    if pos[1] < GROUND:
      self.dug.add(pos)
    else:
      del self.walls[pos]
      self.levers.pop(pos, None)
    self.clicks.append(('broke', pos))
    self.mining = None
    self.hitDelay = 5

  # -------------------------------------------------------------- containers

  def worldLook(self, pos: tuple) -> Any:
    """
    How the block at 'pos' is drawn: its faces, the tinted ones' tints and
    whether it is mirrored; by its id and meta (or, flattened, the key of
    the way it is drawn); None for no look.
    """
    if self.flattened:
      drawn = self.looks26.get(self.walls.get(pos), ())
      key = self.metas.get(pos)
      for each in drawn:
        if key is None or each['key'] == key:
          return each['faces'], each['tints'], each['mirrored']
      return None
    meta = self.metas.get(pos, 0)
    for (kind, _), variants in self.looks.items():
      if kind != self.walls.get(pos):
        continue
      for variant, faces in variants:
        if variant == meta:
          return faces, {}, False
    return None

  def slotsShown(self) -> list:
    """The open chest's slots, then the player's 27, then its hotbar."""
    return self.chests[self.screen] + self.rest + self.hotbar

  def setSlot(self, index: int, item: Any) -> None:
    if index < 27:
      self.chests[self.screen][index] = item
    elif index < 54:
      self.rest[index - 27] = item
    else:
      self.hotbar[index - 54] = item

  def quickMove(self, index: int) -> None:
    """A shift-click: the stack to the other side, merging first."""
    shown = self.slotsShown()
    stack = shown[index]
    if stack is None:
      return
    stack = dict(stack)
    into = list(range(62, 26, -1)) if index < 27 else list(range(27))
    for target in into:
      there = shown[target]
      if there and (there['id'], there['meta']) == (stack['id'],
                                                    stack['meta']):
        moved = min(64 - there['count'], stack['count'])
        self.setSlot(target, dict(there, count=there['count'] + moved))
        stack['count'] -= moved
        shown = self.slotsShown()
      if not stack['count']:
        break
    for target in into:
      if stack['count'] and shown[target] is None:
        self.setSlot(target, dict(stack))
        stack['count'] = 0
        shown = self.slotsShown()
    self.setSlot(index, stack if stack['count'] else None)

  def containerShown(self) -> dict:
    if self.screen is None:
      slots = [None] * 9 + self.rest + self.hotbar
      return {'class': 'net.minecraft.inventory.ContainerPlayer',
              'window': 0, 'player_own': True,
              'slots': [{'index': i, 'item': item}
                        for i, item in enumerate(slots)],
              'player_slots': [9, 44]}
    return {'class': 'net.minecraft.inventory.ContainerChest', 'window': 1,
            'player_own': False,
            'slots': [{'index': i, 'item': item}
                      for i, item in enumerate(self.slotsShown())],
            'player_slots': [27, 62]}

  # ------------------------------------------------------- what it perceives

  def target(self) -> Any:
    yaw, pitch = math.radians(self.yaw), math.radians(self.pitch)
    dx = -math.sin(yaw) * math.cos(pitch)
    dy = -math.sin(pitch)
    dz = math.cos(yaw) * math.cos(pitch)
    eye = (self.x, self.y + EYE, self.z)
    last = tuple(math.floor(v) for v in eye)
    n = 0
    while n * 0.005 <= REACH:
      at = tuple(e + d * n * 0.005 for e, d in zip(eye, (dx, dy, dz)))
      cell = tuple(math.floor(v) for v in at)
      door = (cell[0], cell[2]) in self.doors and cell[1] in (4, 5)
      if cell in self.lows and all(
          low <= p - c < high for p, c, low, high in zip(
            at, cell, self.lows[cell][:3], self.lows[cell][3:])):
        #  inside a small block's shape: met, from above
        return {'block': list(cell), 'face': 'up', 'hit': list(at),
                'id': self.blockId(*cell), 'meta': 0}
      if cell != last and (self.solid(*cell) or door):
        moved = tuple(c - l for c, l in zip(cell, last))
        face = {(0, -1, 0): 'up', (0, 1, 0): 'down', (0, 0, 1): 'north',
                (0, 0, -1): 'south', (1, 0, 0): 'west',
                (-1, 0, 0): 'east'}.get(moved, 'up')
        return {'block': list(cell), 'face': face, 'hit': list(at),
                'id': self.blockId(*cell), 'meta': 0}
      last = cell
      n += 1
    return None

  def near(self, around: int) -> list:
    fx, fz = math.floor(self.x), math.floor(self.z)
    found = []
    for y in range(int(GROUND) - 1, int(GROUND) + 4):
      for x in range(fx - around, fx + around + 1):
        for z in range(fz - around, fz + around + 1):
          if not self.solid(x, y, z):
            continue
          found.append({'pos': [x, y, z], 'id': self.blockId(x, y, z),
                        'meta': 0,
                        'boxes': [[float(x), float(y), float(z),
                                   x + 1.0, self.top(x, y, z), z + 1.0]],
                        'liquid': False, 'climbable': False,
                        'opens': False})
    for kind, blocks in (('water', self.water), ('lava', self.lava)):
      for x, y, z in sorted(blocks):
        if abs(x - fx) <= around and abs(z - fz) <= around:
          found.append({'pos': [x, y, z], 'id': 'minecraft:' + kind,
                        'meta': 0, 'boxes': [], 'liquid': True,
                        'climbable': False, 'opens': False})
    for (x, y, z), edge in sorted(self.ladders.items()):
      if abs(x - fx) <= around and abs(z - fz) <= around:
        x0, z0, x1, z1 = LADDER_EDGES[edge]
        found.append({'pos': [x, y, z], 'id': 'minecraft:ladder',
                      'meta': LADDER_METAS[edge],
                      'boxes': [[x + x0, float(y), z + z0, x + x1, y + 1.0,
                                 z + z1]],
                      'liquid': False, 'climbable': True, 'opens': False})
    for (x, z), door in self.doors.items():
      if abs(x - fx) <= around and abs(z - fz) <= around:
        for y in (4, 5):
          found.append({'pos': [x, y, z], 'id': self.blockId(x, y, z),
                        'meta': 0,
                        'boxes': [[bx0, float(y), bz0, bx1, y + 1.0, bz1]
                                  for bx0, bz0, bx1, bz1 in
                                  self.doorBoxes(x, z)],
                        'liquid': False, 'climbable': False,
                        'opens': door.get('hand', True)})
    return found

  def perceived(self, around: int) -> dict:
    return {
      'tick': self.tick, 'pos': [self.x, self.y, self.z],
      'eye': [self.x, self.y + EYE, self.z],
      'box': [self.x - HALF, self.y, self.z - HALF, self.x + HALF,
              self.y + HEIGHT, self.z + HALF],
      'look': {'yaw': self.yaw, 'pitch': self.pitch},
      'motion': [self.mx, self.my if not self.onGround else
                 -0.0784000015258789, self.mz],
      'on_ground': self.onGround,
      'collided': {'horizontally': self.collided, 'vertically': True},
      'in_water': self.inWater(), 'in_lava': False,
      'on_ladder': self.onLadder(),
      'sneaking': 'key.sneak' in self.keys, 'sprinting': False,
      'flying': self.flying, 'reach': {'block': REACH, 'entity': 6.0},
      'target': self.target(), 'blocks': self.near(around)}

  # ----------------------------------------------------- the probe's answers

  def handlers(self) -> dict:
    """The fake probe's handlers: each waits for the tick's end first."""

    def at(op: str, does):
      def handler(args: dict, side: Any) -> Any:
        self.ops.append(op)
        self.step()
        return does(args)
      return handler

    def look(args: dict) -> dict:
      self.yaw = float(args['yaw'])
      self.pitch = float(args['pitch'])
      self.step()
      return {}

    def wait(args: dict) -> dict:
      self.run(int(args['n']) - 1)
      return {'waited_ms': 50, 'from': self.tick, 'tick': self.tick}

    def down(args: dict) -> dict:
      self.keysAsked.append(args['key'])
      self.keys.add(args['key'])
      self.pressed.add(args['key'])
      return {}

    def tap(args: dict) -> dict:
      down(args)
      self.run(int(args.get('ticks', 1)))
      self.keys.discard(args['key'])
      self.step()
      return {}

    def click(args: dict) -> dict:
      if self.screen is None:
        raise FakeError('NotReady', 'no container screen is open')
      if args.get('mode') == 'quick_move':
        self.quickMove(int(args['slot']))
      self.run(2)
      return {}

    def close(args: dict) -> dict:
      self.screen = None
      self.step()
      return {}

    def blockGet(args: dict) -> dict:
      pos = tuple(args['pos'])
      if not self.solid(*pos):
        return {'id': 'minecraft:air', 'meta': 0, 'tile': None}
      meta = self.metas.get(pos, 0)
      if pos in self.levers:
        meta = 5 + (8 if self.levers[pos] else 0)
      return {'id': self.blockId(*pos), 'meta': meta, 'tile': None}

    def blockSet(args: dict) -> dict:
      pos, block = tuple(args['pos']), args['block']
      self.levers.pop(pos, None)
      self.chests.pop(pos, None)
      if block['id'] == 'minecraft:air':
        self.walls.pop(pos, None)
        return {}
      self.walls[pos] = block['id']
      self.metas[pos] = block.get('meta', 0)
      if block['id'] == 'minecraft:lever':
        self.levers[pos] = bool(block.get('meta', 0) & 8)
      if block['id'] == 'minecraft:chest':
        self.chests[pos] = [None] * 27
      return {}

    def blockItems(args: dict) -> dict:
      pos = tuple(args['pos'])
      if pos not in self.chests:
        there = self.blockId(*pos) if self.solid(*pos) else 'minecraft:air'
        raise FakeError('NotFound', 'no inventory at %s: %s is there' % (
          pos, there))
      return {'slots': list(self.chests[pos])}

    def view(args: dict) -> dict:
      pos = tuple(args['pos'])
      target = self.target()
      mine = (not self.blind and target is not None and
              tuple(target['block']) == pos)
      eye = (self.x, self.y + EYE, self.z)
      look = self.worldLook(pos) if mine else None
      texture = _texture(look[0][target['face']]) if look else None
      tint = look[1].get(target['face'], 0xFFFFFF) if look else 0xFFFFFF
      data = bytearray()
      for y in range(48):
        for x in range(64):
          inside = 24 <= x < 40 and 16 <= y < 32
          if inside and texture:
            across = 15 - (x - 24) if look[2] else x - 24
            argb = texture[(y - 16) * 16 + across]
            data += bytes(int(((argb >> shift) & 255) * self.light *
                              ((tint >> shift) & 255) / 255)
                          for shift in (16, 8, 0))
          else:
            data += bytes((200, 40, 40) if inside and mine else (90, 90, 90))
      png.write(args['file'], 64, 48, 3, bytes(data))
      camera = (faceCamera(pos, target['face'], eye, (24, 16, 40, 32), 64,
                           48) if mine else
                {'pos': list(eye),
                 'look': {'yaw': self.yaw, 'pitch': self.pitch},
                 'modelview': [0.0] * 16, 'projection': [0.0] * 16,
                 'viewport': [0, 0, 64, 48]})
      return {'file': args['file'], 'width': 64, 'height': 48,
              'tick': self.tick, 'camera': camera,
              'rect': [24, 16, 40, 32],
              'mask': [('1' if mine else '0') * 16] * 16,
              'faces': {target['face']: 256} if mine else {},
              'covered': []}

    def blockFaces(args: dict) -> dict:
      out = []
      if self.flattened:
        for block in args['blocks']:
          if 'meta' in block:
            raise FakeError('BadRequest', "26.3's blocks have no meta",
                            field='blocks')
          variants = [{'states': each['states'], 'faces': each['faces'],
                       'tints': each['tints'],
                       'corners': {face: corners(face, each['mirrored'])
                                   for face in each['faces']}}
                      for each in self.looks26.get(block['id'], ())]
          out.append({'cube': bool(variants), 'tint': 0xFFFFFF,
                      'variants': variants})
        return {'blocks': out}
      for block in args['blocks']:
        variants = [{'metas': [m], 'faces': faces}
                    for (kind, _), each in sorted(self.looks.items())
                    if kind == block['id'] for m, faces in each]
        out.append({'cube': bool(variants), 'tint': 0xFFFFFF,
                    'variants': variants})
      return {'blocks': out}

    def textures(args: dict) -> dict:
      return {'icons': {name: {'width': 16, 'height': 16,
                               'pixels': _texture(name)}
                        for name in args['icons']}}

    def until(args: dict) -> dict:
      """The fake's changes are there at once: the check holds now or not."""
      reads = {'block.get': blockGet, 'inventory.get': inventory}
      if args['op'] not in reads:
        raise FakeError('Unsupported', 'the fake checks no %s' % args['op'])
      value = reads[args['op']](args['args'])
      return {'held': _holds(value, args['test']), 'tick': self.tick,
              'checks': 1, 'value': value}

    def inventory(args: dict) -> Any:
      main = list(self.hotbar) + list(self.rest)
      if args.get('slot') == 'held':
        return main[self.selected]
      return {'selected': self.selected, 'main': main,
              'armor': {'feet': None, 'legs': None, 'chest': None,
                        'head': None}, 'cursor': None}

    return {
      'player.perceive': at('player.perceive',
                            lambda args: self.perceived(args['around'])),
      'player.look': at('player.look', look),
      'key.down': at('key.down', down),
      'key.tap': at('key.tap', tap),
      'inventory.get': at('inventory.get', inventory),
      'container.get': at('container.get',
                          lambda args: self.containerShown()),
      'container.click': at('container.click', click),
      'screen.close': at('screen.close', close),
      'block.get': at('block.get', blockGet),
      'block.set': at('block.set', blockSet),
      'block.items': at('block.items', blockItems),
      'view.block': at('view.block', view),
      'block.faces': at('block.faces', blockFaces),
      'texture.get': at('texture.get', textures),
      'key.up': at('key.up',
                   lambda args: self.keys.discard(args['key']) or {}),
      'ticks.wait': at('ticks.wait', wait),
      'wait.until': at('wait.until', until),
    }

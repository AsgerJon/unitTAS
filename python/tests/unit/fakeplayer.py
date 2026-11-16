"""
FakePlayer: a client player on flat ground without a game, for the
agent's tests (not a test module itself). It moves as 1.7.10's does on
grass, near enough for a controller: each tick the held keys push it
along its look (0.1 a tick, 0.98 of it forward, 0.3 of that sneaking),
it moves by its motion, stopped by walls, and keeps 0.546 of it. Its
crosshair is a ray marched from the eye. Every request waits for the
end of the next tick first, as the probe runs a client step there
(Sides), so the agent meets the latency it meets in the game.

Its clicks are 1.7.10's too, near enough: a key.use pressed right-clicks
what the crosshair targets (a lever toggles; a block held is placed
against the face hit, unless the player stands there); key.attack held
breaks the block targeted, at once in creative, after 'hardness' ticks
otherwise, and then waits 5 ticks before the next. The hotbar keys
select a slot, and the client's inventory is read as the probe gives it.

The ground's top is at y 4; walls are full blocks at whole positions.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import math
from typing import Any

EYE = 1.62
HALF = 0.3
HEIGHT = 1.8
GROUND = 4.0
FRICTION = 0.546
REACH = 5.0
#  what a click places: the blocks among the items (a stick places none)
BLOCK_ITEMS = {'minecraft:stone', 'minecraft:dirt'}


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
    self.hitDelay = 0
    #  the keys pressed since the last tick, which click once
    self.pressed = set()
    #  the nine hotbar slots, as inventory.get gives items, and the rest
    self.hotbar = [None] * 9
    self.selected = 0
    #  what its clicks did: ('use', pos), ('placed', pos), ('broke', pos)
    self.clicks = []

  # --------------------------------------------------------------- the world

  def solid(self, x: int, y: int, z: int) -> bool:
    if y < GROUND:
      return (x, y, z) not in self.dug
    return (x, y, z) in self.walls

  def blockId(self, x: int, y: int, z: int) -> str:
    return 'minecraft:grass' if y < GROUND else self.walls[(x, y, z)]

  def blocked(self, x: float, z: float) -> bool:
    """Whether the player's box at x, z meets a wall."""
    for cx in range(math.floor(x - HALF), math.floor(x + HALF - 1e-9) + 1):
      for cz in range(math.floor(z - HALF),
                      math.floor(z + HALF - 1e-9) + 1):
        for cy in (int(GROUND), int(GROUND) + 1):
          if (cx, cy, cz) in self.walls:
            return True
    return False

  # ------------------------------------------------------------------- ticks

  def step(self) -> None:
    """One tick: the clicks, then movement, as 1.7.10's on the ground."""
    self.tick += 1
    self.click()
    forward = 0.0
    if 'key.forward' in self.keys:
      forward += 0.98
    if 'key.back' in self.keys:
      forward -= 0.98
    if 'key.sneak' in self.keys:
      forward *= 0.3
    yaw = math.radians(self.yaw)
    self.mx += -math.sin(yaw) * forward * 0.1
    self.mz += math.cos(yaw) * forward * 0.1
    self.collided = False
    if self.blocked(self.x + self.mx, self.z):
      self.collided = True
      self.mx = 0.0
    else:
      self.x += self.mx
    if self.blocked(self.x, self.z + self.mz):
      self.collided = True
      self.mz = 0.0
    else:
      self.z += self.mz
    self.mx *= FRICTION
    self.mz *= FRICTION
    self.trail.append((self.x, self.z))
    self.bumps += self.collided

  def run(self, n: int) -> None:
    for _ in range(n):
      self.step()

  # ------------------------------------------------------------------ clicks

  def click(self) -> None:
    pressed, self.pressed = self.pressed, set()
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

  # ------------------------------------------------------- what it perceives

  def target(self) -> Any:
    yaw, pitch = math.radians(self.yaw), math.radians(self.pitch)
    dx = -math.sin(yaw) * math.cos(pitch)
    dy = -math.sin(pitch)
    dz = math.cos(yaw) * math.cos(pitch)
    eye = (self.x, GROUND + EYE, self.z)
    last = tuple(math.floor(v) for v in eye)
    n = 0
    while n * 0.005 <= REACH:
      at = tuple(e + d * n * 0.005 for e, d in zip(eye, (dx, dy, dz)))
      cell = tuple(math.floor(v) for v in at)
      if cell != last and self.solid(*cell):
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
    for y in range(int(GROUND) - 1, int(GROUND) + 3):
      for x in range(fx - around, fx + around + 1):
        for z in range(fz - around, fz + around + 1):
          if not self.solid(x, y, z):
            continue
          found.append({'pos': [x, y, z], 'id': self.blockId(x, y, z),
                        'meta': 0,
                        'boxes': [[float(x), float(y), float(z),
                                   x + 1.0, y + 1.0, z + 1.0]],
                        'liquid': False, 'climbable': False})
    return found

  def perceived(self, around: int) -> dict:
    return {
      'tick': self.tick, 'pos': [self.x, GROUND, self.z],
      'eye': [self.x, GROUND + EYE, self.z],
      'box': [self.x - HALF, GROUND, self.z - HALF, self.x + HALF,
              GROUND + HEIGHT, self.z + HALF],
      'look': {'yaw': self.yaw, 'pitch': self.pitch},
      'motion': [self.mx, -0.0784000015258789, self.mz], 'on_ground': True,
      'collided': {'horizontally': self.collided, 'vertically': True},
      'in_water': False, 'in_lava': False, 'on_ladder': False,
      'sneaking': 'key.sneak' in self.keys, 'sprinting': False,
      'flying': False, 'reach': {'block': REACH, 'entity': 6.0},
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
      self.keys.add(args['key'])
      self.pressed.add(args['key'])
      return {}

    def tap(args: dict) -> dict:
      down(args)
      self.run(int(args.get('ticks', 1)))
      self.keys.discard(args['key'])
      self.step()
      return {}

    def inventory(args: dict) -> Any:
      main = list(self.hotbar) + [None] * 27
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
      'key.up': at('key.up',
                   lambda args: self.keys.discard(args['key']) or {}),
      'ticks.wait': at('ticks.wait', wait),
    }

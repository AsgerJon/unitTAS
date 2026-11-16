"""
FakePlayer: a client player on flat ground without a game, for the
agent's tests (not a test module itself). It moves as 1.7.10's does on
grass, near enough for a controller: each tick the held keys push it
along its look (0.1 a tick, 0.98 of it forward, 0.3 of that sneaking),
it moves by its motion, stopped by walls, and keeps 0.546 of it. Its
crosshair is a ray marched from the eye. Every request waits for the
end of the next tick first, as the probe runs a client step there
(Sides), so the agent meets the latency it meets in the game.

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

  # --------------------------------------------------------------- the world

  def solid(self, x: int, y: int, z: int) -> bool:
    return y < GROUND or (x, y, z) in self.walls

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
    """One tick of movement, as 1.7.10's on the ground."""
    self.tick += 1
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

    return {
      'player.perceive': at('player.perceive',
                            lambda args: self.perceived(args['around'])),
      'player.look': at('player.look', look),
      'key.down': at('key.down',
                     lambda args: self.keys.add(args['key']) or {}),
      'key.up': at('key.up',
                   lambda args: self.keys.discard(args['key']) or {}),
      'ticks.wait': at('ticks.wait', wait),
    }

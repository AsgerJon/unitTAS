"""
The port the probe's game tests run on (SPEC.md 19.7): a version and its
loader, named by the run ('on 26.3-fabric'; unittas.selftest puts it in
UNITTAS_PROBE_PORT), 1.7.10 Forge's development client without one. A
test class starts its port's game (probeGame), puts the player where its
flat test world's start is (start), says a command as that version reads
it where the versions' texts differ (command), and skips what its port
can't do yet, saying why (onlyOn).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import unittest
from typing import Callable

from fabricgame import FabricGame, buildFabric
from probegame import ROOT, results
from unittas.dev import DevGame
from unittas.game import LaunchedGame
from unittas.selftest import PORTS
from unittas.values import Block, BlockPos, Vec3

FORGE_1_7_10, FABRIC_26_3 = PORTS
#  where the reset puts the player in each port's flat test world: on its grass, at y 3 in 1.7.10 and y -61 in 26.3
STARTS = {FORGE_1_7_10: (0.5, 4.0, 0.5), FABRIC_26_3: (0.5, -60.0, 0.5)}
#  the commands whose text differs between the versions, by what they do
COMMANDS = {
  'xp 30 levels': {FORGE_1_7_10: '/xp 30L', FABRIC_26_3: '/xp add @p 30 levels'},
  'speed for 600 s, level 3': {FORGE_1_7_10: '/effect @p 1 600 2',
                               FABRIC_26_3: '/effect give @p minecraft:speed 600 2'},
  'speed for 30 s, level 2': {FORGE_1_7_10: '/effect @p 1 30 1',
                              FABRIC_26_3: '/effect give @p minecraft:speed 30 1'},
  'instant damage': {FORGE_1_7_10: '/effect @p 7 1 0',
                     FABRIC_26_3: '/effect give @p minecraft:instant_damage 1 0'},
}
#  a key's raw code, as each version numbers its keys: 1.7.10's LWJGL codes, 26.3's SDL3 scancodes
CODES = {'space': {FORGE_1_7_10: 57, FABRIC_26_3: 44}}


def _door(kind: str, half: str) -> Block:
  """26.3's door half, shut, facing south: its box along the block's north edge, as 1.7.10's meta 1 has it."""
  return Block('minecraft:' + kind, -1, state=(('facing', 'south'), ('half', half), ('hinge', 'left'),
                                               ('open', 'false'), ('powered', 'false')))


#  the blocks a scene needs whose state is the version's own (mcdex names a block, not its state), by what they are
BLOCKS = {
  #  on a block west of it: its box along its west edge
  'ladder facing east': {FORGE_1_7_10: Block('minecraft:ladder', 5),
                         FABRIC_26_3: Block('minecraft:ladder', -1,
                                            state=(('facing', 'east'), ('waterlogged', 'false')))},
  #  on a block south of it: its box along its south edge
  'ladder facing north': {FORGE_1_7_10: Block('minecraft:ladder', 2),
                          FABRIC_26_3: Block('minecraft:ladder', -1,
                                             state=(('facing', 'north'), ('waterlogged', 'false')))},
  #  a door shut across the way along z, its box along the north edge; its upper half set first (a lower half alone
  #  falls apart)
  'wooden door, lower': {FORGE_1_7_10: Block('minecraft:wooden_door', 1), FABRIC_26_3: _door('oak_door', 'lower')},
  'wooden door, upper': {FORGE_1_7_10: Block('minecraft:wooden_door', 8), FABRIC_26_3: _door('oak_door', 'upper')},
  'iron door, lower': {FORGE_1_7_10: Block('minecraft:iron_door', 1), FABRIC_26_3: _door('iron_door', 'lower')},
  'iron door, upper': {FORGE_1_7_10: Block('minecraft:iron_door', 8), FABRIC_26_3: _door('iron_door', 'upper')},
  #  a lever on the ground, off (1.7.10's meta 5, and 8 more when on)
  'lever on the ground, off': {FORGE_1_7_10: Block('minecraft:lever', 5),
                               FABRIC_26_3: Block('minecraft:lever', -1, state=(('face', 'floor'), ('facing', 'north'),
                                                                               ('powered', 'false')))},
  #  a chest with three pink wool in its first slot, facing as the game sets it (1.7.10: 3; 26.3: north); its items
  #  as each version writes them (1.7.10's numbered id and damage; 26.3's id and count)
  'chest of three pink wool': {
    FORGE_1_7_10: Block('minecraft:chest', 3, True, '{Items:[{Slot:0b,id:35s,Count:3b,Damage:6s}]}'),
    FABRIC_26_3: Block('minecraft:chest', -1, True, '{Items:[{Slot:0b,id:"minecraft:pink_wool",count:3}]}',
                       (('facing', 'north'), ('type', 'single'), ('waterlogged', 'false')))},
  #  a gate shut across the way along z
  'fence gate': {FORGE_1_7_10: Block('minecraft:fence_gate', 0),
                 FABRIC_26_3: Block('minecraft:oak_fence_gate', -1, state=(('facing', 'south'), ('in_wall', 'false'),
                                                                          ('open', 'false'), ('powered', 'false')))},
}


def port() -> str:
  """The run's port: UNITTAS_PROBE_PORT, 1.7.10 Forge without it."""
  named = os.environ.get('UNITTAS_PROBE_PORT') or FORGE_1_7_10
  if named not in PORTS:
    raise ValueError('UNITTAS_PROBE_PORT is %r: the ports are %s' % (named, ', '.join(PORTS)))
  return named


def start() -> tuple:
  """Where the reset puts the player in the port's flat test world."""
  return STARTS[port()]


def command(what: str) -> str:
  """The command that does 'what', as the port's version reads it."""
  return COMMANDS[what][port()]


def block(what: str) -> Block:
  """A scene's block whose state is the version's own, as the port's version has it."""
  return BLOCKS[what][port()]


def lift(y: float) -> float:
  """
  A height in 1.7.10's flat test world (its start's feet at y 4), as the port's: moved by the difference between
  their starts (26.3's feet are at y -60), so a test written in 1.7.10's places runs on any port.
  """
  return y - 4.0 + start()[1]


def at(x: int, y: int, z: int) -> BlockPos:
  """A block's place written in 1.7.10's flat world, on the port's."""
  return BlockPos(x, int(lift(y)), z)


def point(x: float, y: float, z: float) -> Vec3:
  """A point written in 1.7.10's flat world, on the port's."""
  return Vec3(x, lift(y), z)


def code(key: str) -> int:
  """A key's raw code, as the port's version numbers it."""
  return CODES[key][port()]


def onlyOn(*ports: str, why: str) -> Callable:
  """A test (or class) run on those ports only; on another it skips, saying why."""
  return unittest.skipUnless(port() in ports, 'not on %s: %s' % (port(), why))


def probeGame(name: str) -> LaunchedGame:
  """The port's game for a test class, its output in '<results>/<name>/'."""
  if port() == FABRIC_26_3:
    return FabricGame(results(), buildFabric(os.path.join(results(), 'fabric-build', 'build.log')), name)
  return DevGame(ROOT, results(), name)

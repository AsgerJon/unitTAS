"""
The port the probe's game tests run on (SPEC.md 19.7): a version and what
runs it, named by the run ('on 26.3-fabric', 'on 26.3'; unittas.selftest puts
it in UNITTAS_PROBE_PORT), 1.7.10 Forge's development client without one. A
test class starts its port's game (probeGame: 26.3, 1.21.1 or 1.20.1 as
Mojang ships it, the probe a Java agent; or beside Fabric or NeoForge), puts
the player where its flat test world's start is (start), says a command as
that version reads it where the versions' texts differ (command), and skips
what its version can't do yet, saying why (onlyOn). The tables are by version
(V1_7_10, V1_20_1, V1_21_1, V26_3): each version's ports share its own, and
1.21.1 has 26.3's block states and command texts (the same from 1.13 and
1.20.5 on) but for its own keys' codes (GLFW's, not SDL3's); 1.20.1 has
1.21.1's but for its items' data in a block entity (NBT, before 1.20.5's
components: Count, a byte).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import unittest
from typing import Callable

from agentgame import AgentGame, buildAgent
from fabricgame import FabricGame
from neoforgegame import NeoForgeGame
from probegame import ROOT, results
from unittas.dev import DevGame
from unittas.game import LaunchedGame
from unittas.selftest import PORTS
from unittas.values import Block, BlockPos, Item, Vec3

(FORGE_1_7_10, FABRIC_26_3, VANILLA_26_3, VANILLA_1_21_1, FABRIC_1_21_1, VANILLA_1_20_1, FABRIC_1_20_1,
 NEOFORGE_1_21_1) = PORTS
#  the versions, which the tables are by
V1_7_10, V1_20_1, V1_21_1, V26_3 = '1.7.10', '1.20.1', '1.21.1', '26.3'
VERSIONS = {FORGE_1_7_10: V1_7_10, FABRIC_26_3: V26_3, VANILLA_26_3: V26_3, VANILLA_1_21_1: V1_21_1,
            FABRIC_1_21_1: V1_21_1, VANILLA_1_20_1: V1_20_1, FABRIC_1_20_1: V1_20_1, NEOFORGE_1_21_1: V1_21_1}
#  the ports with Fabric Loader beside the probe, and with NeoForge
FABRIC_PORTS = (FABRIC_26_3, FABRIC_1_21_1, FABRIC_1_20_1)
NEOFORGE_PORTS = (NEOFORGE_1_21_1,)
#  the versions whose items keep their data as NBT (data components from 1.20.5 on)
NBT_ITEMS = (V1_7_10, V1_20_1)
#  where the reset puts the player in each version's flat test world: on its grass, at y 3 in 1.7.10 and y -61 from
#  1.18 on (the world's bottom at y -64)
STARTS = {V1_7_10: (0.5, 4.0, 0.5), V1_20_1: (0.5, -60.0, 0.5), V1_21_1: (0.5, -60.0, 0.5),
          V26_3: (0.5, -60.0, 0.5)}
#  the commands whose text differs between the versions, by what they do
COMMANDS = {
  'xp 30 levels': {V1_7_10: '/xp 30L', V26_3: '/xp add @p 30 levels'},
  'speed for 600 s, level 3': {V1_7_10: '/effect @p 1 600 2',
                               V26_3: '/effect give @p minecraft:speed 600 2'},
  'speed for 30 s, level 2': {V1_7_10: '/effect @p 1 30 1',
                              V26_3: '/effect give @p minecraft:speed 30 1'},
  'instant damage': {V1_7_10: '/effect @p 7 1 0',
                     V26_3: '/effect give @p minecraft:instant_damage 1 0'},
}
#  a key's raw code, as each version numbers its keys: 1.7.10's LWJGL codes, 26.3's SDL3 scancodes
CODES = {'space': {V1_7_10: 57, V1_20_1: 32, V1_21_1: 32, V26_3: 44}}


def _door(kind: str, half: str) -> Block:
  """26.3's door half, shut, facing south: its box along the block's north edge, as 1.7.10's meta 1 has it."""
  return Block('minecraft:' + kind, -1, state=(('facing', 'south'), ('half', half), ('hinge', 'left'),
                                               ('open', 'false'), ('powered', 'false')))


#  the blocks a scene needs whose state is the version's own (mcdex names a block, not its state), by what they are
BLOCKS = {
  #  on a block west of it: its box along its west edge
  'ladder facing east': {V1_7_10: Block('minecraft:ladder', 5),
                         V26_3: Block('minecraft:ladder', -1,
                                            state=(('facing', 'east'), ('waterlogged', 'false')))},
  #  on a block south of it: its box along its south edge
  'ladder facing north': {V1_7_10: Block('minecraft:ladder', 2),
                          V26_3: Block('minecraft:ladder', -1,
                                             state=(('facing', 'north'), ('waterlogged', 'false')))},
  #  a door shut across the way along z, its box along the north edge; its upper half set first (a lower half alone
  #  falls apart)
  'wooden door, lower': {V1_7_10: Block('minecraft:wooden_door', 1), V26_3: _door('oak_door', 'lower')},
  'wooden door, upper': {V1_7_10: Block('minecraft:wooden_door', 8), V26_3: _door('oak_door', 'upper')},
  'iron door, lower': {V1_7_10: Block('minecraft:iron_door', 1), V26_3: _door('iron_door', 'lower')},
  'iron door, upper': {V1_7_10: Block('minecraft:iron_door', 8), V26_3: _door('iron_door', 'upper')},
  #  a lever on the ground, off (1.7.10's meta 5, and 8 more when on)
  'lever on the ground, off': {V1_7_10: Block('minecraft:lever', 5),
                               V26_3: Block('minecraft:lever', -1, state=(('face', 'floor'), ('facing', 'north'),
                                                                               ('powered', 'false')))},
  #  a chest with three pink wool in its first slot, facing as the game sets it (1.7.10: 3; 26.3: north); its items
  #  as each version writes them (1.7.10's numbered id and damage; 26.3's id and count)
  'chest of three pink wool': {
    V1_7_10: Block('minecraft:chest', 3, True, '{Items:[{Slot:0b,id:35s,Count:3b,Damage:6s}]}'),
    V26_3: Block('minecraft:chest', -1, True, '{Items:[{Slot:0b,id:"minecraft:pink_wool",count:3}]}',
                       (('facing', 'north'), ('type', 'single'), ('waterlogged', 'false')))},
  #  the model scenario's (modelsuite.py): a chest facing south (1.7.10 sets a chest's facing itself as it is added: 3),
  #  a hopper pointing west into the block west of it, a lever on the ground and on, a chest of one pink wool
  'chest facing south': {V1_7_10: Block('minecraft:chest', 3),
                         V26_3: Block('minecraft:chest', -1, state=(('facing', 'south'), ('type', 'single'),
                                                                          ('waterlogged', 'false')))},
  'hopper pointing west': {V1_7_10: Block('minecraft:hopper', 4),
                           V26_3: Block('minecraft:hopper', -1, state=(('enabled', 'true'), ('facing', 'west')))},
  'lever on the ground, on': {V1_7_10: Block('minecraft:lever', 13),
                              V26_3: Block('minecraft:lever', -1, state=(('face', 'floor'), ('facing', 'north'),
                                                                              ('powered', 'true')))},
  'chest of one pink wool': {
    V1_7_10: Block('minecraft:chest', 3, True, '{Items:[{Slot:0b,id:35s,Count:1b,Damage:6s}]}'),
    V26_3: Block('minecraft:chest', -1, True, '{Items:[{Slot:0b,id:"minecraft:pink_wool",count:1}]}',
                       (('facing', 'south'), ('type', 'single'), ('waterlogged', 'false')))},
  #  a furnace facing south: 1.7.10 sets a furnace's facing itself as it is added, south with nothing around (meta 3)
  'furnace facing south': {V1_7_10: Block('minecraft:furnace', 3),
                           V26_3: Block('minecraft:furnace', -1, state=(('facing', 'south'), ('lit', 'false')))},
  #  a gate shut across the way along z
  'fence gate': {V1_7_10: Block('minecraft:fence_gate', 0),
                 V26_3: Block('minecraft:oak_fence_gate', -1, state=(('facing', 'south'), ('in_wall', 'false'),
                                                                          ('open', 'false'), ('powered', 'false')))},
}


#  1.21.1's block states and command texts are 26.3's: the same from 1.13 (states) and 1.20.5 (commands, items' data)
for _table in (COMMANDS, BLOCKS):
  for _entry in _table.values():
    _entry[V1_21_1] = _entry[V26_3]
    _entry[V1_20_1] = _entry[V26_3]
#  but 1.20.1's items in a block entity are NBT: an id and Count, a byte (count, an int, from 1.20.5)
BLOCKS['chest of three pink wool'][V1_20_1] = Block(
  'minecraft:chest', -1, True, '{Items:[{Slot:0b,id:"minecraft:pink_wool",Count:3b}]}',
  (('facing', 'north'), ('type', 'single'), ('waterlogged', 'false')))
BLOCKS['chest of one pink wool'][V1_20_1] = Block(
  'minecraft:chest', -1, True, '{Items:[{Slot:0b,id:"minecraft:pink_wool",Count:1b}]}',
  (('facing', 'south'), ('type', 'single'), ('waterlogged', 'false')))


def port() -> str:
  """The run's port: UNITTAS_PROBE_PORT, 1.7.10 Forge without it."""
  named = os.environ.get('UNITTAS_PROBE_PORT') or FORGE_1_7_10
  if named not in PORTS:
    raise ValueError('UNITTAS_PROBE_PORT is %r: the ports are %s' % (named, ', '.join(PORTS)))
  return named


def version() -> str:
  """The run's port's version: what the tables are by."""
  return VERSIONS[port()]


def fabricVersion() -> str:
  """The version test_fabric's Fabric game is: the port's on a Fabric port, 26.3 on any other."""
  return version() if port() in FABRIC_PORTS else V26_3


def start() -> tuple:
  """Where the reset puts the player in the port's flat test world."""
  return STARTS[version()]


def command(what: str) -> str:
  """The command that does 'what', as the port's version reads it."""
  return COMMANDS[what][version()]


def block(what: str) -> Block:
  """A scene's block whose state is the version's own, as the port's version has it."""
  return BLOCKS[what][version()]


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
  return CODES[key][version()]


def damageable(item: Item) -> Item:
  """
  A new damageable item (boots, a sword) as the port's game makes it: 1.20.1 writes an item's damage into its NBT as
  it makes it, a new one's too ({Damage:0}); 1.7.10 keeps damage in the meta, and a 1.20.5 stack lists only a damage
  taken among its components.
  """
  return item.replace(snbt='{Damage:0}') if version() == V1_20_1 else item


def neoForgeVersion() -> str:
  """The version test_neoforge's NeoForge game is: the port's on a NeoForge port, 1.21.1 on any other."""
  return version() if port() in NEOFORGE_PORTS else V1_21_1


def onlyOn(*versions: str, why: str) -> Callable:
  """A test (or class) run on those versions' ports only; on another it skips, saying why."""
  return unittest.skipUnless(version() in versions, 'not on %s: %s' % (port(), why))


def probeGame(name: str) -> LaunchedGame:
  """The port's game for a test class, its output in '<results>/<name>/'."""
  if port() == FABRIC_26_3:
    return FabricGame(results(), buildAgent(os.path.join(results(), 'agent-build', 'build.log')), name)
  if port() == VANILLA_26_3:
    return AgentGame(results(), buildAgent(os.path.join(results(), 'agent-build', 'build.log')), name)
  if port() == VANILLA_1_21_1:
    return AgentGame(results(), buildAgent(os.path.join(results(), 'agent-build', 'build.log'), V1_21_1), name,
                     minecraft=V1_21_1)
  if port() == FABRIC_1_21_1:
    return FabricGame(results(), buildAgent(os.path.join(results(), 'agent-build', 'build.log'), V1_21_1), name,
                      minecraft=V1_21_1)
  if port() == NEOFORGE_1_21_1:
    return NeoForgeGame(results(), buildAgent(os.path.join(results(), 'agent-build', 'build.log'), V1_21_1), name,
                        minecraft=V1_21_1)
  if port() == VANILLA_1_20_1:
    return AgentGame(results(), buildAgent(os.path.join(results(), 'agent-build', 'build.log'), V1_20_1), name,
                     minecraft=V1_20_1)
  if port() == FABRIC_1_20_1:
    return FabricGame(results(), buildAgent(os.path.join(results(), 'agent-build', 'build.log'), V1_20_1), name,
                      minecraft=V1_20_1)
  return DevGame(ROOT, results(), name)

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

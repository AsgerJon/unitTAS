"""
The test across versions (SPEC.md 12.3 step 9, 19.7 steps 4 and 6f): one scene played on 1.7.10 Forge's development
client and on real vanilla clients of 26.3, 1.21.1 and 1.20.1 (the probe a Java agent; 1.21.1 and 1.20.1 obfuscated),
one game after the other, never two at once. On each, red wool and then blue wool placed by their mcdex members a step
from the world's start and read back, each read recorded with the members its version reads it as; the game stopped
before the next starts. The reads differ as the versions do (1.7.10's minecraft:wool with meta 14, the flattened
versions' minecraft:red_wool with no meta); compared through a small helper, by their recorded members, red wool is
the same thing on every pair of versions, and red and blue wool are not. The model for record and compare (SPEC.md
16).

  python -m unittas.selftest test_crossversion.      (through the watcher: "probe test_crossversion.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import itertools
import os
import shutil
import unittest
from typing import Any

from mcdex import MCBlocks

from agentgame import AgentGame, buildAgent
from ports import STARTS, V1_7_10, V1_20_1, V1_21_1, V26_3
from probegame import READY_SECONDS, ROOT, results
from unittas.api import Game
from unittas.dev import DevGame
from unittas.reset import reset
from unittas.values import Vec3

#  what the scene places, by its name in the record
PLACED = {'red wool': MCBlocks.RedWool, 'blue wool': MCBlocks.BlueWool}
#  the versions played, in their order: 1.7.10's development client, then each agent version's vanilla client
PLAYED = (V1_7_10, V26_3, V1_21_1, V1_20_1)


def sameThing(first: tuple, second: tuple) -> frozenset:
  """
  What two versions' recorded reads have in common: each read is (the value as its game reported it, the mcdex
  members its version reads it as); the members both are. Empty when they are different things, however alike their
  values look.
  """
  return frozenset(first[1]) & frozenset(second[1])


def played(version: str, launched: Any) -> dict:
  """
  The scene on one version's game, the game stopped after: its version as its hello said it, and each placed block's
  read (its value, its members), recorded.
  """
  record = {}
  shutil.rmtree(os.path.join(launched.gameDir, 'saves', 'unittas'), ignore_errors=True)
  connection = launched.start(READY_SECONDS)
  try:
    connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    connection.request('world.create', {}, timeout=240)
    connection.request('world.prepare')
    reset(connection, at=STARTS[version])
    game = Game(connection)
    record['minecraft'] = connection.hello.minecraft
    pos = Vec3(*STARTS[version]).block().offset(2, 0, 2)
    for name, member in PLACED.items():
      game.setBlock(pos, member)
      value = game.block(pos)
      record[name] = (value, game.membersOf(value))
      game.setBlock(pos, MCBlocks.Air)
  finally:
    launched.stop()
  return record


class CrossVersionTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    log = os.path.join(results(), 'agent-build', 'build.log')
    cls.records = {V1_7_10: played(V1_7_10, DevGame(ROOT, results(), 'cross-1.7.10'))}
    for version in PLAYED[1:]:
      cls.records[version] = played(version, AgentGame(results(), buildAgent(log, version), 'cross-' + version,
                                                       minecraft=version))

  def test_every_version_played(self) -> None:
    self.assertEqual(PLAYED, tuple(self.records[version]['minecraft'] for version in PLAYED))

  def test_red_wool_on_each(self) -> None:
    # read as each version keeps it: not alike as values
    old = self.records[V1_7_10]['red wool']
    self.assertEqual(('minecraft:wool', 14), (old[0].id, old[0].meta))
    for version in PLAYED[1:]:
      with self.subTest(version=version):
        new = self.records[version]['red wool']
        self.assertEqual(('minecraft:red_wool', -1), (new[0].id, new[0].meta))
    # the same thing all the same, on every pair
    for first, second in itertools.combinations(PLAYED, 2):
      with self.subTest(first=first, second=second):
        self.assertEqual({MCBlocks.RedWool},
                         sameThing(self.records[first]['red wool'], self.records[second]['red wool']))

  def test_different_things_are_told_apart(self) -> None:
    for first, second in itertools.permutations(PLAYED, 2):
      with self.subTest(red=first, blue=second):
        self.assertEqual(frozenset(),
                         sameThing(self.records[first]['red wool'], self.records[second]['blue wool']))


if __name__ == '__main__':
  unittest.main()

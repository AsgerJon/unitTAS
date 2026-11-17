"""
The first test across two versions (SPEC.md 12.3 step 9, 19.7 step 4): one scene played on 1.7.10 Forge's development
client and on a real vanilla 26.3 client (the probe a Java agent), one game after the other, never two at once. On
each, red wool and then blue wool placed by their mcdex members a step from the world's start and read back, each read
recorded with the members its version reads it as; the game stopped before the next starts. The reads differ as the
versions do (1.7.10's minecraft:wool with meta 14, 26.3's minecraft:red_wool with no meta); compared through a small
helper, by their recorded members, red wool is the same thing on both, and red and blue wool are not. The model for
record and compare (SPEC.md 16).

  python -m unittas.selftest test_crossversion.      (through the watcher: "probe test_crossversion.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest
from typing import Any

from mcdex import MCBlocks

from agentgame import AgentGame, buildAgent
from ports import STARTS, V1_7_10, V26_3
from probegame import READY_SECONDS, ROOT, results
from unittas.api import Game
from unittas.dev import DevGame
from unittas.reset import reset
from unittas.values import Vec3

#  what the scene places, by its name in the record
PLACED = {'red wool': MCBlocks.RedWool, 'blue wool': MCBlocks.BlueWool}


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
    cls.records = {
      V1_7_10: played(V1_7_10, DevGame(ROOT, results(), 'cross-1.7.10')),
      V26_3: played(V26_3, AgentGame(results(), buildAgent(os.path.join(results(), 'agent-build', 'build.log')),
                                     'cross-26.3')),
    }

  def test_both_versions_played(self) -> None:
    self.assertEqual(('1.7.10', '26.3'), (self.records[V1_7_10]['minecraft'], self.records[V26_3]['minecraft']))

  def test_red_wool_on_both(self) -> None:
    old, new = self.records[V1_7_10]['red wool'], self.records[V26_3]['red wool']
    # read as each version keeps it: not alike as values
    self.assertEqual(('minecraft:wool', 14), (old[0].id, old[0].meta))
    self.assertEqual(('minecraft:red_wool', -1), (new[0].id, new[0].meta))
    # the same thing all the same
    self.assertEqual({MCBlocks.RedWool}, sameThing(old, new))

  def test_different_things_are_told_apart(self) -> None:
    self.assertEqual(frozenset(), sameThing(self.records[V1_7_10]['red wool'], self.records[V26_3]['blue wool']))


if __name__ == '__main__':
  unittest.main()

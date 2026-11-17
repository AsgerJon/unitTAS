"""
The first test on two versions at once (SPEC.md 12.3 step 9, 19.7 step 4): one class with two games, 1.7.10 Forge's
development client and a real vanilla 26.3 client (the probe a Java agent), both up together, and one scene on both:
red wool placed by its mcdex member, a step from each world's start, and read back. The reads differ as the versions do (1.7.10's
minecraft:wool with meta 14, 26.3's minecraft:red_wool with no meta); compared through a small helper, by the mcdex
members each version reads its block as, they are the same thing. The model for record and compare (SPEC.md 16).
Two games at once: asked for before it is run.

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


def sameThing(first: tuple, second: tuple) -> frozenset:
  """
  What two versions' reads have in common: each read is (game, value), the value as its game reported it; the mcdex
  members both read it as. Empty when the two are different things, however alike their values look.
  """
  (firstGame, firstValue), (secondGame, secondValue) = first, second
  return firstGame.membersOf(firstValue) & secondGame.membersOf(secondValue)


class CrossVersionTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = {}
    cls.games = {}
    for port, launched in ((V1_7_10, lambda: DevGame(ROOT, results(), 'cross-1.7.10')),
                           (V26_3, lambda: AgentGame(results(), buildAgent(
                             os.path.join(results(), 'agent-build', 'build.log')), 'cross-26.3'))):
      game = launched()
      cls.launched[port] = game
      shutil.rmtree(os.path.join(game.gameDir, 'saves', 'unittas'), ignore_errors=True)
      connection = game.start(READY_SECONDS)
      connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
      connection.request('world.create', {}, timeout=240)
      connection.request('world.prepare')
      cls.games[port] = Game(connection)

  @classmethod
  def tearDownClass(cls) -> None:
    for launched in cls.launched.values():
      launched.stop()

  def setUp(self) -> None:
    for port, game in self.games.items():
      reset(game.connection, at=STARTS[port])

  def placed(self, port: str, member: Any) -> Any:
    """The member placed two blocks east and south of the port's start, and its block read back there."""
    game = self.games[port]
    pos = Vec3(*STARTS[port]).block().offset(2, 0, 2)
    game.setBlock(pos, member)
    try:
      return game.block(pos)
    finally:
      game.setBlock(pos, MCBlocks.Air)

  def test_both_games_are_up(self) -> None:
    self.assertEqual(('1.7.10', '26.3'), (self.games[V1_7_10].connection.hello.minecraft,
                                          self.games[V26_3].connection.hello.minecraft))

  def test_red_wool_on_both(self) -> None:
    old = self.placed(V1_7_10, MCBlocks.RedWool)
    new = self.placed(V26_3, MCBlocks.RedWool)
    # read as each version keeps it: not alike as values
    self.assertEqual(('minecraft:wool', 14), (old.id, old.meta))
    self.assertEqual(('minecraft:red_wool', -1), (new.id, new.meta))
    # the same thing all the same
    self.assertEqual({MCBlocks.RedWool}, sameThing((self.games[V1_7_10], old), (self.games[V26_3], new)))

  def test_different_things_are_told_apart(self) -> None:
    old = self.placed(V1_7_10, MCBlocks.RedWool)
    new = self.placed(V26_3, MCBlocks.BlueWool)
    self.assertEqual(frozenset(), sameThing((self.games[V1_7_10], old), (self.games[V26_3], new)))


if __name__ == '__main__':
  unittest.main()

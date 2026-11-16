"""
The agent and containers on the run's port (SPEC.md 15.6 step 4, 19.7),
on flat ground, by a player's means alone: a chest opened by using it,
its screen read as it shows the chest; a stack taken and one put by
shift-clicks (container.click), the chest then read by command as the
server holds it (block.items); the screen closed as Esc does; a block
that isn't a container, a TesttimeError. Things by mcdex member, places
written as in 1.7.10's flat world and moved to the port's (ports.at).

  python -m unittas.selftest test_containers.
  (through the watcher: "probe test_containers.",
  "probe test_containers on 26.3-fabric")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from mcdex import MCBlocks, MCItems

from ports import at, block, probeGame, start
from probegame import READY_SECONDS
from unittas.agent import Agent
from unittas.api import Game
from unittas.errors import TesttimeError
from unittas.reset import reset

CHEST = at(3, 4, 5)


class ContainerTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = probeGame('containers')
    shutil.rmtree(os.path.join(cls.launched.gameDir, 'saves', 'unittas'),
                  ignore_errors=True)
    connection = cls.launched.start(READY_SECONDS)
    connection.events.waitFor(
      lambda event: event.get('event') == 'ready', READY_SECONDS)
    cls.game = Game(connection)
    cls.game.request('world.create', {}, timeout=240)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.launched.stop()

  def setUp(self) -> None:
    reset(self.game.connection, at=start())
    self.game.setBlock(CHEST, block('chest of three pink wool'))
    self.agent = Agent(self.game)

  def tearDown(self) -> None:
    self.game.setBlock(CHEST, MCBlocks.Air)

  def chestItems(self) -> list:
    """The chest's stacks as the server holds them, by command (block.items)."""
    return [each for each in self.game.items(CHEST) if not each.empty]

  def assertStack(self, member, count: int, stack) -> None:
    self.assertIn(member, self.game.membersOf(stack))
    self.assertEqual(count, stack.count)

  def test_a_opens_a_chest(self) -> None:
    shown = self.agent.open(CHEST)
    self.assertFalse(shown.playerOwn)
    self.assertEqual(27, len(shown.contents))
    self.assertStack(MCItems.PinkWool, 3, shown.contents[0])
    self.assertTrue(self.game.screen().container)

  def test_b_takes_a_stack(self) -> None:
    self.agent.open(CHEST)
    taken = self.agent.take(MCItems.PinkWool)
    self.assertStack(MCItems.PinkWool, 3, taken)
    self.assertEqual([], self.chestItems())
    self.assertIn(taken, self.game.inventory().main)

  def test_c_puts_a_stack(self) -> None:
    self.game.setSlot('main.2', MCItems.Stone, 16)
    self.agent.open(CHEST)
    put = self.agent.put(MCItems.Stone)
    self.assertStack(MCItems.Stone, 16, put)
    self.agent.close()
    stone = [each for each in self.chestItems() if MCItems.Stone in self.game.membersOf(each)]
    self.assertEqual(1, len(stone), self.chestItems())
    self.assertEqual(16, stone[0].count)
    self.assertTrue(self.game.slot('main.2').empty)

  def test_d_closes_it(self) -> None:
    self.agent.open(CHEST)
    self.agent.close()
    self.assertIsNone(self.game.screen())
    self.assertTrue(self.game.container().playerOwn)

  def test_e_a_block_that_isn_t_one(self) -> None:
    self.game.setBlock(at(3, 4, 7), MCBlocks.Stone)
    try:
      with self.assertRaises(TesttimeError) as raised:
        self.agent.open(at(3, 4, 7))
      self.assertIn('opened no container', str(raised.exception))
    finally:
      self.game.setBlock(at(3, 4, 7), MCBlocks.Air)


if __name__ == '__main__':
  unittest.main()

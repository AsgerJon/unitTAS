"""
The agent's verbs on the run's port (SPEC.md 15.6 step 3, 19.7), on
flat ground, by a player's keys and look alone: using a lever, on and off
again; breaking a block in creative, and nothing behind it; mining one
in survival; placing a block from its hotbar slot, and where the agent
stands (it steps aside); an item not in the hotbar, a TesttimeError. The
world's state is read by command, as an examination is by default: a
lever's on by its meta (1.7.10) or its state (26.3). Places written as in
1.7.10's flat world and moved to the port's (ports.at).

  python -m unittas.selftest test_verbs.
  (through the watcher: "probe test_verbs.", "probe test_verbs on 26.3-fabric")
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
from unittas.values import BlockPos


class VerbTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = probeGame('verbs')
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
    self.agent = Agent(self.game)
    self.placed = []

  def tearDown(self) -> None:
    for pos in reversed(self.placed):
      self.game.setBlock(pos, MCBlocks.Air)

  def place(self, pos: tuple, block) -> None:
    """The block at pos, written in 1.7.10's flat world, on the port's."""
    pos = at(*pos)
    self.game.setBlock(pos, block)
    self.placed.append(pos)

  def isOn(self, pos: BlockPos) -> bool:
    """A lever's on, by command: 1.7.10's meta bit 8, 26.3's state."""
    there = self.game.block(pos)
    if there.state:
      return there.properties['powered'] == 'true'
    return bool(there.meta & 8)

  def test_a_uses_a_lever(self) -> None:
    self.place((5, 4, 7), block('lever on the ground, off'))
    self.agent.use(at(5, 4, 7))
    self.assertTrue(self.isOn(at(5, 4, 7)), 'on')
    self.agent.use(at(5, 4, 7))
    self.assertFalse(self.isOn(at(5, 4, 7)), 'off again')

  def test_b_breaks_a_block_in_creative(self) -> None:
    self.place((3, 4, 6), MCBlocks.Stone)
    self.agent.breakBlock(at(3, 4, 6))
    self.assertEqual('minecraft:air', self.game.block(at(3, 4, 6)).id)
    #  let go in time: nothing behind it broken. The grass it covered may have turned to dirt meanwhile, as covered
    #  grass does on a random tick (the game's own chance, a few in a hundred here): either is still there
    self.game.ticks(10)
    under = self.game.membersOf(self.game.block(at(3, 3, 6)))
    self.assertTrue({MCBlocks.GrassBlock, MCBlocks.Dirt} & under, under)

  def test_c_mines_a_block_in_survival(self) -> None:
    self.game.command('/gamemode survival')
    self.place((3, 4, 6), MCBlocks.Dirt)
    before = self.agent.perceive().tick
    seen = self.agent.breakBlock(at(3, 4, 6))
    self.assertEqual('minecraft:air', self.game.block(at(3, 4, 6)).id)
    #  dirt by hand: 15 ticks of mining
    self.assertGreaterEqual(seen.tick - before, 15)

  def test_d_places_a_block_from_its_slot(self) -> None:
    self.game.setSlot('main.3', MCItems.Stone, 16)
    self.placed.append(at(4, 4, 6))
    self.agent.place(at(4, 4, 6), MCItems.Stone)
    self.assertEqual({MCBlocks.Stone}, self.game.membersOf(self.game.block(at(4, 4, 6))))
    self.assertEqual(3, self.game.inventory(side='client').selected)

  def test_e_places_where_it_stands(self) -> None:
    self.game.setSlot('main.0', MCItems.Stone, 16)
    self.placed.append(at(0, 4, 0))
    self.agent.place(at(0, 4, 0), MCItems.Stone)
    self.assertEqual('minecraft:stone', self.game.block(at(0, 4, 0)).id)

  def test_f_not_in_the_hotbar(self) -> None:
    with self.assertRaises(TesttimeError) as raised:
      self.agent.place(at(4, 4, 6), MCItems.Stone)
    self.assertIn('no MCItems.Stone in the hotbar', str(raised.exception))


if __name__ == '__main__':
  unittest.main()

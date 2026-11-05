"""
Step 5 of phase 3 (SPEC.md section 9.3): the game's API (unittas.api.Game) in the development client, a sample of each
helper: a command and its chat, the player, the inventory, blocks, entities, screens, ticks, and reflection by readable
names. One launch, in a world of its own; each test starts from a reset.

  python -m unittas.selftest test_api.      (through the watcher: "probe test_api.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from probegame import READY_SECONDS, ROOT, results
from unittas.api import Game
from unittas.dev import DevGame
from unittas.errors import NotFound
from unittas.launcher import Sources
from unittas.mappings import Mappings
from unittas.reset import reset
from unittas.values import Block, BlockPos, Item, Look, Vec3


class ApiTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = DevGame(ROOT, results(), 'api')
    shutil.rmtree(os.path.join(cls.launched.gameDir, 'saves', 'unittas'), ignore_errors=True)
    connection = cls.launched.start()
    connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    cls.game = Game(connection, mappings=Mappings.load(Sources(gradleHome=os.path.join(ROOT, '.gradle-home'))))
    cls.game.request('world.create', {}, timeout=240)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.launched.stop()

  def setUp(self) -> None:
    reset(self.game.connection)
    self.mark = self.game.mark()

  def test_a_command_and_its_chat(self) -> None:
    said = self.game.command('/give @p wool 1 14')
    self.assertEqual(1, said.result)
    self.assertTrue(any('Red Wool' in line for line in said.lines), said)
    self.assertTrue(any('Red Wool' in line.plain for line in self.game.chat(self.mark)))
    self.assertEqual(Item('minecraft:wool', 1, 14), self.game.held())

  def test_the_player(self) -> None:
    self.game.teleport(Vec3(5.5, 4, 5.5), look=Look(90, 0))
    player = self.game.player()
    self.assertEqual(Vec3(5.5, 4.0, 5.5), player.pos)
    self.assertEqual('creative', player.gameMode)
    self.game.look(45, 10)
    self.assertEqual(Look(45, 10), self.game.player(side='client').look)

  def test_the_inventory(self) -> None:
    self.game.setSlot('armor.feet', Item('minecraft:leather_boots', 1, 0))
    self.assertEqual(Item('minecraft:leather_boots', 1, 0), self.game.inventory().feet)
    self.assertIs(Item.EMPTY, self.game.slot('main.12'))

  def test_blocks(self) -> None:
    self.game.setBlock(BlockPos(3, 4, 3), 'minecraft:gold_block')
    self.assertEqual(Block('minecraft:gold_block', 0), self.game.block((3, 4, 3)))
    self.game.setBlock((5, 4, 3), Block('minecraft:chest', 0))
    self.assertEqual('Chest', self.game.block((5, 4, 3), tile=True).tile['id'])

  def test_entities(self) -> None:
    pig = self.game.spawn('Pig', (4.5, 4, 4.5))
    self.assertEqual(pig.entity, self.game.entity(pig).entity)
    self.assertEqual((pig.entity,), tuple(each.entity for each in self.game.entities(type='Pig')))
    self.game.remove(pig)
    self.game.ticks(2, side='server')
    self.assertEqual((), self.game.entities(type='Pig'))
    with self.assertRaises(NotFound):
      self.game.entity(pig)

  def test_screens_and_ticks(self) -> None:
    self.game.openScreen('inventory')
    self.assertTrue(self.game.screen().container)
    self.game.closeScreen()
    self.assertIsNone(self.game.screen())
    before = self.game.ticks(1)
    #  ticks pass between two requests, so at least 5 later, not exactly
    self.assertGreaterEqual(self.game.ticks(5), before + 5)

  def test_reflection_by_readable_names(self) -> None:
    self.assertEqual(0, self.game.reflect(['inventory', 'currentItem']))
    self.game.reflectSet(['inventory', 'currentItem'], 2)
    self.assertEqual(2, self.game.reflect(['inventory', 'currentItem']))
    self.assertEqual(20.0, self.game.reflect([{'call': 'getHealth'}], side='client'))


if __name__ == '__main__':
  unittest.main()

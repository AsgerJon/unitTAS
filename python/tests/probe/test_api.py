"""
Step 5 of phase 3 (SPEC.md section 9.3), on the run's port (19.7 step 9): the game's API (unittas.api.Game), a sample
of each helper: a command and its chat, the player, the inventory, blocks, entities, screens, ticks, and reflection by
readable names (1.7.10's MCP names translated by the orchestrator's mappings, Mojang's by the probe). Things by mcdex
member, places from the port's start. One launch, in a world of its own; each test starts from a reset.

  python -m unittas.selftest test_api.      (through the watcher: "probe test_api.", "probe test_api. on 1.21.1")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from mcdex import MCBlocks, MCEntities, MCItems

from ports import V1_7_10, at, damageable, point, probeGame, start, version
from probegame import READY_SECONDS, ROOT
from unittas.api import Game
from unittas.errors import NotFound
from unittas.launcher import Sources
from unittas.mappings import Mappings
from unittas.reset import reset
from unittas.things import itemOf
from unittas.values import Block, Look

#  three red wool's command, and the player's selected slot by its readable names, as each version has them
GIVE = {V1_7_10: '/give @p wool 1 14'}
SELECTED = {V1_7_10: ['inventory', 'currentItem']}


def give() -> str:
  """One red wool, as the port's version's /give takes it."""
  return GIVE.get(version(), '/give @p minecraft:red_wool 1')


def selected() -> list:
  """The selected slot's path from the player, by the version's readable names (Mojang's from 1.13 on)."""
  return SELECTED.get(version(), ['inventory', 'selected'])


class ApiTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = probeGame('api')
    shutil.rmtree(os.path.join(cls.launched.gameDir, 'saves', 'unittas'), ignore_errors=True)
    connection = cls.launched.start(READY_SECONDS)
    connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    if version() == V1_7_10:
      cls.game = Game(connection, mappings=Mappings.load(Sources(gradleHome=os.path.join(ROOT, '.gradle-home'))))
    else:
      cls.game = Game(connection)
    cls.game.request('world.create', {}, timeout=240)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.launched.stop()

  def setUp(self) -> None:
    reset(self.game.connection, at=start())
    self.mark = self.game.mark()

  def test_a_command_and_its_chat(self) -> None:
    said = self.game.command(give())
    self.assertEqual(1, said.result)
    self.assertTrue(any('Red Wool' in line for line in said.lines), said)
    self.assertTrue(any('Red Wool' in line.plain for line in self.game.chat(self.mark)))
    self.assertEqual(itemOf(MCItems.RedWool, self.game.version, 1), self.game.held())

  def test_the_player(self) -> None:
    self.game.teleport(point(5.5, 4, 5.5), look=Look(90, 0))
    player = self.game.player()
    self.assertEqual(point(5.5, 4.0, 5.5), player.pos)
    self.assertEqual('creative', player.gameMode)
    self.game.look(45, 10)
    self.assertEqual(Look(45, 10), self.game.player(side='client').look)

  def test_the_inventory(self) -> None:
    boots = itemOf(MCItems.LeatherBoots, self.game.version)
    self.game.setSlot('armor.feet', boots)
    self.assertEqual(damageable(boots), self.game.inventory().feet)
    self.assertTrue(self.game.slot('main.12').empty)

  def test_blocks(self) -> None:
    self.game.setBlock(at(3, 4, 3), MCBlocks.GoldBlock)
    self.assertIn(MCBlocks.GoldBlock, self.game.membersOf(self.game.block(at(3, 4, 3))))
    #  meta 3: 1.7.10 sets a chest's facing itself as it is added
    self.game.setBlock(at(5, 4, 3), Block('minecraft:chest', 3) if version() == V1_7_10 else MCBlocks.Chest)
    chest = self.game.block(at(5, 4, 3), tile=True)
    self.assertIsNotNone(chest.tile, 'a chest has its block entity')
    if version() == V1_7_10:
      self.assertEqual('Chest', chest.tile['id'])

  def test_entities(self) -> None:
    pig = self.game.spawn(MCEntities.Pig, point(4.5, 4, 4.5))
    self.assertEqual(pig.entity, self.game.entity(pig).entity)
    self.assertEqual((pig.entity,), tuple(each.entity for each in self.game.entities(type=MCEntities.Pig)))
    self.game.remove(pig)
    self.game.ticks(2, side='server')
    self.assertEqual((), self.game.entities(type=MCEntities.Pig))
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
    self.assertEqual(0, self.game.reflect(selected()))
    self.game.reflectSet(selected(), 2)
    self.assertEqual(2, self.game.reflect(selected()))
    self.assertEqual(20.0, self.game.reflect([{'call': 'getHealth'}], side='client'))


if __name__ == '__main__':
  unittest.main()

"""
The reset (SPEC.md 8.3 step 5b), on the run's port (19.7): the player dirtied in every way README's "What tests
share" names that a command or the probe reaches, the reset run, and each part read back; then from the End; twice;
its parts alone; none without a world. Things by mcdex member, places from the port's start, the commands whose text
differs as the version reads them (ports.py); the off hand where the version has one. One launch, in a world of its
own.

  python -m unittas.selftest test_reset      (through the watcher: "probe test_reset",
                                              "probe test_reset on 26.3-fabric")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from mcdex import MCDimensions, MCEntities, MCItems

from ports import command, probeGame, start
from probegame import READY_SECONDS
from unittas.api import Game
from unittas.errors import NotReady
from unittas.reset import reset
from unittas.values import Item, Look, Vec3


class ResetTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = probeGame('reset')
    shutil.rmtree(os.path.join(cls.launched.gameDir, 'saves', 'unittas'), ignore_errors=True)
    cls.connection = cls.launched.start(READY_SECONDS)
    cls.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    cls.connection.request('world.create', {}, timeout=240)
    # the steady world, as a run's: a flat world spawns slimes by itself, and one that came between a reset and its
    # check failed test_01 once (2026-11-05)
    cls.connection.request('world.prepare')
    cls.game = Game(cls.connection)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.launched.stop()

  def request(self, op, args=None, side=None, timeout=60.0):
    return self.connection.request(op, args, side=side, timeout=timeout)

  def command(self, text: str) -> None:
    said = self.game.command(text)
    self.assertEqual((), tuple(said.errors), (text, said))

  def reset(self) -> None:
    reset(self.connection, at=start())

  def members(self, radius: float = 64) -> set:
    """The mcdex members of the entities near the player."""
    found = set()
    for entity in self.game.entities(radius=radius):
      found |= self.game.membersOf(entity)
    return found

  def test_01_everything_put_back(self) -> None:
    #  from the start, as every test is: the flat world's own spawn can be far from 0, 0 (1.7.10's near x -1560),
    #  and a mob summoned into a chunk that isn't loaded is quietly never added
    self.reset()
    here = Vec3(*start())
    # dirtied: survival, experience, items (the off hand too, where there is one), an effect, hurt, moved and
    # turned, rain, Hard, mobs, a container open
    self.command('/gamemode survival')
    self.command(command('xp 30 levels'))
    self.game.setSlot('main.0', MCItems.RedWool, 3)
    self.game.setSlot('main.1', MCItems.Diamond, 5)
    offhand = self.game.inventory().hasOffhand
    if offhand:
      self.game.setSlot('offhand', MCItems.Shield)
    self.command(command('speed for 600 s, level 3'))
    self.command(command('instant damage'))
    self.command('/weather rain')
    self.command('/difficulty hard')
    self.game.spawn(MCEntities.Zombie, here.offset(4.5, 0, 4.5))
    self.game.spawn(MCEntities.Pig, here.offset(2.5, 0, 2.5))
    #  it falls at once: not verified by its place (the reset's is, below)
    self.game.teleport(here.offset(20, 6, 20), look=Look(45.0, 30.0), verify=False)
    self.game.openScreen('inventory')
    dirty = self.game.player()
    self.assertEqual('survival', dirty.gameMode)
    self.assertLess(dirty.health, dirty.maxHealth, 'instant damage hurt it')
    self.assertTrue(dirty.effects)
    self.assertLessEqual({MCEntities.Zombie, MCEntities.Pig}, self.members())

    self.reset()

    player = self.game.player()
    self.assertEqual('creative', player.gameMode)
    self.assertEqual((0, 0), (player.xpLevel, player.xpTotal))
    self.assertEqual((), player.effects)
    self.assertEqual(here, player.pos)
    self.assertEqual(Look(0.0, 0.0), player.look)
    self.assertEqual(player.maxHealth, player.health)
    self.assertEqual(20, player.food)
    self.assertFalse(player.flying)
    self.assertEqual((0, 0.0, -1, 0), (player.fireTicks, player.fallDistance, player.riding, player.arrows))
    inventory = self.game.inventory()
    self.assertEqual((Item.EMPTY,) * 36, inventory.main)
    self.assertEqual((Item.EMPTY,) * 4, (inventory.feet, inventory.legs, inventory.chest, inventory.head))
    self.assertEqual(offhand, inventory.hasOffhand)
    self.assertIs(Item.EMPTY, inventory.offhand)
    self.assertEqual(0, inventory.selected)
    world = self.request('world.get')
    self.assertEqual((False, False), (world['raining'], world['thundering']))
    self.assertEqual('easy', world['difficulty'])
    self.assertEqual((), self.game.entities(radius=64))
    self.assertIsNone(self.game.screen())
    self.assertTrue(self.request('container.get', side='client')['player_own'])
    client = self.game.player(side='client')
    self.assertEqual('minecraft:overworld', client.dimension)
    self.assertAlmostEqual(here.x, client.pos.x, places=3)
    self.assertEqual((Item.EMPTY,) * 36, self.game.inventory(side='client').main, 'the client has the slots too')

  def test_02_from_the_end(self) -> None:
    self.game.teleport((0.5, 70.0, 0.5), dimension=MCDimensions.TheEnd, timeout=120)
    self.assertEqual('minecraft:the_end', self.game.player().dimension)
    self.reset()
    #  a new player entity (1.7.10 gives it the old one's id): the "player" handle reaches it all the same
    player = self.game.player()
    self.assertEqual('minecraft:overworld', player.dimension)
    self.assertEqual(Vec3(*start()), player.pos)
    self.assertEqual('minecraft:overworld', self.game.player(side='client').dimension)
    self.assertEqual('world', self.request('status')['state'])

  def test_03_twice_is_once(self) -> None:
    self.reset()
    self.reset()
    self.assertEqual(Vec3(*start()), self.game.player().pos)

  def test_04_the_parts_alone(self) -> None:
    self.assertEqual({'respawned': False}, self.request('player.reset', {'at': list(start())}))
    self.assertEqual({}, self.request('world.reset'))
    self.assertEqual({}, self.request('client.reset'))

  def test_05_no_world_no_reset(self) -> None:
    self.request('world.close', timeout=240)
    with self.assertRaises(NotReady):
      self.request('client.reset')
    with self.assertRaises(NotReady):
      self.request('player.reset', {'at': list(start())})

  def test_06_quit(self) -> None:
    self.assertEqual({}, self.request('quit', {'reason': 'test_06'}))
    self.assertTrue(self.launched.ended(120))


if __name__ == '__main__':
  unittest.main()

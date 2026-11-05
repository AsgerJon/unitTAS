"""
Step 5b of phase 2 (SPEC.md section 8.3): the reset, three operations in today's order (unittas.reset). The player is
dirtied in every way README's "What tests share" names that a command can reach, the reset runs, and each item is read
back. Then the End: the player there, and the reset brings it back. One launch, in a world of its own.

  python -m unittas.selftest reset      (through the watcher: "probe reset")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from probegame import READY_SECONDS, ROOT, results
from unittas.dev import DevGame
from unittas.errors import NotReady
from unittas.reset import reset


class ResetTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.game = DevGame(ROOT, results(), 'reset')
    shutil.rmtree(os.path.join(cls.game.gameDir, 'saves', 'unittas'), ignore_errors=True)
    cls.connection = cls.game.start()
    cls.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    cls.connection.request('world.create', {}, timeout=240)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop()

  def request(self, op, args=None, side=None, timeout=60.0):
    return self.connection.request(op, args, side=side, timeout=timeout)

  def command(self, text: str) -> None:
    said = self.request('command.run', {'command': text})
    self.assertEqual([], said['errors'], (text, said))

  def test_01_everything_put_back(self) -> None:
    #  from the start, as every test is: the flat world's own spawn is far from 0, 0 (here near x -1560), and a mob
    #  summoned into a chunk that isn't loaded is quietly never added, the command's success line notwithstanding
    reset(self.connection)
    # dirtied: survival, experience, items, an effect, hurt, moved and turned, rain, Hard, mobs, a container open
    self.command('/gamemode 0')
    self.command('/xp 30L')
    self.command('/give @p wool 3 14')
    self.command('/give @p diamond 5')
    self.command('/effect @p 1 600 2')
    self.command('/effect @p 7 1 0')
    self.command('/weather rain')
    self.command('/difficulty 3')
    self.command('/summon Zombie 5 4 5')
    self.command('/summon Pig 3 4 3')
    self.request('player.teleport', {'pos': [20.5, 10.0, 20.5], 'look': {'yaw': 45.0, 'pitch': 30.0}})
    self.request('screen.open', {'screen': 'inventory'})
    dirty = self.request('player.get')
    self.assertEqual('survival', dirty['game_mode'])
    self.assertLess(dirty['health'], dirty['max_health'], 'instant damage hurt it')
    self.assertTrue(dirty['effects'])
    types = [each['type'] for each in self.request('entity.list', {'near': {'pos': 'player', 'radius': 64}})]
    self.assertIn('Zombie', types)
    self.assertIn('Pig', types)

    reset(self.connection)

    player = self.request('player.get')
    self.assertEqual('creative', player['game_mode'])
    self.assertEqual(0, player['xp']['level'])
    self.assertEqual(0, player['xp']['total'])
    self.assertEqual([], player['effects'])
    self.assertEqual([0.5, 4.0, 0.5], player['pos'])
    self.assertEqual({'yaw': 0.0, 'pitch': 0.0}, player['look'])
    self.assertEqual(player['max_health'], player['health'])
    self.assertEqual(20, player['food'])
    self.assertFalse(player['flying'])
    self.assertEqual(0, player['fire_ticks'])
    self.assertEqual(0.0, player['fall_distance'])
    self.assertIsNone(player['riding'])
    self.assertEqual(0, player['arrows'])
    inventory = self.request('inventory.get')
    self.assertEqual([None] * 36, inventory['main'])
    self.assertEqual({'feet': None, 'legs': None, 'chest': None, 'head': None}, inventory['armor'])
    self.assertEqual(0, inventory['selected'])
    world = self.request('world.get')
    self.assertEqual((False, False), (world['raining'], world['thundering']))
    self.assertEqual('easy', world['difficulty'])
    self.assertEqual([], self.request('entity.list', {'near': {'pos': 'player', 'radius': 64}}))
    self.assertIsNone(self.request('screen.get'))
    self.assertTrue(self.request('container.get', side='client')['player_own'])
    client = self.request('player.get', side='client')
    self.assertEqual('minecraft:overworld', client['dimension'])
    self.assertAlmostEqual(0.5, client['pos'][0], places=3)
    self.assertEqual([None] * 36, self.request('inventory.get', side='client')['main'], 'the client has the slots too')

  def test_02_from_the_end(self) -> None:
    self.request('player.teleport', {'dimension': 'minecraft:the_end', 'pos': [0.5, 70.0, 0.5]}, timeout=120)
    self.assertEqual('minecraft:the_end', self.request('player.get')['dimension'])
    reset(self.connection)
    #  a new player entity (1.7.10 gives it the old one's id): the "player" handle reaches it all the same
    player = self.request('player.get')
    self.assertEqual('minecraft:overworld', player['dimension'])
    self.assertEqual([0.5, 4.0, 0.5], player['pos'])
    self.assertEqual('minecraft:overworld', self.request('player.get', side='client')['dimension'])
    self.assertEqual('world', self.request('status')['state'])

  def test_03_twice_is_once(self) -> None:
    reset(self.connection)
    reset(self.connection)
    self.assertEqual([0.5, 4.0, 0.5], self.request('player.get')['pos'])

  def test_04_the_parts_alone(self) -> None:
    self.assertEqual({'respawned': False}, self.request('player.reset'))
    self.assertEqual({}, self.request('world.reset'))
    self.assertEqual({}, self.request('client.reset'))

  def test_05_no_world_no_reset(self) -> None:
    self.request('world.close', timeout=240)
    with self.assertRaises(NotReady):
      self.request('client.reset')
    with self.assertRaises(NotReady):
      self.request('player.reset')

  def test_06_quit(self) -> None:
    self.assertEqual({}, self.request('quit', {'reason': 'test_06'}))
    self.assertTrue(self.game.ended(120))


if __name__ == '__main__':
  unittest.main()

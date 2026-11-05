"""
Step 5a of phase 2 (SPEC.md section 8.3, reordered): the operations the reset's tests need. command.run and the chat
events; player.get on both sides; player.teleport, within a dimension and to the End and back; inventory.get,
container.get and entity.list; screen.open and screen.close (the creative inventory's container, EFR's case);
hooks.run with unitTAS's own SelfPlugin. One launch, in a world of its own, its tests in order.

  python -m unittas.selftest player      (through the watcher: "probe player")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from probegame import READY_SECONDS, ROOT, results
from unittas.dev import DevGame
from unittas.errors import BadRequest

WOOL = {'id': 'minecraft:wool', 'count': 3, 'meta': 14}


class PlayerTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.game = DevGame(ROOT, results(), 'player')
    shutil.rmtree(os.path.join(cls.game.gameDir, 'saves', 'unittas'), ignore_errors=True)
    cls.connection = cls.game.start()
    cls.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    cls.connection.request('world.create', {}, timeout=240)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop()

  def request(self, op, args=None, side=None, timeout=60.0):
    return self.connection.request(op, args, side=side, timeout=timeout)

  def clientHolds(self, op, args, test, ticks=60):
    found = self.request('wait.until', {'side': 'client', 'op': op, 'args': args, 'test': test, 'max_ticks': ticks})
    self.assertTrue(found['held'], 'the client never saw it: %r' % (found,))
    return found['value']

  def test_01_command_run(self) -> None:
    mark = self.connection.events.mark()
    said = self.request('command.run', {'command': '/time set 6000'})
    self.assertEqual(1, said['result'])
    self.assertTrue(any('6000' in line for line in said['lines']), said)
    self.assertEqual([], said['errors'])
    chat = [event['plain'] for event in self.connection.events.since(mark) if event.get('event') == 'chat']
    self.assertEqual(said['lines'], chat, 'the lines are the chat events that came')

  def test_02_a_command_that_fails(self) -> None:
    said = self.request('command.run', {'command': '/wobble'})
    self.assertEqual(0, said['result'])
    self.assertTrue(said['errors'], 'an unknown command answers in red')
    with self.assertRaises(BadRequest):
      self.request('command.run', {})

  def test_03_a_command_in_a_batch(self) -> None:
    entries = self.request('batch', {'ops': [
      {'op': 'command.run', 'args': {'command': '/time set 1000', 'settle_ticks': 0}},
      {'op': 'world.get'},
    ]}, side='server')
    self.assertEqual({'result': 1, 'lines': [], 'errors': []}, entries[0]['value'])
    self.assertEqual(1000, entries[1]['value']['day_time'], 'read in the same tick, after the command')
    #  its answer still reaches the chat a tick or two later: let it land before the next test's command
    self.request('ticks.wait', {'side': 'client', 'n': 5})

  def test_04_as_the_server(self) -> None:
    said = self.request('command.run', {'command': '/time set 6000', 'as': 'server'})
    self.assertEqual(1, said['result'])
    #  the console's own answer goes to the log; operators (the player, with cheats) see the grey notice of it
    self.assertTrue(said['lines'], said)
    self.assertTrue(all(line.startswith('[Server') for line in said['lines']), said)

  def test_05_the_player_on_both_sides(self) -> None:
    server = self.request('player.get')
    client = self.request('player.get', side='client')
    self.assertEqual(server['entity'], client['entity'], 'the same entity id on both sides')
    self.assertEqual(server['name'], client['name'])
    self.assertEqual('creative', server['game_mode'])
    self.assertEqual('minecraft:overworld', server['dimension'])
    self.assertEqual(20.0, server['health'])
    for field in ('pos', 'look', 'motion', 'food', 'saturation', 'xp', 'on_ground', 'flying', 'may_fly', 'effects',
                  'fire_ticks', 'air', 'fall_distance', 'riding', 'arrows'):
      self.assertIn(field, server)
    self.assertEqual(3, len(server['pos']))

  def test_06_teleport_within_the_dimension(self) -> None:
    self.request('player.teleport', {'pos': [5.5, 4.0, 5.5], 'look': {'yaw': 90.0, 'pitch': 0.0}})
    server = self.request('player.get')
    self.assertEqual([5.5, 4.0, 5.5], server['pos'])
    self.assertEqual(90.0, server['look']['yaw'])
    self.clientHolds('player.get', {}, {'path': ['pos', 0], 'eq': 5.5})

  def test_07_inventory(self) -> None:
    self.request('command.run', {'command': '/give @p wool 3 14'})
    inventory = self.request('inventory.get')
    self.assertEqual(36, len(inventory['main']))
    self.assertIn(WOOL, inventory['main'])
    self.assertEqual(0, inventory['selected'])
    self.assertEqual(WOOL, self.request('inventory.get', {'slot': 'held'}))
    self.assertEqual({'feet', 'legs', 'chest', 'head'}, set(inventory['armor']))
    self.clientHolds('inventory.get', {'slot': 'held'}, {'path': ['id'], 'eq': 'minecraft:wool'})
    with self.assertRaises(BadRequest):
      self.request('inventory.get', {'slot': 'main.99'})

  def test_08_entities(self) -> None:
    self.request('command.run', {'command': '/summon Zombie 8 4 8'})
    near = {'near': {'pos': 'player', 'radius': 16}}
    zombies = self.request('entity.list', dict(near, type='Zombie'))
    self.assertEqual(1, len(zombies), zombies)
    zombie = zombies[0]
    self.assertEqual('Zombie', zombie['type'])
    self.assertTrue(zombie['class'].endswith('EntityZombie'))
    self.assertGreater(zombie['health'], 0)
    self.assertTrue(zombie['alive'])
    monsters = self.request('entity.list', dict(near, **{'class': 'net.minecraft.entity.monster.IMob'}))
    self.assertEqual([zombie['entity']], [each['entity'] for each in monsters])
    self.assertEqual([], [each for each in self.request('entity.list', near) if each['type'] == 'Player'])
    players = self.request('entity.list', dict(near, players=True))
    self.assertIn(self.request('player.get')['entity'], [each['entity'] for each in players])
    seen = self.clientHolds('entity.list', dict(near, type='Zombie'), {'len': {'eq': 1}})
    self.assertEqual(zombie['entity'], seen[0]['entity'], 'the client knows it by the same id')

  def test_09_the_creative_inventory_s_container(self) -> None:
    self.request('screen.open', {'screen': 'creative'})
    self.assertTrue(self.request('screen.get')['class'].endswith('GuiContainerCreative'))
    self.assertFalse(self.request('container.get', side='client')['player_own'], "creative's grid is a container of its own")
    self.request('screen.close')
    self.assertIsNone(self.request('screen.get'))
    self.assertTrue(self.request('container.get', side='client')['player_own'], 'closed as Esc closes it')

  def test_10_the_other_screens(self) -> None:
    #  in creative the game opens its creative inventory for the player's: the survival one needs survival
    self.request('command.run', {'command': '/gamemode 0'})
    self.request('screen.open', {'screen': 'inventory'})
    self.assertTrue(self.request('screen.get')['class'].endswith('GuiInventory'))
    self.assertTrue(self.request('container.get', side='client')['player_own'])
    self.request('screen.close')
    self.request('command.run', {'command': '/gamemode 1'})
    self.request('screen.open', {'screen': 'chat', 'text': '/'})
    self.assertTrue(self.request('screen.get')['chat'])
    self.request('screen.close')
    self.request('screen.open', {'screen': 'pause'})
    self.assertTrue(self.request('screen.get')['pauses'])
    self.request('screen.close')
    self.assertIsNone(self.request('screen.get'))
    with self.assertRaises(BadRequest):
      self.request('screen.open', {'screen': 'wobble'})

  def test_11_hooks(self) -> None:
    ran = self.request('hooks.run', {'hook': 'setUpWorld'})
    names = [plugin['class'] for plugin in ran['plugins']]
    self.assertTrue(any(name.endswith('SelfPlugin') for name in names), ran)
    self.assertTrue(all(plugin['ok'] for plugin in ran['plugins']), ran)
    self.assertTrue(self.request('hooks.run', {'hook': 'beforeRun'})['plugins'], 'a client hook goes to the client')
    with self.assertRaises(BadRequest):
      self.request('hooks.run', {'hook': 'wobble'})
    with self.assertRaises(BadRequest):
      self.request('hooks.run', {'hook': 'beforeRun'}, side='server')

  def test_12_to_the_end_and_back(self) -> None:
    self.request('player.teleport', {'dimension': 'minecraft:the_end', 'pos': [0.5, 70.0, 0.5]}, timeout=120)
    self.assertEqual('minecraft:the_end', self.request('player.get')['dimension'])
    self.assertEqual('minecraft:the_end', self.request('player.get', side='client')['dimension'])
    self.assertEqual('minecraft:the_end', self.request('status')['world']['dimension'])
    self.request('player.teleport', {'dimension': 'minecraft:overworld', 'pos': [0.5, 4.0, 0.5]}, timeout=120)
    self.assertEqual('minecraft:overworld', self.request('player.get', side='client')['dimension'])
    entries = self.request('batch', {'ops': [{'op': 'player.teleport', 'args': {'dimension': 'minecraft:the_end'}}]},
                           side='server')
    self.assertEqual('BadRequest', entries[0]['error']['type'], 'another dimension waits for the client: not in a batch')
    self.assertEqual('minecraft:overworld', self.request('player.get')['dimension'])

  def test_13_quit(self) -> None:
    self.assertEqual({}, self.request('quit', {'reason': 'test_13'}))
    self.assertTrue(self.game.ended(120))


if __name__ == '__main__':
  unittest.main()

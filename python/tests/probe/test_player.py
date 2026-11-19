"""
Step 5a of phase 2 (SPEC.md section 8.3, reordered), on the run's port (19.7 step 9): the operations the reset's tests
need. command.run and the chat events; player.get on both sides; player.teleport, within a dimension and to the End
and back; inventory.get, container.get and entity.list; screen.open and screen.close (the creative inventory's
container, EFR's case); hooks.run (with unitTAS's own SelfPlugin in 1.7.10's development client). One launch, in a
world of its own, its tests in order. Each version's own texts and names by the tables below and ports' (a command,
an entity's type and class, a screen's class), its places from its start.

  python -m unittas.selftest player      (through the watcher: "probe player", "probe player on 1.21.1")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from ports import V1_7_10, V1_16_1, V1_20_1, V1_21_1, V26_3, at, command, lift, onlyOn, probeGame, version
from probegame import GONE_SECONDS, READY_SECONDS
from unittas.errors import BadRequest

#  three red wool, as inventory.get reads them: 1.7.10's by its meta, a block's own id from 1.13 on
WOOL = {V1_7_10: {'id': 'minecraft:wool', 'count': 3, 'meta': 14}, V1_20_1: {'id': 'minecraft:red_wool', 'count': 3},
        V1_21_1: {'id': 'minecraft:red_wool', 'count': 3}, V26_3: {'id': 'minecraft:red_wool', 'count': 3},
        V1_16_1: {'id': 'minecraft:red_wool', 'count': 3}}
#  a zombie's type and class, the monsters' type, and the player's type, as entity.list names them
MODERN_ENTITIES = ('minecraft:zombie', 'net.minecraft.world.entity.monster.Zombie',
                   'net.minecraft.world.entity.monster.Enemy', 'minecraft:player')
ENTITIES = {V1_7_10: ('Zombie', 'net.minecraft.entity.monster.EntityZombie', 'net.minecraft.entity.monster.IMob',
                      'Player'),
            V1_16_1: MODERN_ENTITIES, V1_20_1: MODERN_ENTITIES, V1_21_1: MODERN_ENTITIES,
            V26_3: ('minecraft:zombie', 'net.minecraft.world.entity.monster.zombie.Zombie',
                    'net.minecraft.world.entity.monster.Enemy', 'minecraft:player')}
#  the creative inventory's and the survival inventory's classes
MODERN_SCREENS = ('net.minecraft.client.gui.screens.inventory.CreativeModeInventoryScreen',
                  'net.minecraft.client.gui.screens.inventory.InventoryScreen')
SCREENS = {V1_7_10: ('net.minecraft.client.gui.inventory.GuiContainerCreative',
                     'net.minecraft.client.gui.inventory.GuiInventory'),
           V1_16_1: MODERN_SCREENS, V1_20_1: MODERN_SCREENS, V1_21_1: MODERN_SCREENS, V26_3: MODERN_SCREENS}


def timeSet(time: int) -> int:
  """
  /time set's own number (command.run's result): 1.7.10's commands count their runs (1); from 1.13 on a command
  returns its own value, the time it set.
  """
  return 1 if version() == V1_7_10 else time


class PlayerTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.game = probeGame('player')
    shutil.rmtree(os.path.join(cls.game.gameDir, 'saves', 'unittas'), ignore_errors=True)
    cls.connection = cls.game.start(READY_SECONDS)
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
    self.assertEqual(timeSet(6000), said['result'])
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
    ran = entries[0]['value']
    self.assertEqual((timeSet(1000), []), (ran['result'], ran['errors']))
    if version() == V1_7_10:
      self.assertEqual([], ran['lines'], "1.7.10's lines are the chat's, which comes a tick or two later")
    else:
      self.assertTrue(any('1000' in line for line in ran['lines']), "from 1.13 on its lines are what it said back to"
                      " its source, at once: %r" % (ran,))
    self.assertEqual(1000, entries[1]['value']['day_time'], 'read in the same tick, after the command')
    #  its answer still reaches the chat a tick or two later: let it land before the next test's command
    self.request('ticks.wait', {'side': 'client', 'n': 5})

  def test_04_as_the_server(self) -> None:
    said = self.request('command.run', {'command': '/time set 6000', 'as': 'server'})
    self.assertEqual(timeSet(6000), said['result'])
    self.assertTrue(said['lines'], said)
    if version() == V1_7_10:
      #  the console's own answer goes to the log; operators (the player, with cheats) see the grey notice of it
      self.assertTrue(all(line.startswith('[Server') for line in said['lines']), said)
    else:
      #  from 1.13 on its lines are the console's own answer, as it said it back to its source
      self.assertTrue(any('6000' in line for line in said['lines']), said)

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
    self.request('player.teleport', {'pos': [5.5, lift(4.0), 5.5], 'look': {'yaw': 90.0, 'pitch': 0.0}})
    server = self.request('player.get')
    self.assertEqual([5.5, lift(4.0), 5.5], server['pos'])
    self.assertEqual(90.0, server['look']['yaw'])
    self.clientHolds('player.get', {}, {'path': ['pos', 0], 'eq': 5.5})

  def test_07_inventory(self) -> None:
    wool = WOOL[version()]
    self.request('command.run', {'command': command('three red wool')})
    inventory = self.request('inventory.get')
    self.assertEqual(36, len(inventory['main']))
    self.assertIn(wool, inventory['main'])
    self.assertEqual(0, inventory['selected'])
    self.assertEqual(wool, self.request('inventory.get', {'slot': 'held'}))
    self.assertEqual({'feet', 'legs', 'chest', 'head'}, set(inventory['armor']))
    self.clientHolds('inventory.get', {'slot': 'held'}, {'path': ['id'], 'eq': wool['id']})
    with self.assertRaises(BadRequest):
      self.request('inventory.get', {'slot': 'main.99'})

  def test_08_entities(self) -> None:
    kind, named, monster, player = ENTITIES[version()]
    place = at(8, 4, 8)
    self.request('command.run', {'command': '/summon %s %d %d %d' % (kind, place.x, place.y, place.z)})
    near = {'near': {'pos': 'player', 'radius': 16}}
    zombies = self.request('entity.list', dict(near, type=kind))
    self.assertEqual(1, len(zombies), zombies)
    zombie = zombies[0]
    self.assertEqual(kind, zombie['type'])
    self.assertEqual(named, zombie['class'])
    self.assertGreater(zombie['health'], 0)
    self.assertTrue(zombie['alive'])
    monsters = self.request('entity.list', dict(near, **{'class': monster}))
    self.assertEqual([zombie['entity']], [each['entity'] for each in monsters])
    self.assertEqual([], [each for each in self.request('entity.list', near) if each['type'] == player])
    players = self.request('entity.list', dict(near, players=True))
    self.assertIn(self.request('player.get')['entity'], [each['entity'] for each in players])
    seen = self.clientHolds('entity.list', dict(near, type=kind), {'len': {'eq': 1}})
    self.assertEqual(zombie['entity'], seen[0]['entity'], 'the client knows it by the same id')

  def test_09_the_creative_inventory_s_container(self) -> None:
    self.request('screen.open', {'screen': 'creative'})
    self.assertEqual(SCREENS[version()][0], self.request('screen.get')['class'])
    self.assertFalse(self.request('container.get', side='client')['player_own'], "creative's grid is a container of its own")
    self.request('screen.close')
    self.assertIsNone(self.request('screen.get'))
    self.assertTrue(self.request('container.get', side='client')['player_own'], 'closed as Esc closes it')

  def test_10_the_other_screens(self) -> None:
    #  in creative the game opens its creative inventory for the player's: the survival one needs survival
    self.request('command.run', {'command': command('survival')})
    self.request('screen.open', {'screen': 'inventory'})
    self.assertEqual(SCREENS[version()][1], self.request('screen.get')['class'])
    self.assertTrue(self.request('container.get', side='client')['player_own'])
    self.request('screen.close')
    self.request('command.run', {'command': command('creative')})
    self.request('screen.open', {'screen': 'chat', 'text': '/'})
    self.assertTrue(self.request('screen.get')['chat'])
    self.request('screen.close')
    self.request('screen.open', {'screen': 'pause'})
    self.assertTrue(self.request('screen.get')['pauses'])
    self.request('screen.close')
    self.assertIsNone(self.request('screen.get'))
    with self.assertRaises(BadRequest):
      self.request('screen.open', {'screen': 'wobble'})

  @onlyOn(V1_7_10, why="unitTAS's own SelfPlugin is in 1.7.10's development client; a modern game has none of its")
  def test_11_hooks(self) -> None:
    ran = self.request('hooks.run', {'hook': 'setUpWorld'})
    names = [plugin['class'] for plugin in ran['plugins']]
    self.assertTrue(any(name.endswith('SelfPlugin') for name in names), ran)
    self.assertTrue(all(plugin['ok'] for plugin in ran['plugins']), ran)
    self.assertTrue(self.request('hooks.run', {'hook': 'beforeRun'})['plugins'], 'a client hook goes to the client')

  def test_11b_hooks_refused(self) -> None:
    with self.assertRaises(BadRequest):
      self.request('hooks.run', {'hook': 'wobble'})
    with self.assertRaises(BadRequest):
      self.request('hooks.run', {'hook': 'beforeRun'}, side='server')

  def test_12_to_the_end_and_back(self) -> None:
    self.request('player.teleport', {'dimension': 'minecraft:the_end', 'pos': [0.5, 70.0, 0.5]}, timeout=120)
    self.assertEqual('minecraft:the_end', self.request('player.get')['dimension'])
    self.assertEqual('minecraft:the_end', self.request('player.get', side='client')['dimension'])
    self.assertEqual('minecraft:the_end', self.request('status')['world']['dimension'])
    self.request('player.teleport', {'dimension': 'minecraft:overworld', 'pos': [0.5, lift(4.0), 0.5]},
                 timeout=120)
    self.assertEqual('minecraft:overworld', self.request('player.get', side='client')['dimension'])
    entries = self.request('batch', {'ops': [{'op': 'player.teleport', 'args': {'dimension': 'minecraft:the_end'}}]},
                           side='server')
    self.assertEqual('BadRequest', entries[0]['error']['type'], 'another dimension waits for the client: not in a batch')
    self.assertEqual('minecraft:overworld', self.request('player.get')['dimension'])

  def test_13_quit(self) -> None:
    self.assertEqual({}, self.request('quit', {'reason': 'test_13'}))
    self.assertTrue(self.game.ended(GONE_SECONDS))


if __name__ == '__main__':
  unittest.main()

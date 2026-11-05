"""
Step 6 of phase 2 (SPEC.md section 8.3): the game's things. player.look, inventory.set, block.get and .set,
entity.spawn, .get and .remove, the keys, typing into a screen, chat.send and chat.read (ChatTests' twin), camera.set,
sound.play (MixinTests' twin, with the sound events), screenshot, and the screen events. One launch, in a world of its
own; each test starts from a reset, as every test does.

  python -m unittas.selftest game      (through the watcher: "probe game")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import struct
import unittest

from probegame import READY_SECONDS, ROOT, results
from unittas.dev import DevGame
from unittas.errors import BadRequest, NotFound, NotReady
from unittas.reset import reset


class GameTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.game = DevGame(ROOT, results(), 'game')
    shutil.rmtree(os.path.join(cls.game.gameDir, 'saves', 'unittas'), ignore_errors=True)
    cls.connection = cls.game.start()
    cls.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    cls.connection.request('world.create', {}, timeout=240)
    cls.connection.request('world.rules.set', {'rules': {'doDaylightCycle': False, 'doMobSpawning': False}})

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop()

  def setUp(self) -> None:
    reset(self.connection)
    self.mark = self.connection.events.mark()

  def request(self, op, args=None, side=None, timeout=60.0):
    return self.connection.request(op, args, side=side, timeout=timeout)

  def clientHolds(self, op, args, test, ticks=60):
    found = self.request('wait.until', {'side': 'client', 'op': op, 'args': args, 'test': test, 'max_ticks': ticks})
    self.assertTrue(found['held'], 'the client never saw it: %r' % (found,))
    return found['value']

  def events(self, kind):
    return [event for event in self.connection.events.since(self.mark) if event.get('event') == kind]

  def test_01_look(self) -> None:
    self.request('player.look', {'yaw': 90.0, 'pitch': 30.0})
    self.assertEqual({'yaw': 90.0, 'pitch': 30.0}, self.request('player.get', side='client')['look'])
    found = self.request('wait.until', {'side': 'server', 'op': 'player.get', 'max_ticks': 40,
                                        'test': {'path': ['look', 'yaw'], 'eq': 90.0}})
    self.assertTrue(found['held'], 'the server learns the look from the client, as from a mouse')

  def test_02_inventory_set(self) -> None:
    self.request('inventory.set', {'slot': 'held', 'item': {'id': 'minecraft:diamond', 'count': 2}})
    self.assertEqual({'id': 'minecraft:diamond', 'count': 2, 'meta': 0}, self.request('inventory.get', {'slot': 'held'}))
    self.clientHolds('inventory.get', {'slot': 'held'}, {'path': ['id'], 'eq': 'minecraft:diamond'})
    self.request('inventory.set', {'items': {'main.3': {'id': 'minecraft:wool', 'meta': 14},
                                             'armor.feet': {'id': 'minecraft:leather_boots'}}})
    inventory = self.request('inventory.get')
    self.assertEqual({'id': 'minecraft:wool', 'count': 1, 'meta': 14}, inventory['main'][3])
    self.assertEqual('minecraft:leather_boots', inventory['armor']['feet']['id'])
    self.clientHolds('inventory.get', {}, {'path': ['armor', 'feet', 'id'], 'eq': 'minecraft:leather_boots'})
    self.request('inventory.set', {'slot': 'held', 'item': None})
    self.assertIsNone(self.request('inventory.get', {'slot': 'held'}))
    with self.assertRaises(NotFound):
      self.request('inventory.set', {'slot': 'held', 'item': {'id': 'minecraft:wobble'}})
    with self.assertRaises(BadRequest):
      self.request('inventory.set', {'slot': 'main.99', 'item': {'id': 'minecraft:stone'}})

  def test_03_blocks(self) -> None:
    self.assertEqual({'id': 'minecraft:grass', 'meta': 0}, self.request('block.get', {'pos': [0, 3, 0]}))
    self.assertEqual({'id': 'minecraft:air', 'meta': 0}, self.request('block.get', {'pos': [3, 4, 3]}))
    self.request('block.set', {'pos': [3, 4, 3], 'block': {'id': 'minecraft:wool', 'meta': 14}})
    self.assertEqual({'id': 'minecraft:wool', 'meta': 14}, self.request('block.get', {'pos': [3, 4, 3]}))
    self.clientHolds('block.get', {'pos': [3, 4, 3]}, {'path': ['id'], 'eq': 'minecraft:wool'})
    self.request('block.set', {'pos': [3, 4, 3], 'block': {'id': 'minecraft:air'}})
    with self.assertRaises(NotFound):
      self.request('block.set', {'pos': [3, 4, 3], 'block': {'id': 'minecraft:wobble'}})
    with self.assertRaises(BadRequest):
      self.request('block.get', {'pos': [3, 4]})

  def test_04_entities(self) -> None:
    zombie = self.request('entity.spawn', {'type': 'Zombie', 'pos': [4.5, 4.0, 4.5]})
    self.assertEqual('Zombie', zombie['type'])
    self.assertEqual([4.5, 4.0, 4.5], zombie['pos'])
    self.assertEqual(zombie['entity'], self.request('entity.get', {'entity': zombie['entity']})['entity'])
    self.clientHolds('entity.list', {'type': 'Zombie'}, {'len': {'eq': 1}})
    self.request('entity.remove', {'entity': zombie['entity']})
    with self.assertRaises(NotFound):
      self.request('entity.get', {'entity': zombie['entity']})
    with self.assertRaises(NotFound):
      self.request('entity.spawn', {'type': 'Wobble', 'pos': [4.5, 4.0, 4.5]})
    with self.assertRaises(NotReady) as caught:
      self.request('entity.spawn', {'type': 'Pig', 'pos': [100000.5, 4.0, 100000.5]})
    self.assertIn('loaded', caught.exception.message)

  def test_05_keys(self) -> None:
    start = self.request('player.get', side='client')['pos']
    self.request('key.down', {'key': 'key.forward'})
    self.request('ticks.wait', {'side': 'client', 'n': 10})
    self.request('key.up', {'key': 'key.forward'})
    moved = self.request('player.get', side='client')['pos']
    self.assertGreater(moved[2], start[2] + 0.5, 'looking south (yaw 0), forward is +z')
    self.request('key.tap', {'key': 'key.jump'})
    self.clientHolds('player.get', {}, {'path': ['on_ground'], 'eq': False}, ticks=10)
    self.request('key.down', {'key': {'code': 57}})
    self.request('key.up', {'key': {'code': 57}})
    with self.assertRaises(BadRequest):
      self.request('key.down', {'key': 'key.wobble'})

  def test_06_typing_into_the_chat(self) -> None:
    self.request('screen.open', {'screen': 'chat'})
    self.request('screen.type', {'text': '/time se'})
    self.assertEqual('/time se', self.request('chat.read')['text'])
    self.request('screen.close')

  def test_07_tab_completes_from_the_server(self) -> None:
    self.request('screen.open', {'screen': 'chat'})
    self.request('screen.type', {'text': '/tim'})
    self.request('screen.key', {'key': 'tab'})
    read = self.request('chat.read')
    self.assertEqual('/time', read['text'])
    self.assertIn('/time', read['suggestions'])
    self.assertEqual([], read['usage'], "1.7.10's own chat shows no usage")
    self.request('screen.close')

  def test_08_enter_runs_it(self) -> None:
    self.request('screen.open', {'screen': 'chat', 'text': '/time set 6000'})
    self.request('screen.key', {'key': 'enter'})
    self.assertIsNone(self.request('screen.get'), 'enter sends and closes')
    lines = [event['plain'] for event in self.events('chat')]
    self.assertTrue(any('6000' in line for line in lines), lines)
    with self.assertRaises(NotReady):
      self.request('chat.read')

  def test_09_chat_send(self) -> None:
    said = self.request('chat.send', {'text': '/time set 7000'})
    self.assertTrue(any('7000' in line for line in said['lines']), said)
    self.assertEqual(7000, self.request('world.get')['day_time'])

  def test_10_camera(self) -> None:
    self.request('camera.set', {'view': 1})
    self.assertEqual(1, self.request('player.get', side='client')['camera'])
    self.request('camera.set', {'view': 0})
    with self.assertRaises(BadRequest):
      self.request('camera.set', {'view': 3})

  def test_11_sounds(self) -> None:
    self.request('sound.play', {'id': 'minecraft:gui.button.press'})
    heard = self.connection.events.waitFor(lambda event: event.get('event') == 'sound', 10, since=self.mark)
    self.assertEqual('minecraft:gui.button.press', heard['id'])
    self.assertTrue(heard['known'])
    self.request('sound.play', {'id': 'minecraft:wobble.nothing'})
    unknown = self.connection.events.waitFor(
      lambda event: event.get('event') == 'sound' and event.get('id') == 'minecraft:wobble.nothing', 10, since=self.mark)
    self.assertFalse(unknown['known'], 'the game has no such sound: nothing is heard')

  def test_12_screen_events(self) -> None:
    self.request('screen.open', {'screen': 'inventory'})
    self.request('screen.close')
    changes = [(event['from'], event['to']) for event in self.events('screen')]
    self.assertTrue(any(to is not None and to.endswith('GuiContainerCreative') for _, to in changes), changes)
    self.assertEqual(None, changes[-1][1], changes)

  def test_13_screenshot(self) -> None:
    file = os.path.join(results(), 'game', 'screenshots', 'probe-picture.png')
    taken = self.request('screenshot', {'file': file})
    self.assertEqual(file, taken['file'])
    with open(file, 'rb') as picture:
      head = picture.read(24)
    self.assertEqual(b'\x89PNG', head[:4])
    self.assertEqual((taken['width'], taken['height']), struct.unpack('>II', head[16:24]))

  def test_14_quit(self) -> None:
    self.assertEqual({}, self.request('quit', {'reason': 'test_14'}))
    self.assertTrue(self.game.ended(120))


if __name__ == '__main__':
  unittest.main()

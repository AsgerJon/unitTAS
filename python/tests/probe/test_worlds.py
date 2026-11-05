"""
Step 4 of phase 2 (SPEC.md section 8.3): worlds. world.create makes the spec's flat world; world.get reads it; the
rules, the time, the weather and the difficulty are set; world.close leaves the folder whole, so Python can copy it,
and world.open opens the copy with all of that in it. With a world open, the server side ticks, and step 3's waits
are tested on it. One launch, its tests in order.

  python -m unittas.selftest worlds      (through the watcher: "probe worlds")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from probegame import READY_SECONDS, ROOT, results
from unittas.dev import DevGame
from unittas.errors import BadRequest, Exists, NotFound, NotReady

SEED = 20261029
LAYERS = '2;7,2x3,2;1;'
COPY = 'unittas-probe-copy'


class WorldTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.game = DevGame(ROOT, results(), 'worlds')
    cls.saves = os.path.join(cls.game.gameDir, 'saves')
    #  the orchestrator's part: the folders this test makes are cleared before it, with no world open
    for folder in ('unittas', COPY):
      shutil.rmtree(os.path.join(cls.saves, folder), ignore_errors=True)
    cls.connection = cls.game.start()

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop()
    shutil.rmtree(os.path.join(cls.saves, COPY), ignore_errors=True)

  def request(self, op, args=None, side=None, timeout=60.0):
    return self.connection.request(op, args, side=side, timeout=timeout)

  def test_00_ready(self) -> None:
    self.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)

  def test_01_no_world_yet(self) -> None:
    with self.assertRaises(NotReady):
      self.request('world.get')
    with self.assertRaises(NotReady):
      self.request('world.close')
    self.assertIsNone(self.request('status')['world'])

  def test_02_create(self) -> None:
    mark = self.connection.events.mark()
    made = self.request('world.create', {}, timeout=240)
    self.assertEqual('unittas', made['folder'])
    self.assertGreater(made['load_ms'], 0)
    self.assertEqual(3, len(made['spawn']))
    states = [event['state'] for event in self.connection.events.since(mark) if event.get('event') == 'world']
    self.assertIn('open', states)
    status = self.request('status')
    self.assertEqual('world', status['state'])
    self.assertEqual(['client', 'server'], status['sides'])
    self.assertEqual({'folder': 'unittas', 'dimension': 'minecraft:overworld'}, status['world'])
    self.assertIsNotNone(status['ticks']['server'])

  def test_03_the_spec_s_world(self) -> None:
    world = self.request('world.get')
    self.assertEqual('unittas', world['folder'])
    self.assertEqual('unitTAS', world['name'])
    self.assertEqual(SEED, world['seed'])
    self.assertEqual('flat', world['type'])
    self.assertEqual(LAYERS, world['generator'])
    self.assertEqual('creative', world['game_mode'])
    self.assertTrue(world['cheats'])
    self.assertFalse(world['hardcore'])
    self.assertIn('minecraft:overworld', world['dimensions'])
    self.assertIn('doDaylightCycle', world['rules'])
    again = self.request('world.get', side='server')
    #  the same world, its time a tick or two on
    self.assertEqual({key: value for key, value in world.items() if 'time' not in key},
                     {key: value for key, value in again.items() if 'time' not in key})
    with self.assertRaises(BadRequest):
      self.request('world.get', side='client')

  def test_04_one_world_at_a_time(self) -> None:
    with self.assertRaises(NotReady):
      self.request('world.create', {'folder': 'another'})
    with self.assertRaises(NotReady):
      self.request('world.open', {'folder': 'unittas'})

  def test_05_the_server_side_waits(self) -> None:
    value = self.request('ticks.wait', {'side': 'server', 'n': 20})
    self.assertEqual(20, value['tick'] - value['from'])
    entries = self.request('batch', {'ops': [{'op': 'world.get'}, {'op': 'world.get'}]}, side='server')
    self.assertEqual(1, len({entry['at']['server'] for entry in entries}), entries)
    self.assertEqual(entries[0]['value']['time'], entries[1]['value']['time'], 'one tick, one time')

  def test_06_wait_until_holds_later(self) -> None:
    #  the world's total time goes on with the day's cycle off: ten ticks from now it is ten more
    goal = self.request('world.get')['time'] + 10
    found = self.request('wait.until', {'side': 'server', 'op': 'world.get', 'max_ticks': 100,
                                        'test': {'path': ['time'], 'ge': goal}})
    self.assertTrue(found['held'])
    self.assertGreaterEqual(found['value']['time'], goal)
    self.assertGreater(found['checks'], 5)
    self.assertLess(found['checks'], 15)

  def test_07_rules(self) -> None:
    self.request('world.rules.set', {'rules': {'doDaylightCycle': False, 'doMobSpawning': False, 'doFireTick': False,
                                               'mobGriefing': False, 'keepInventory': True}})
    rules = self.request('world.get')['rules']
    self.assertEqual('false', rules['doDaylightCycle'])
    self.assertEqual('true', rules['keepInventory'])
    with self.assertRaises(NotFound) as caught:
      self.request('world.rules.set', {'rules': {'doWobbling': True}})
    self.assertIn('doWobbling', caught.exception.message)

  def test_08_time(self) -> None:
    self.request('world.time.set', {'time': 6000})
    self.assertEqual(6000, self.request('world.get')['day_time'])

  def test_09_weather(self) -> None:
    self.request('world.weather.set', {'weather': 'rain'})
    world = self.request('world.get')
    self.assertEqual((True, False), (world['raining'], world['thundering']))
    self.request('world.weather.set', {'weather': 'thunder'})
    self.assertTrue(self.request('world.get')['thundering'])
    self.request('world.weather.set', {'weather': 'clear', 'hold': True})
    world = self.request('world.get')
    self.assertEqual((False, False), (world['raining'], world['thundering']))

  def test_10_difficulty(self) -> None:
    self.request('world.difficulty.set', {'difficulty': 'hard'})
    self.assertEqual('hard', self.request('world.get')['difficulty'])
    self.request('world.difficulty.set', {'difficulty': 'easy'})
    self.assertEqual('easy', self.request('world.get')['difficulty'])

  def test_10b_prepare(self) -> None:
    # the steady world both runners give a test world (TasRunner.prepareWorld's body): four rules off, noon, clear
    self.request('world.rules.set', {'rules': {'doDaylightCycle': True, 'doMobSpawning': True, 'doFireTick': True,
                                               'mobGriefing': True}})
    self.request('world.time.set', {'time': 1000})
    self.request('world.weather.set', {'weather': 'rain'})
    self.assertEqual({}, self.request('world.prepare'))
    world = self.request('world.get')
    self.assertEqual({rule: 'false' for rule in ('doDaylightCycle', 'doMobSpawning', 'doFireTick', 'mobGriefing')},
                     {rule: world['rules'][rule] for rule in ('doDaylightCycle', 'doMobSpawning', 'doFireTick',
                                                              'mobGriefing')})
    self.assertEqual(6000, world['day_time'])
    self.assertEqual((False, False), (world['raining'], world['thundering']))

  def test_11_close(self) -> None:
    mark = self.connection.events.mark()
    closed = self.request('world.close', timeout=240)
    self.assertGreater(closed['close_ms'], 0)
    states = [event['state'] for event in self.connection.events.since(mark) if event.get('event') == 'world']
    self.assertIn('closed', states)
    status = self.request('status')
    self.assertEqual('menu', status['state'])
    self.assertEqual(['client'], status['sides'])
    with self.assertRaises(NotReady):
      self.request('ticks.wait', {'side': 'server', 'n': 1})

  def test_12_the_folder_is_whole_and_opens_again(self) -> None:
    #  the orchestrator's part: with no world open, the folder is files, copied in Python
    shutil.copytree(os.path.join(self.saves, 'unittas'), os.path.join(self.saves, COPY))
    opened = self.request('world.open', {'folder': COPY}, timeout=240)
    self.assertEqual(COPY, opened['folder'])
    world = self.request('world.get')
    self.assertEqual(SEED, world['seed'])
    self.assertEqual('false', world['rules']['doDaylightCycle'])
    self.assertEqual('true', world['rules']['keepInventory'])
    self.assertEqual(6000, world['day_time'])
    self.request('world.close', timeout=240)

  def test_13_not_there_and_in_the_way(self) -> None:
    with self.assertRaises(NotFound):
      self.request('world.open', {'folder': 'no-such-save'})
    with self.assertRaises(Exists):
      self.request('world.create', {'folder': 'unittas'})
    self.assertEqual('menu', self.request('status')['state'])

  def test_14_quit(self) -> None:
    self.assertEqual({}, self.request('quit', {'reason': 'test_14'}))
    self.assertTrue(self.game.ended(120))


if __name__ == '__main__':
  unittest.main()

"""
Step 4 of phase 2 (SPEC.md section 8.3), on the run's port (19.7 step 9): worlds. world.create makes the spec's flat
world; world.get reads it; the rules, the time, the weather and the difficulty are set; world.close leaves the folder
whole, so Python can copy it, and world.open opens the copy with all of that in it. With a world open, the server
side ticks, and step 3's waits are tested on it. A world of the default type (real terrain), and a flat world by its
layers. One launch, its tests in order.

Each version's own names, by the tables below: the flat world's text (1.7.10's numbers; the Customize box's text from
1.13 on), the rules (camel case up to 1.21.1, snake case in 26.3, where fire's spread is a radius), a layer's block
(1.7.10's by its meta; a block's id alone from 1.13 on). test_fabric's 26.3 world tests were these, on 26.3 alone.

  python -m unittas.selftest worlds      (through the watcher: "probe worlds", "probe worlds on 1.21.1")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from ports import V1_7_10, V1_16_1, V1_20_1, V1_21_1, V26_3, onlyOn, probeGame, start, title, version
from probegame import GONE_SECONDS, READY_SECONDS
from unittas.errors import BadRequest, Exists, NotFound, NotReady

SEED = 20261029
COPY, TERRAIN, LAYERED = 'unittas-probe-copy', 'unittas-terrain', 'unittas-layers'
#  the Customize box's text from 1.13 on: bedrock, two dirt, grass, on plains
MODERN_LAYERS = 'minecraft:bedrock,2*minecraft:dirt,minecraft:grass_block;minecraft:plains'
#  the spec's flat world, as each version writes it
LAYERS = {V1_7_10: '2;7,2x3,2;1;', V1_16_1: MODERN_LAYERS, V1_20_1: MODERN_LAYERS, V1_21_1: MODERN_LAYERS,
          V26_3: MODERN_LAYERS}
#  the rules the tests set, by what they do, as each version names them
CAMEL = {'daylight': 'doDaylightCycle', 'mobs': 'doMobSpawning', 'fire': 'doFireTick', 'griefing': 'mobGriefing',
         'keep': 'keepInventory'}
RULES = {V1_7_10: CAMEL, V1_16_1: CAMEL, V1_20_1: CAMEL, V1_21_1: CAMEL,
         V26_3: {'daylight': 'advance_time', 'mobs': 'spawn_mobs', 'fire': 'fire_spread_radius_around_player',
                 'griefing': 'mob_griefing', 'keep': 'keep_inventory'}}
#  fire off and on: a rule that is false or true; 26.3's spread radius, 0 or the default 128
FIRE = {V1_7_10: (False, True), V1_16_1: (False, True), V1_20_1: (False, True), V1_21_1: (False, True),
        V26_3: (0, 128)}
#  a rule by the other naming's name, which the version hasn't
OTHER_NAMING = {V1_7_10: 'advance_time', V1_16_1: 'advance_time', V1_20_1: 'advance_time', V1_21_1: 'advance_time',
                V26_3: 'doDaylightCycle'}
#  a flat world by its layers: the layers, the biome, the text the version writes of them, its top block and where
LAYERED_WORLD = {
  V1_7_10: ([{'id': 'minecraft:bedrock', 'meta': 0, 'count': 1}, {'id': 'minecraft:stone', 'meta': 0, 'count': 2},
             {'id': 'minecraft:wool', 'meta': 14, 'count': 1}], '2', '2;7,2x1,35:14;2;',
            {'id': 'minecraft:wool', 'meta': 14}, [0, 3, 0]),
}
for _modern in (V1_16_1, V1_20_1, V1_21_1, V26_3):
  LAYERED_WORLD[_modern] = (
    [{'id': 'minecraft:bedrock', 'count': 1}, {'id': 'minecraft:stone', 'count': 2},
     {'id': 'minecraft:red_wool', 'count': 1}], 'minecraft:desert',
    'minecraft:bedrock,2*minecraft:stone,minecraft:red_wool;minecraft:desert', {'id': 'minecraft:red_wool'},
    #  the top layer: y 3 where the world's bottom is y 0 (1.16.1), y -61 from 1.18 on
    [0, 3 if _modern == V1_16_1 else -61, 0])


def rule(what: str) -> str:
  """A rule by what it does, as the port's version names it."""
  return RULES[version()][what]


def text(value) -> str:
  """A rule's value as world.get reads it: the game's own text."""
  return str(value).lower() if isinstance(value, bool) else str(value)


class WorldTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.game = probeGame('worlds')
    cls.saves = os.path.join(cls.game.gameDir, 'saves')
    #  the orchestrator's part: the folders this test makes are cleared before it, with no world open
    for folder in ('unittas', COPY, TERRAIN, LAYERED):
      shutil.rmtree(os.path.join(cls.saves, folder), ignore_errors=True)
    cls.connection = cls.game.start(READY_SECONDS)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop()
    shutil.rmtree(os.path.join(cls.saves, COPY), ignore_errors=True)

  def request(self, op, args=None, side=None, timeout=60.0):
    return self.connection.request(op, args, side=side, timeout=timeout)

  def steady(self) -> dict:
    """The rules a steady test world has (world.prepare's): the day's cycle, mobs, fire's spread, griefing off."""
    return {rule('daylight'): 'false', rule('mobs'): 'false', rule('fire'): text(FIRE[version()][0]),
            rule('griefing'): 'false'}

  def test_00_ready(self) -> None:
    self.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)

  def test_01_no_world_yet(self) -> None:
    for op in ('world.create', 'world.open', 'world.close', 'world.get', 'world.rules.set', 'world.time.set',
               'world.weather.set', 'world.difficulty.set', 'world.prepare'):
      self.assertIn(op, self.connection.hello.ops)
    with self.assertRaises(NotReady):
      self.request('world.get')
    with self.assertRaises(NotReady):
      self.request('world.close')
    self.assertIsNone(self.request('status')['world'])

  @onlyOn(V1_16_1, V1_20_1, V1_21_1, V26_3, why="1.7.10's flat text is its own numbers (test_13b has its layers)")
  def test_01b_a_generator_the_version_can_t_read_is_refused_first(self) -> None:
    """The Customize box's text, read as the game reads it; one it would read otherwise is refused, nothing made."""
    for args in ({'generator': 'minecraft:bedrock,2*minecraft:no_such_block;minecraft:plains'},
                 {'generator': 'minecraft:bedrock,x*minecraft:dirt'},
                 {'type': 'default', 'generator': MODERN_LAYERS}):
      with self.subTest(args=args):
        with self.assertRaises(BadRequest) as caught:
          self.request('world.create', args)
        self.assertEqual('generator', caught.exception.fields.get('field'), caught.exception.message)
    self.assertFalse(os.path.exists(os.path.join(self.saves, 'unittas')), 'a refused world.create makes nothing')

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
    self.assertEqual(LAYERS[version()], world['generator'])
    self.assertEqual('creative', world['game_mode'])
    self.assertTrue(world['cheats'])
    self.assertFalse(world['hardcore'])
    if version() != V1_7_10:
      self.assertEqual(int(start()[1]), world['spawn'][1], 'on the grass, at the bottom of the world')
    self.assertIn('minecraft:overworld', world['dimensions'])
    self.assertIn(rule('daylight'), world['rules'])
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
    keep = 'minecraft:keep_inventory' if version() == V26_3 else rule('keep')
    self.request('world.rules.set', {'rules': {rule('daylight'): False, rule('mobs'): False,
                                               rule('fire'): FIRE[version()][0], rule('griefing'): False,
                                               keep: True}})
    rules = self.request('world.get')['rules']
    self.assertEqual('false', rules[rule('daylight')])
    self.assertEqual(text(FIRE[version()][0]), rules[rule('fire')])
    self.assertEqual('true', rules[rule('keep')], 'by its full name too in 26.3, as /gamerule takes it')
    for unknown in ('doWobbling', OTHER_NAMING[version()]):
      with self.subTest(rule=unknown):
        with self.assertRaises(NotFound) as caught:
          self.request('world.rules.set', {'rules': {unknown: False}})
        self.assertIn(unknown, caught.exception.message)
    if version() != V1_7_10:
      #  1.7.10's rules are any text; from 1.13 on a rule is a boolean or a number
      with self.assertRaises(BadRequest):
        self.request('world.rules.set', {'rules': {rule('daylight'): 'sometimes'}})
      self.assertEqual('false', self.request('world.get')['rules'][rule('daylight')], 'a refused value sets nothing')

  def test_08_time(self) -> None:
    self.request('world.time.set', {'time': 6000})
    self.assertEqual(6000, self.request('world.get')['day_time'])
    self.request('world.time.set', {'time': 7000, 'dimension': 'minecraft:overworld'})
    self.assertEqual(7000, self.request('world.get')['day_time'])
    with self.assertRaises(NotFound):
      self.request('world.time.set', {'time': 6000, 'dimension': 'minecraft:the_moon'})
    self.request('world.time.set', {'time': 6000})

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
    self.request('world.rules.set', {'rules': {rule('daylight'): True, rule('mobs'): True,
                                               rule('fire'): FIRE[version()][1], rule('griefing'): True}})
    self.request('world.time.set', {'time': 1000})
    self.request('world.weather.set', {'weather': 'rain'})
    self.assertEqual({}, self.request('world.prepare'))
    world = self.request('world.get')
    self.assertEqual(self.steady(), {name: world['rules'][name] for name in self.steady()})
    self.assertEqual(6000, world['day_time'])
    self.assertEqual((False, False), (world['raining'], world['thundering']))
    self.request('ticks.wait', {'side': 'server', 'n': 20})
    self.assertEqual(6000, self.request('world.get')['day_time'], "the day's cycle off: its clock is still")

  def test_11_close(self) -> None:
    mark = self.connection.events.mark()
    closed = self.request('world.close', timeout=240)
    self.assertGreater(closed['close_ms'], 0)
    states = [event['state'] for event in self.connection.events.since(mark) if event.get('event') == 'world']
    self.assertIn('closed', states)
    status = self.request('status')
    self.assertEqual('menu', status['state'])
    self.assertEqual(title(), status['screen'])
    self.assertEqual(['client'], status['sides'])
    with self.assertRaises(NotReady):
      self.request('ticks.wait', {'side': 'server', 'n': 1})

  def test_12_the_folder_is_whole_and_opens_again(self) -> None:
    #  the orchestrator's part: with no world open, the folder is files, copied in Python
    shutil.copytree(os.path.join(self.saves, 'unittas'), os.path.join(self.saves, COPY))
    opened = self.request('world.open', {'folder': COPY}, timeout=240)
    self.assertEqual(COPY, opened['folder'])
    self.assertEqual('unitTAS', opened['name'])
    world = self.request('world.get')
    self.assertEqual(SEED, world['seed'])
    self.assertEqual(LAYERS[version()], world['generator'])
    self.assertEqual('false', world['rules'][rule('daylight')])
    self.assertEqual('true', world['rules'][rule('keep')])
    self.assertEqual(6000, world['day_time'])
    self.request('world.close', timeout=240)

  def test_13_not_there_and_in_the_way(self) -> None:
    with self.assertRaises(NotFound):
      self.request('world.open', {'folder': 'no-such-save'})
    with self.assertRaises(Exists):
      self.request('world.create', {'folder': 'unittas'})
    self.assertEqual('menu', self.request('status')['state'])

  def test_13a_real_terrain(self) -> None:
    """A world of the default type (a class's own world asks for one: real terrain, for maps and the like)."""
    made = self.request('world.create', {'folder': TERRAIN, 'type': 'default', 'seed': 1234}, timeout=240)
    try:
      world = self.request('world.get')
      self.assertEqual(('default', '', 1234), (world['type'], world['generator'], world['seed']))
      self.assertEqual(made['spawn'], world['spawn'])
      self.assertGreater(world['spawn'][1], start()[1], 'real terrain is above the flat test world')
    finally:
      self.request('world.close', timeout=240)

  def test_13b_a_flat_world_by_its_layers(self) -> None:
    """
    Layers as this version's own blocks, bottom up, and a biome by its id
    (SPEC.md 17.4): the probe writes the version's own text itself (1.7.10's
    blocks by number). What doesn't fit is refused before anything is made.
    """
    layers, biome, written, top, where = LAYERED_WORLD[version()]
    with self.assertRaises(BadRequest):
      self.request('world.create', {'folder': LAYERED, 'type': 'flat', 'layers': layers,
                                    'generator': LAYERS[version()]})
    with self.assertRaises(BadRequest):
      self.request('world.create', {'folder': LAYERED, 'type': 'default', 'layers': layers})
    with self.assertRaises(NotFound):
      self.request('world.create', {'folder': LAYERED, 'type': 'flat', 'biome': biome,
                                    'layers': [dict(layers[0], id='minecraft:no_such_block')]})
    self.assertEqual('menu', self.request('status')['state'])
    self.request('world.create', {'folder': LAYERED, 'type': 'flat', 'layers': layers, 'biome': biome},
                 timeout=240)
    try:
      self.assertEqual(written, self.request('world.get')['generator'])
      self.assertEqual(top, self.request('block.get', {'pos': where}, side='server'))
      self.assertEqual(where, self.request('block.ground', {'x': 0, 'z': 0}, side='server')['pos'])
    finally:
      self.request('world.close', timeout=240)

  def test_14_quit(self) -> None:
    self.assertEqual({}, self.request('quit', {'reason': 'test_14'}))
    self.assertTrue(self.game.ended(GONE_SECONDS))


if __name__ == '__main__':
  unittest.main()

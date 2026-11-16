"""
Phase 4 (SPEC.md section 12.3): the 26.3 Fabric probe.
- Step 1, no game: fabric/ builds (its own Gradle build and wrapper, Fabric Loom, Java 25, Mojang's names; no
  daemon left), and its jar is the probe's: fabric.mod.json names its entrypoint and its mixins, and depends on Fabric
  Loader, Minecraft 26.3 and Java 25 only, never on Fabric API (D3); the probe's version-free core (shared with the
  1.7.10 probe as source, D5) is compiled into it.
- Step 2, one game: a real 26.3 Fabric client from unitTAS's own launcher (any version with a loader on top:
  bin/launch_client.py --minecraft 26.3 --loader fabric --loader-version 0.20.1, its Java the one 26.3's JSON asks
  for), in a game folder of its own with the probe in mods/, in the test display. The probe wakes before Minecraft
  loads, dials from the end of Minecraft's constructor, and its hello says what really runs: the port 26.3-fabric,
  Minecraft 26.3, Fabric Loader 0.20.1, Mojang's names, a client. Its first run downloads 26.3 (the client, its
  libraries and assets, several hundred MB) into the download cache, once. Asked to quit, it does, as the Quit
  button does.
- Step 3, the same game: its hooks (mixins on Minecraft's tick and screen and the server's tick, no Fabric API).
  Ready once it has loaded (the loading overlay gone, the title screen up), naming its mods; status in the menu,
  its ticks counted; ticks.wait counts exactly; wait.until on screen.get; the heartbeat's client ticks. Its window
  is titled unitTAS, as the 1.7.10 probe's is (PROTOCOL.md 2.5). Its game folder's options.txt is a returning
  player's (onboardAccessibility:false, tutorialStep:none): a first launch of 26.3 opens on its accessibility
  onboarding screen, not the title screen.
- Step 4, a launch of its own: worlds (FabricWorldTests), as test_worlds has them in 1.7.10: made, read, their rules,
  time, weather and difficulty set, the steady world, closed, copied and opened again, refused when not there or in
  the way; a world of real terrain too. The bodies are the core's (WorldOps); the game's calls 26.3's (FabricWorlds).
- Step 5a, a launch of its own: the game's things and the reset (FabricThingTests), as test_reset and test_game have
  them in 1.7.10: command.run, players, the inventory with its off hand, items with components, blocks with their
  states, entities by their ids, screens; the reset from anything a command reaches, and from the End.

  python -m unittas.selftest test_fabric.      (through the watcher: "probe test_fabric.")
  python -m unittest test_fabric.FabricJarTests (here: it builds, nothing more)
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import glob
import json
import os
import shutil
import signal
import subprocess
import sys
import unittest
import zipfile

from probegame import GONE_SECONDS, READY_SECONDS, ROOT, results
from unittas.cache import defaultRoot
from unittas.errors import BadRequest, Exists, NotFound, NotReady
from unittas.game import LaunchedGame
from unittas.release import gameJvms, putMods
from unittas.reset import reset

FABRIC = os.path.join(ROOT, 'fabric')
MINECRAFT, LOADER, LOADER_VERSION = '26.3', 'fabric', '0.20.1'
TITLE = 'net.minecraft.client.gui.screens.TitleScreen'
JAR = os.path.join(FABRIC, 'build', 'libs', 'unittas-probe-26.3-fabric.jar')
JAVA_25 = os.environ.get('UNITTAS_JAVA_25', '/usr/lib/jvm/java-25-openjdk')
#  the test world (step 4): the run's seed; a flat world's layers as 26.3's Customize box writes them, bedrock, two
#  dirt and grass on plains, no structures (1.7.10's are '2;7,2x3,2;1;')
SEED = 20261029
LAYERS_26 = 'minecraft:bedrock,2*minecraft:dirt,minecraft:grass_block;minecraft:plains'
COPY, TERRAIN = 'unittas-probe-copy', 'unittas-terrain'
#  where the reset puts the player in 26.3's flat test world: on its grass (the surface y -61), at the spawn
START_26 = (0.5, -60.0, 0.5)
#  the core: compiled into both probes from one place (D5); the world operations' bodies too (step 4a), their game
#  calls the port's GameWorlds
CORE = ('io/github/asgerjon/unittas/probe/link/Json.class', 'io/github/asgerjon/unittas/probe/link/Link.class',
        'io/github/asgerjon/unittas/probe/link/StartFile.class', 'io/github/asgerjon/unittas/probe/Probe.class',
        'io/github/asgerjon/unittas/probe/Ops.class', 'io/github/asgerjon/unittas/probe/Call.class',
        'io/github/asgerjon/unittas/probe/WorldOps.class', 'io/github/asgerjon/unittas/probe/GameWorlds.class')


def buildFabric(log: str) -> str:
  """fabric/'s jar, built (its own wrapper, Java 25, the project's own Gradle home, no daemon), its output into 'log'."""
  environ = dict(os.environ, JAVA_HOME=JAVA_25, GRADLE_USER_HOME=os.path.join(ROOT, '.gradle-home'))
  os.makedirs(os.path.dirname(log), exist_ok=True)
  with open(log, 'ab') as output:
    code = subprocess.call(['./gradlew', '--no-daemon', '--console=plain', 'build'], cwd=FABRIC, env=environ,
                           stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT)
  if code != 0:
    raise RuntimeError("fabric/'s build failed (exit %d); its log: %s" % (code, log))
  return JAR


class FabricJarTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.jar = buildFabric(os.path.join(results(), 'fabric-build', 'build.log'))
    with zipfile.ZipFile(cls.jar) as jar:
      cls.names = set(jar.namelist())
      cls.mod = json.loads(jar.read('fabric.mod.json').decode('utf-8'))

  def test_1_the_mod(self) -> None:
    self.assertEqual('unittas', self.mod['id'])
    self.assertEqual('*', self.mod.get('environment', '*'))
    entry = self.mod['entrypoints']['client'][0]
    self.assertIn(entry.replace('.', '/') + '.class', self.names, 'the entrypoint is in the jar')

  def test_2_what_it_needs(self) -> None:
    depends = self.mod['depends']
    self.assertEqual({'fabricloader', 'minecraft', 'java'}, set(depends), 'no Fabric API (D3)')
    self.assertEqual('26.3', depends['minecraft'])
    self.assertEqual('>=25', depends['java'])

  def test_3_its_mixins(self) -> None:
    for config in self.mod['mixins']:
      name = config if isinstance(config, str) else config['config']
      self.assertIn(name, self.names)

  def test_4_the_shared_core(self) -> None:
    for name in CORE:
      self.assertIn(name, self.names)


class FabricGame(LaunchedGame):
  """
  One launch of a real 26.3 Fabric client in run/fabric-26.3, its output in '<results>/<name>/client.log': the
  probe's jar in mods/, the game started by unitTAS's own launcher (any version with a loader on top) in the test
  display, the download cache filled as it needs.
  """

  def __init__(self, results: str, jar: str, name: str = 'fabric', cache: str = None) -> None:
    LaunchedGame.__init__(self, ROOT, results, name)
    self.__jar__ = jar
    self.__cache__ = cache or defaultRoot()

  def gameFolder(self) -> str:
    return os.path.join(ROOT, 'run', 'fabric-' + MINECRAFT)

  def command(self) -> list:
    return [os.path.join(ROOT, 'unittas-display.sh'), sys.executable, '-I', os.path.join(ROOT, 'bin', 'launch_client.py'),
            '--game', self.gameFolder(), '--cache', self.__cache__, '--minecraft', MINECRAFT, '--loader', LOADER,
            '--loader-version', LOADER_VERSION]

  def outputName(self) -> str:
    return 'client.log'

  def prepare(self) -> None:
    putMods(self.gameFolder(), [self.__jar__], os.path.join(self.results, 'mods-before-this-run'))
    # a returning player's options: 26.3's first launch opens on its accessibility onboarding, and a world's first
    # minutes show the movement tutorial's hints
    with open(os.path.join(self.gameFolder(), 'options.txt'), 'w', encoding='utf-8') as file:
      file.write('onboardAccessibility:false\ntutorialStep:none\n')

  def terminate(self) -> None:
    """The display's process group (the display, the game in it); and the game's JVM, found by its folder."""
    try:
      os.killpg(self.process().pid, signal.SIGTERM)
    except ProcessLookupError:
      pass
    for pid in gameJvms(self.gameFolder()):
      try:
        os.kill(pid, signal.SIGTERM)
      except ProcessLookupError:
        pass


class FabricGameTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    folder = os.path.join(results(), 'fabric')
    jar = buildFabric(os.path.join(folder, 'build.log'))
    cls.game = FabricGame(results(), jar)
    cls.connection = cls.game.start(READY_SECONDS)
    cls.ready = cls.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop(30)

  def test_1_its_hello_says_what_runs(self) -> None:
    hello = self.connection.hello
    self.assertEqual('26.3-fabric', hello.probePort)
    self.assertEqual(MINECRAFT, hello.minecraft)
    self.assertEqual((LOADER, LOADER_VERSION), (hello.loaderName, hello.loaderVersion))
    self.assertEqual('mojang', hello.names, '26.x is unobfuscated: no mappings')
    self.assertEqual('client', hello.role.value if hasattr(hello.role, 'value') else str(hello.role))
    self.assertFalse(hello.development, 'a real client, not a development run')
    self.assertTrue(hello.probeVersion, "the probe's version from its fabric.mod.json")
    self.assertTrue(hello.javaVersion.startswith('25'), hello.javaVersion)

  def test_2_the_probe_s_own_operations(self) -> None:
    for op in ('status', 'quit', 'ticks.wait', 'cancel', 'events.set'):
      self.assertIn(op, self.connection.hello.ops)
    self.assertIn('screen.get', self.connection.hello.ops, "the client's own (step 3)")
    self.assertNotIn('key.down', self.connection.hello.ops, "input comes with a later step (6)")

  def test_2b_ready_once_loaded(self) -> None:
    self.assertEqual(TITLE, self.ready['screen'])
    mods = {mod['id'] for mod in self.ready['mods']}
    self.assertTrue({'unittas', 'minecraft', 'fabricloader'} <= mods, mods)
    self.assertEqual((854, 480), (self.ready['window']['width'], self.ready['window']['height']))
    self.assertEqual('unitTAS', self.ready['window']['title'], "the window's behaviours (PROTOCOL.md 2.5)")
    self.assertEqual([], self.ready['mixins']['missing'])

  def test_3_status_answers(self) -> None:
    status = self.connection.request('status')
    self.assertEqual('menu', status['state'])
    self.assertEqual(TITLE, status['screen'])
    self.assertEqual(['client'], status['sides'], 'no world: no server side')
    self.assertGreaterEqual(status['ticks']['client'], 1)
    self.assertEqual('unitTAS', status['player'])
    self.assertEqual('unitTAS', status['window']['title'])

  def test_3b_ticks_counted_exactly(self) -> None:
    before = self.connection.request('status')['ticks']['client']
    waited = self.connection.request('ticks.wait', {'side': 'client', 'n': 20}, timeout=30)
    self.assertGreaterEqual(waited['from'], before)
    self.assertEqual(20, waited['tick'] - waited['from'])
    none = self.connection.request('ticks.wait', {'side': 'client', 'n': 0})
    self.assertEqual(none['from'], none['tick'])

  def test_3c_wait_until_on_the_screen(self) -> None:
    found = self.connection.request('wait.until', {'side': 'client', 'op': 'screen.get', 'args': {},
                                                   'test': {'path': ['class'], 'eq': TITLE}, 'max_ticks': 100})
    self.assertTrue(found['held'], found)
    self.assertFalse(found['value']['pauses'])
    never = self.connection.request('wait.until', {'side': 'client', 'op': 'screen.get', 'args': {},
                                                   'test': {'path': ['pauses'], 'eq': True}, 'max_ticks': 10})
    self.assertFalse(never['held'])
    self.assertEqual(10, never['checks'], 'one check a tick')

  def test_3d_the_heartbeat_s_ticks(self) -> None:
    mark = self.connection.events.mark()
    first = self.connection.events.waitFor(lambda event: event.get('event') == 'tick', 10, since=mark)
    self.connection.request('ticks.wait', {'side': 'client', 'n': 40}, timeout=30)
    later = self.connection.events.waitFor(
      lambda event: event.get('event') == 'tick' and event['client'] > first['client'], 10, since=mark)
    self.assertGreater(later['client'], first['client'])
    self.assertIsNone(later['server'], 'no world: no server ticks')

  def test_4_quit_ends_the_game(self) -> None:
    """The game's own way out (Minecraft.stop, as its Quit button), which the port gives the probe as it dials."""
    mark = self.connection.events.mark()
    self.assertEqual({}, self.connection.request('quit', {'reason': 'test_4'}, timeout=10))
    gone = self.connection.events.waitFor(lambda event: event.get('event') == 'quit', 30, since=mark)
    self.assertEqual('asked', gone['reason'])
    self.assertTrue(self.game.ended(GONE_SECONDS), 'the game is still running %s s after quit' % GONE_SECONDS)


class FabricWorldTests(unittest.TestCase):
  """
  Step 4 (SPEC.md 12.3): worlds in 26.3, as test_worlds has them in 1.7.10, in one launch, its tests in order. The
  operations' bodies are the core's (WorldOps, step 4a); the game's calls are 26.3's own (FabricWorlds): a world made
  as createFreshLevel makes it, opened as the world list's Play opens it, left as the pause menu's Save and Quit
  leaves it. Its own names where 26.3's differ: the rules (advance_time, not doDaylightCycle), a flat world's layers as
  its Customize box writes them, and a flat world that starts at the bottom of the world (y -64), so its surface is
  y -61 and the player stands at y -60.
  """

  @classmethod
  def setUpClass(cls) -> None:
    folder = os.path.join(results(), 'fabric-worlds')
    jar = buildFabric(os.path.join(folder, 'build.log'))
    cls.game = FabricGame(results(), jar, name='fabric-worlds')
    cls.saves = os.path.join(cls.game.gameFolder(), 'saves')
    #  the orchestrator's part: the folders this test makes are cleared before it, with no world open
    for save in ('unittas', COPY, TERRAIN):
      shutil.rmtree(os.path.join(cls.saves, save), ignore_errors=True)
    cls.connection = cls.game.start(READY_SECONDS)
    cls.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop(30)
    shutil.rmtree(os.path.join(cls.saves, COPY), ignore_errors=True)

  def request(self, op, args=None, side=None, timeout=60.0):
    return self.connection.request(op, args, side=side, timeout=timeout)

  def test_01_no_world_yet(self) -> None:
    for op in ('world.create', 'world.open', 'world.close', 'world.get', 'world.rules.set', 'world.time.set',
               'world.weather.set', 'world.difficulty.set', 'world.prepare'):
      self.assertIn(op, self.connection.hello.ops)
    with self.assertRaises(NotReady):
      self.request('world.get')
    with self.assertRaises(NotReady):
      self.request('world.close')
    self.assertIsNone(self.request('status')['world'])

  def test_01b_a_generator_26_3_can_t_read_is_refused_first(self) -> None:
    """The Customize box's text, read as the game reads it; one it would read otherwise is refused, nothing made."""
    for args in ({'generator': 'minecraft:bedrock,2*minecraft:no_such_block;minecraft:plains'},
                 {'generator': 'minecraft:bedrock,x*minecraft:dirt'},
                 {'type': 'default', 'generator': LAYERS_26}):
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
    self.assertEqual(LAYERS_26, world['generator'])
    self.assertEqual('creative', world['game_mode'])
    self.assertTrue(world['cheats'])
    self.assertFalse(world['hardcore'])
    self.assertEqual(-60, world['spawn'][1], 'on the grass, at the bottom of the world')
    self.assertIn('minecraft:overworld', world['dimensions'])
    self.assertIn('advance_time', world['rules'])
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
    goal = self.request('world.get')['time'] + 10
    found = self.request('wait.until', {'side': 'server', 'op': 'world.get', 'max_ticks': 100,
                                        'test': {'path': ['time'], 'ge': goal}})
    self.assertTrue(found['held'])
    self.assertGreaterEqual(found['value']['time'], goal)
    self.assertGreater(found['checks'], 5)
    self.assertLess(found['checks'], 15)

  def test_07_rules(self) -> None:
    self.request('world.rules.set', {'rules': {'advance_time': False, 'spawn_mobs': False,
                                               'fire_spread_radius_around_player': 0, 'mob_griefing': False,
                                               'minecraft:keep_inventory': True}})
    rules = self.request('world.get')['rules']
    self.assertEqual('false', rules['advance_time'])
    self.assertEqual('0', rules['fire_spread_radius_around_player'])
    self.assertEqual('true', rules['keep_inventory'], 'by its full name too, as /gamerule takes it')
    with self.assertRaises(NotFound) as caught:
      self.request('world.rules.set', {'rules': {'doDaylightCycle': False}})
    self.assertIn('doDaylightCycle', caught.exception.message, "1.7.10's name isn't 26.3's")
    with self.assertRaises(BadRequest):
      self.request('world.rules.set', {'rules': {'advance_time': 'sometimes'}})
    self.assertEqual('false', self.request('world.get')['rules']['advance_time'], 'a refused value sets nothing')

  def test_08_time(self) -> None:
    self.request('world.time.set', {'time': 6000})
    self.assertEqual(6000, self.request('world.get')['day_time'])
    self.request('world.time.set', {'time': 7000, 'dimension': 'minecraft:overworld'})
    self.assertEqual(7000, self.request('world.get')['day_time'])
    with self.assertRaises(NotFound):
      self.request('world.time.set', {'time': 6000, 'dimension': 'minecraft:the_moon'})

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
    #  the steady world both runners give a test world, by 26.3's rules: four off, noon, clear
    steady = {'advance_time': 'false', 'spawn_mobs': 'false', 'fire_spread_radius_around_player': '0',
              'mob_griefing': 'false'}
    self.request('world.rules.set', {'rules': {'advance_time': True, 'spawn_mobs': True,
                                               'fire_spread_radius_around_player': 128, 'mob_griefing': True}})
    self.request('world.time.set', {'time': 1000})
    self.request('world.weather.set', {'weather': 'rain'})
    self.assertEqual({}, self.request('world.prepare'))
    world = self.request('world.get')
    self.assertEqual(steady, {rule: world['rules'][rule] for rule in steady})
    self.assertEqual(6000, world['day_time'])
    self.assertEqual((False, False), (world['raining'], world['thundering']))
    self.request('ticks.wait', {'side': 'server', 'n': 20})
    self.assertEqual(6000, self.request('world.get')['day_time'], "advance_time off: the day's clock is still")

  def test_11_close(self) -> None:
    mark = self.connection.events.mark()
    closed = self.request('world.close', timeout=240)
    self.assertGreater(closed['close_ms'], 0)
    states = [event['state'] for event in self.connection.events.since(mark) if event.get('event') == 'world']
    self.assertIn('closed', states)
    status = self.request('status')
    self.assertEqual('menu', status['state'])
    self.assertEqual(TITLE, status['screen'])
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
    self.assertEqual(LAYERS_26, world['generator'])
    self.assertEqual('false', world['rules']['advance_time'])
    self.assertEqual('true', world['rules']['keep_inventory'])
    self.assertEqual(6000, world['day_time'])
    self.request('world.close', timeout=240)

  def test_13_not_there_and_in_the_way(self) -> None:
    with self.assertRaises(NotFound):
      self.request('world.open', {'folder': 'no-such-save'})
    with self.assertRaises(Exists):
      self.request('world.create', {'folder': 'unittas'})
    self.assertEqual('menu', self.request('status')['state'])

  def test_13b_real_terrain(self) -> None:
    """A world of the default type (a class's own world asks for one: real terrain, for maps and the like)."""
    made = self.request('world.create', {'folder': TERRAIN, 'type': 'default', 'seed': 1234}, timeout=240)
    world = self.request('world.get')
    self.assertEqual(('default', '', 1234), (world['type'], world['generator'], world['seed']))
    self.assertEqual(made['spawn'], world['spawn'])
    self.assertGreater(world['spawn'][1], -60, 'real terrain is above the bottom of the world')
    self.request('world.close', timeout=240)

  def test_14_quit(self) -> None:
    self.assertEqual({}, self.request('quit', {'reason': 'test_14'}))
    self.assertTrue(self.game.ended(GONE_SECONDS))


class FabricThingTests(unittest.TestCase):
  """
  Step 5a (SPEC.md 12.3): the game's things in 26.3 and the reset, as test_reset and test_game have them in 1.7.10,
  in one launch, its tests in order, on the raw answers (5b reads them as values). 26.3's own values (D4): a block by
  its flattened id and its state's properties, no meta; an item by its id and count, its data as components, no meta
  or NBT; an entity's type by its id (minecraft:zombie); the inventory's off hand. The flat world's surface is y -61:
  the player stands at y -60, so the reset's start here is 0.5 -60 0.5.
  """

  @classmethod
  def setUpClass(cls) -> None:
    folder = os.path.join(results(), 'fabric-things')
    jar = buildFabric(os.path.join(folder, 'build.log'))
    cls.game = FabricGame(results(), jar, name='fabric-things')
    shutil.rmtree(os.path.join(cls.game.gameFolder(), 'saves', 'unittas'), ignore_errors=True)
    cls.connection = cls.game.start(READY_SECONDS)
    cls.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    cls.connection.request('world.create', {}, timeout=240)
    cls.connection.request('world.prepare')

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop(30)

  def request(self, op, args=None, side=None, timeout=60.0):
    return self.connection.request(op, args, side=side, timeout=timeout)

  def command(self, text: str) -> None:
    said = self.request('command.run', {'command': text})
    self.assertEqual([], said['errors'], (text, said))

  def reset(self) -> None:
    reset(self.connection, at=START_26)

  def clientHolds(self, op, args, test, ticks=60):
    found = self.request('wait.until', {'side': 'client', 'op': op, 'args': args, 'test': test, 'max_ticks': ticks})
    self.assertTrue(found['held'], 'the client never saw it: %r' % (found,))
    return found['value']

  def test_01_command_run(self) -> None:
    said = self.request('command.run', {'command': '/say from the probe'})
    self.assertEqual([], said['errors'])
    wrong = self.request('command.run', {'command': '/wobble'})
    self.assertTrue(wrong['errors'], 'an unknown command answers in red: %r' % (wrong,))
    self.assertEqual(wrong['errors'], [line for line in wrong['lines'] if line in wrong['errors']])

  def test_02_everything_put_back(self) -> None:
    self.reset()
    # dirtied: survival, experience, items (the off hand too), an effect, hurt, moved and turned, rain, Hard, mobs, a
    # container open
    self.command('/gamemode survival')
    self.command('/xp add @p 30 levels')
    self.command('/give @p minecraft:red_wool 3')
    self.command('/give @p minecraft:diamond 5')
    self.request('inventory.set', {'slot': 'offhand', 'item': {'id': 'minecraft:shield'}})
    self.command('/effect give @p minecraft:speed 600 2')
    self.command('/effect give @p minecraft:instant_damage 1 0')
    self.command('/weather rain')
    self.command('/difficulty hard')
    self.command('/summon minecraft:zombie 5 -60 5')
    self.command('/summon minecraft:pig 3 -60 3')
    self.request('player.teleport', {'pos': [20.5, -50.0, 20.5], 'look': {'yaw': 45.0, 'pitch': 30.0}})
    self.request('screen.open', {'screen': 'inventory'})
    dirty = self.request('player.get')
    self.assertEqual('survival', dirty['game_mode'])
    self.assertLess(dirty['health'], dirty['max_health'], 'instant damage hurt it')
    self.assertTrue(dirty['effects'])
    self.assertEqual('minecraft:shield', self.request('inventory.get')['offhand']['id'])
    types = [each['type'] for each in self.request('entity.list', {'near': {'pos': 'player', 'radius': 64}})]
    self.assertIn('minecraft:zombie', types)
    self.assertIn('minecraft:pig', types)

    self.reset()

    player = self.request('player.get')
    self.assertEqual('creative', player['game_mode'])
    self.assertEqual(0, player['xp']['level'])
    self.assertEqual(0, player['xp']['total'])
    self.assertEqual([], player['effects'])
    self.assertEqual(list(START_26), player['pos'])
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
    self.assertIsNone(inventory['offhand'])
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
    self.assertEqual(0, client['camera'])
    self.assertEqual([None] * 36, self.request('inventory.get', side='client')['main'], 'the client has the slots too')

  def test_03_from_the_end(self) -> None:
    self.request('player.teleport', {'dimension': 'minecraft:the_end', 'pos': [0.5, 70.0, 0.5]}, timeout=120)
    self.assertEqual('minecraft:the_end', self.request('player.get')['dimension'])
    self.reset()
    player = self.request('player.get')
    self.assertEqual('minecraft:overworld', player['dimension'])
    self.assertEqual(list(START_26), player['pos'])
    self.assertEqual('minecraft:overworld', self.request('player.get', side='client')['dimension'])
    self.assertEqual('world', self.request('status')['state'])

  def test_04_twice_is_once_and_the_parts_alone(self) -> None:
    self.reset()
    self.reset()
    self.assertEqual(list(START_26), self.request('player.get')['pos'])
    self.assertEqual({'respawned': False}, self.request('player.reset', {'at': list(START_26)}))
    self.assertEqual({}, self.request('world.reset'))
    self.assertEqual({}, self.request('client.reset'))
    self.assertEqual({'plugins': []}, self.request('hooks.run', {'hook': 'resetPlayer'}), 'no plugins in 26.3 yet')

  def test_05_inventory(self) -> None:
    self.reset()
    self.request('inventory.set', {'slot': 'held', 'item': {'id': 'minecraft:diamond', 'count': 2}})
    self.assertEqual({'id': 'minecraft:diamond', 'count': 2}, self.request('inventory.get', {'slot': 'held'}))
    self.clientHolds('inventory.get', {'slot': 'held'}, {'path': ['id'], 'eq': 'minecraft:diamond'})
    self.request('inventory.set', {'items': {'main.3': {'id': 'minecraft:red_wool'},
                                             'armor.feet': {'id': 'minecraft:leather_boots'},
                                             'offhand': {'id': 'minecraft:torch', 'count': 4}}})
    inventory = self.request('inventory.get')
    self.assertEqual({'id': 'minecraft:red_wool', 'count': 1}, inventory['main'][3])
    self.assertEqual('minecraft:leather_boots', inventory['armor']['feet']['id'])
    self.assertEqual({'id': 'minecraft:torch', 'count': 4}, inventory['offhand'])
    self.clientHolds('inventory.get', {}, {'path': ['offhand', 'id'], 'eq': 'minecraft:torch'})
    self.request('inventory.set', {'slot': 'held', 'item': None})
    self.assertIsNone(self.request('inventory.get', {'slot': 'held'}))
    with self.assertRaises(NotFound):
      self.request('inventory.set', {'slot': 'held', 'item': {'id': 'minecraft:wobble'}})
    with self.assertRaises(BadRequest):
      self.request('inventory.set', {'slot': 'main.99', 'item': {'id': 'minecraft:stone'}})
    with self.assertRaises(BadRequest) as caught:
      self.request('inventory.set', {'slot': 'held', 'item': {'id': 'minecraft:red_wool', 'meta': 14}})
    self.assertIn('meta', caught.exception.message, "26.3 has no meta: the colour is in the id")

  def test_06_components(self) -> None:
    """An item's data in 26.3 is its components, as SNBT: given, kept, read back as the game writes them."""
    self.reset()
    named = {'id': 'minecraft:red_wool', 'count': 3, 'components': '{"minecraft:custom_name":"Red"}'}
    self.request('inventory.set', {'slot': 'held', 'item': named})
    held = self.request('inventory.get', {'slot': 'held'})
    self.assertEqual(('minecraft:red_wool', 3), (held['id'], held['count']))
    self.assertIn('minecraft:custom_name', held['components'])
    self.assertIn('Red', held['components'])
    self.request('inventory.set', {'slot': 'main.1', 'item': held})
    self.assertEqual(held, self.request('inventory.get', {'slot': 'main.1'}), 'what it reads, it takes back')
    with self.assertRaises(BadRequest):
      self.request('inventory.set', {'slot': 'held', 'item': {'id': 'minecraft:stone', 'nbt': '{a:1}'}})

  def test_07_blocks(self) -> None:
    self.reset()
    self.assertEqual({'id': 'minecraft:grass_block', 'state': {'snowy': 'false'}},
                     self.request('block.get', {'pos': [0, -61, 0]}))
    self.assertEqual({'id': 'minecraft:air'}, self.request('block.get', {'pos': [3, -60, 3]}))
    self.request('block.set', {'pos': [3, -60, 3], 'block': {'id': 'minecraft:red_wool'}})
    self.assertEqual({'id': 'minecraft:red_wool'}, self.request('block.get', {'pos': [3, -60, 3]}))
    self.clientHolds('block.get', {'pos': [3, -60, 3]}, {'path': ['id'], 'eq': 'minecraft:red_wool'})
    self.request('block.set', {'pos': [4, -60, 3], 'block': {'id': 'minecraft:oak_log', 'state': {'axis': 'x'}}})
    self.assertEqual({'id': 'minecraft:oak_log', 'state': {'axis': 'x'}}, self.request('block.get', {'pos': [4, -60, 3]}))
    self.request('block.set', {'pos': [5, -60, 3], 'block': {'id': 'minecraft:chest'}})
    chest = self.request('block.get', {'pos': [5, -60, 3], 'tile': True})
    self.assertEqual('minecraft:chest', chest['id'])
    self.assertIsInstance(chest['tile'], str)
    self.assertIsNone(self.request('block.get', {'pos': [3, -60, 3], 'tile': True})['tile'])
    self.request('block.set', {'pos': [3, -60, 3], 'block': {'id': 'minecraft:air'}})
    with self.assertRaises(NotFound):
      self.request('block.set', {'pos': [3, -60, 3], 'block': {'id': 'minecraft:wobble'}})
    with self.assertRaises(BadRequest):
      self.request('block.set', {'pos': [3, -60, 3], 'block': {'id': 'minecraft:oak_log', 'state': {'axis': 'w'}}})
    with self.assertRaises(BadRequest):
      self.request('block.set', {'pos': [3, -60, 3], 'block': {'id': 'minecraft:red_wool', 'meta': 14}})
    with self.assertRaises(BadRequest):
      self.request('block.get', {'pos': [3, -60]})

  def test_08_entities(self) -> None:
    self.reset()
    zombie = self.request('entity.spawn', {'type': 'minecraft:zombie', 'pos': [4.5, -60.0, 4.5]})
    self.assertEqual('minecraft:zombie', zombie['type'])
    self.assertEqual([4.5, -60.0, 4.5], zombie['pos'])
    self.assertTrue(zombie['health'] > 0.0)
    self.assertEqual(zombie['entity'], self.request('entity.get', {'entity': zombie['entity']})['entity'])
    self.clientHolds('entity.list', {'type': 'minecraft:zombie'}, {'len': {'eq': 1}})
    self.request('entity.remove', {'entity': zombie['entity']})
    with self.assertRaises(NotFound):
      self.request('entity.get', {'entity': zombie['entity']})
    arrow = self.request('entity.spawn', {'type': 'minecraft:arrow', 'pos': [6.5, -58.0, 6.5]})
    self.assertNotIn('health', arrow, 'an arrow is not living')
    with self.assertRaises(NotFound):
      self.request('entity.spawn', {'type': 'minecraft:wobble', 'pos': [4.5, -60.0, 4.5]})
    with self.assertRaises(NotReady) as caught:
      self.request('entity.spawn', {'type': 'minecraft:pig', 'pos': [100000.5, -60.0, 100000.5]})
    self.assertIn('loaded', caught.exception.message)

  def test_09_players(self) -> None:
    self.reset()
    server = self.request('player.get')
    client = self.request('player.get', side='client')
    self.assertEqual(server['entity'], client['entity'])
    self.assertEqual('unitTAS', server['name'])
    self.assertNotIn('camera', server, 'the server side has no camera')
    self.command('/effect give @p minecraft:speed 30 1')
    effects = self.request('player.get')['effects']
    self.assertEqual(['minecraft:speed'], [effect['effect'] for effect in effects])
    self.assertEqual(1, effects[0]['amplifier'])

  def test_10_screens(self) -> None:
    self.reset()
    self.assertIsNone(self.request('screen.get'))
    self.request('screen.open', {'screen': 'inventory'})
    self.assertTrue(self.request('screen.get')['container'])
    self.request('screen.close')
    self.assertIsNone(self.request('screen.get'))

  def test_11_quit_from_a_world(self) -> None:
    self.assertEqual({}, self.request('quit', {'reason': 'test_11'}))
    self.assertTrue(self.game.ended(GONE_SECONDS), 'the game is still running %s s after quit' % GONE_SECONDS)


if __name__ == '__main__':
  unittest.main()

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

  python -m unittas.selftest test_fabric.      (through the watcher: "probe test_fabric.")
  python -m unittest test_fabric.FabricJarTests (here: it builds, nothing more)
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import glob
import json
import os
import signal
import subprocess
import sys
import unittest
import zipfile

from probegame import GONE_SECONDS, READY_SECONDS, ROOT, results
from unittas.cache import defaultRoot
from unittas.game import LaunchedGame
from unittas.release import gameJvms, putMods

FABRIC = os.path.join(ROOT, 'fabric')
MINECRAFT, LOADER, LOADER_VERSION = '26.3', 'fabric', '0.20.1'
TITLE = 'net.minecraft.client.gui.screens.TitleScreen'
JAR = os.path.join(FABRIC, 'build', 'libs', 'unittas-probe-26.3-fabric.jar')
JAVA_25 = os.environ.get('UNITTAS_JAVA_25', '/usr/lib/jvm/java-25-openjdk')
#  the core: compiled into both probes from one place (D5)
CORE = ('io/github/asgerjon/unittas/probe/link/Json.class', 'io/github/asgerjon/unittas/probe/link/Link.class',
        'io/github/asgerjon/unittas/probe/link/StartFile.class', 'io/github/asgerjon/unittas/probe/Probe.class',
        'io/github/asgerjon/unittas/probe/Ops.class', 'io/github/asgerjon/unittas/probe/Call.class')


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
    self.assertNotIn('block.get', self.connection.hello.ops, "the game's things come with the later steps")

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


if __name__ == '__main__':
  unittest.main()

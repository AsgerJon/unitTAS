"""
Phase 3b step 6 (SPEC.md section 11.3): the two multiplayer tests that need unitTAS's own test mod (src/mptest,
build/mptest/unittas-mptest.jar, never released), on a dedicated server that has it.
- A client without the mod is refused at its join: Disconnected, with FML's reason naming the mod; the client is
  back at its title screen.
- Reflection on a dedicated server reads the server's own state, by readable names translated to Searge's.
- The red test: the mod's common code that reaches a client class (Red.reachClient), called on the server, fails
  with a NoClassDefFoundError naming the client class. That failure shows on a dedicated server only, which is what
  a dedicated server in a test run is for.
Two games (a server and a real client): asked for before it is run.

  python -m unittas.selftest test_mptest.      (through the watcher: "probe test_mptest.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import subprocess
import unittest

from probegame import READY_SECONDS, ROOT, results
from unittas.api import Game
from unittas.errors import Disconnected, GameError
from unittas.launcher import Sources
from unittas.mappings import Mappings
from unittas.release import ReleaseGame, releaseJar
from unittas.servergame import ServerGame

MOD = 'unittas_mptest'
RED = 'io.github.asgerjon.unittas.mptest.Red'


def mptestJar(log: str) -> str:
  """The test mod's jar, built (./gradlew mptestJar, no daemon), its output into 'log'."""
  with open(log, 'ab') as output:
    code = subprocess.call(['./gradlew', '--no-daemon', '--console=plain', 'mptestJar'], cwd=ROOT,
                           stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT)
  if code != 0:
    raise RuntimeError('the test mod\'s build failed (exit %d); its log: %s' % (code, log))
  return os.path.join(ROOT, 'build', 'mptest', 'unittas-mptest.jar')


class MpTestModTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    if not os.path.isfile(os.path.join(ROOT, 'asger_accepts_all_eulas.txt')):
      raise unittest.SkipTest("a dedicated server needs Mojang's EULA accepted: this runs on Asger's standing yes only")
    built = os.path.join(results(), 'mptest-server')
    os.makedirs(built, exist_ok=True)
    jar = releaseJar(ROOT, os.path.join(built, 'build.log'))
    testMod = mptestJar(os.path.join(built, 'build.log'))
    mixins = os.path.join(ROOT, 'run', 'oldsaves', 'mods', 'unimixins-1.7.10-0.3.1.jar')
    folder = os.path.join(results(), 'mptest-server-folder')
    shutil.rmtree(folder, ignore_errors=True)
    gradleHome = os.path.join(ROOT, '.gradle-home')
    cls.server = ServerGame(ROOT, results(), 'mptest-server', folder=folder, mods=[jar, mixins, testMod],
                            players=('unitTAS',), eula=True, memory='1G', sources=Sources(gradleHome=gradleHome))
    connection, cls.ready = cls.server.ready(READY_SECONDS)
    cls.serverGame = Game(connection, mappings=Mappings.load(Sources(gradleHome=gradleHome)))
    cls.client = ReleaseGame(ROOT, results(), 'mptest-client', jar=jar)
    try:
      clientConnection = cls.client.start()
      clientConnection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    except BaseException:
      cls.server.stop()
      raise
    cls.clientConnection = clientConnection
    cls.clientGame = Game(clientConnection)

  @classmethod
  def tearDownClass(cls) -> None:
    try:
      cls.client.stop()
    finally:
      cls.server.stop()

  def test_1_the_mod_is_on_the_server_only(self) -> None:
    self.assertIn(MOD, [mod['id'] for mod in self.ready['mods']])
    self.assertNotIn(MOD, [mod['id'] for mod in self.clientConnection.events.waitFor(
      lambda event: event.get('event') == 'ready', 10)['mods']])

  def test_2_a_client_without_it_is_refused(self) -> None:
    with self.assertRaises(Disconnected) as raised:
      self.clientGame.join(self.server.port, maxSeconds=60)
    self.assertIn(MOD, str(raised.exception), "FML's reason names the mod the client lacks")
    answer = self.clientConnection.request('wait.until', {
      'side': 'client', 'op': 'screen.get', 'args': {}, 'max_ticks': 200,
      'test': {'path': ['class'], 'eq': 'net.minecraft.client.gui.GuiMainMenu'}}, timeout=60)
    self.assertTrue(answer['held'], 'not back at the title screen: %r' % (answer['value'],))

  def test_3_reflection_on_the_server(self) -> None:
    self.assertEqual(8, self.serverGame.reflect(['getMaxPlayers'], source='minecraft', side='server'))
    self.assertEqual('unittas', self.serverGame.reflect(['getFolderName'], source='minecraft', side='server'))

  def test_4_the_red_reaches_a_client_class(self) -> None:
    with self.assertRaises(GameError) as raised:
      self.serverGame.reflect([{'call': 'reachClient'}], source={'class': RED}, side='server')
    said = str(raised.exception) + repr(raised.exception.fields)
    self.assertIn('NoClassDefFoundError', said)
    self.assertIn('net/minecraft/client/Minecraft', said)


if __name__ == '__main__':
  unittest.main()

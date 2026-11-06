"""
Phase 3b step 1 (SPEC.md 11.3), without a game: the dedicated server's launch and its folder.
- The command: Forge's universal jar, the libraries Forge's JSON marks a server's (in its order), Mojang's server jar
  last; FML's server launch, no window ('nogui'); from the Gradle cache, else the download cache, each file once and
  held to its sha1; a server's memory as given.
- The folder: server.properties written fresh for each run, listening on 127.0.0.1 only and opening no other port;
  eula.txt only on the user's own acceptance; ops.json the run's players only, never merged with what was there.
Step 2 (the probe in it), without a game:
- The address check: a server whose ready names anything it listens on but 127.0.0.1 is stopped before any client
  joins, and so is one that names nothing; no ready in time stops it too.
- A server game: its start file says role server, its folder and mods/ are made before it starts, its command is the
  server's.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
import unittest

from fakeprobe import FakeProbe, inThread, readStartFile
from test_launcher import FORGE_VERSION, Fixture, sha1
from unittas.cache import Cache
from unittas.errors import LinkTimeout
from unittas.launcher import Missing, SERVER_MAIN, Sources, offlineId, serverCommand
from unittas.link import Listener
from unittas.servergame import EULA_URL, ServerGame, ServerSetupError, awaitServerReady, freePort, serverFiles
from unittas.wire import Role


def properties(folder: str) -> dict:
  with open(os.path.join(folder, 'server.properties'), encoding='utf-8') as file:
    pairs = [line.split('=', 1) for line in file.read().split('\n') if line and not line.startswith('#')]
  return {key: value for key, value in pairs}


class ServerCommandTests(unittest.TestCase):

  def setUp(self) -> None:
    self.scratch = tempfile.mkdtemp(prefix='unittas-servergame-')
    self.addCleanup(shutil.rmtree, self.scratch)
    self.fixture = Fixture()
    self.folder = os.path.join(self.scratch, 'server')
    self.java = os.path.join(self.scratch, 'java')

  def cache(self) -> Cache:
    return Cache(os.path.join(self.scratch, 'cache'), fetch=self.fixture.fetch)

  def classPath(self, launch) -> list:
    return launch.java[launch.java.index('-cp') + 1].split(os.pathsep)

  def test_from_the_gradle_cache_nothing_is_fetched(self) -> None:
    home = self.fixture.gradleHome(self.scratch)
    launch = serverCommand(self.folder, self.java, Sources(gradleHome=home, cache=self.cache()))
    self.assertEqual([], self.fixture.asked)
    self.assertEqual(['forge-%s-universal.jar' % FORGE_VERSION, 'launchwrapper-1.12.jar', 'guava-17.0.jar',
                      'scala-library-2.11.1.jar', 'only-1.0.jar', 'minecraft-1.7.10-server.jar'],
                     [os.path.basename(jar) for jar in self.classPath(launch)],
                     "the universal jar, the server's libraries in Forge's order, the server jar last; no client's")
    java = launch.java
    self.assertEqual(self.java, java[0])
    self.assertEqual(SERVER_MAIN, java[java.index('-cp') + 2])
    self.assertEqual('cpw.mods.fml.relauncher.ServerLaunchWrapper', SERVER_MAIN)
    self.assertEqual('nogui', java[-1])
    self.assertIn('-Xmx2G', java)
    self.assertEqual([], launch.natives, 'a server has no window: no natives')

  def test_its_memory_as_given(self) -> None:
    home = self.fixture.gradleHome(self.scratch)
    launch = serverCommand(self.folder, self.java, Sources(gradleHome=home), memory='1G')
    self.assertIn('-Xmx1G', launch.java)
    self.assertNotIn('-Xmx2G', launch.java)
    with self.assertRaises(ValueError):
      serverCommand(self.folder, self.java, Sources(gradleHome=home), memory='lots')

  def test_from_an_empty_cache_each_file_once(self) -> None:
    cache = self.cache()
    launch = serverCommand(self.folder, self.java, Sources(gradleHome=None, cache=cache))
    classPath = self.classPath(launch)
    self.assertEqual('1.7.10-server.jar', os.path.basename(classPath[-1]))
    with open(classPath[-1], 'rb') as file:
      self.assertEqual(sha1(b'the server jar'), sha1(file.read()))
    self.assertTrue(all(path.startswith(cache.root) for path in classPath), classPath)
    self.assertIn('https://launcher.mojang.com/server.jar', self.fixture.asked)
    self.assertNotIn('https://launcher.mojang.com/client.jar', self.fixture.asked, 'no client jar for a server')
    self.assertNotIn('clientonly', ' '.join(self.fixture.asked), "a client's library is no server's")
    self.assertTrue(all(url.startswith('https://') for url in self.fixture.asked), self.fixture.asked)
    asked = len(self.fixture.asked)
    self.assertEqual(launch.java, serverCommand(self.folder, self.java, Sources(gradleHome=None, cache=cache)).java)
    self.assertEqual(asked, len(self.fixture.asked), 'the second launch fetches nothing')

  def test_a_server_jar_whose_sha1_doesn_t_match_is_refused(self) -> None:
    self.fixture.served['https://launcher.mojang.com/server.jar'] = b'something else'
    with self.assertRaises(Missing) as raised:
      serverCommand(self.folder, self.java, Sources(gradleHome=None, cache=self.cache()))
    self.assertIn('server jar', str(raised.exception))

  def test_without_a_cache_the_server_jar_is_named(self) -> None:
    home = self.fixture.gradleHome(self.scratch)
    os.remove(os.path.join(home, 'caches', 'unimined', 'net', 'minecraft', 'minecraft', '1.7.10',
                           'minecraft-1.7.10-server.jar'))
    with self.assertRaises(Missing) as raised:
      serverCommand(self.folder, self.java, Sources(gradleHome=home))
    self.assertIn('1.7.10 server jar', str(raised.exception))


class ServerFilesTests(unittest.TestCase):

  def setUp(self) -> None:
    self.scratch = tempfile.mkdtemp(prefix='unittas-serverfiles-')
    self.addCleanup(shutil.rmtree, self.scratch)
    self.folder = os.path.join(self.scratch, 'server')

  def test_the_properties_listen_on_loopback_only(self) -> None:
    serverFiles(self.folder, 41300, ('alice', 'bob'), eula=True)
    said = properties(self.folder)
    self.assertEqual('127.0.0.1', said['server-ip'])
    self.assertEqual('41300', said['server-port'])
    self.assertEqual('false', said['online-mode'], 'a test client has no Mojang login')
    for port in ('enable-rcon', 'enable-query'):
      self.assertEqual('false', said[port], 'no other port opened: %s' % port)
    self.assertEqual('false', said['snooper-enabled'])
    for key, value in (('level-name', 'unittas'), ('level-type', 'FLAT'), ('generator-settings', '2;7,2x3,2;1;'),
                       ('level-seed', '20261029'), ('gamemode', '1'), ('force-gamemode', 'true'),
                       ('spawn-protection', '0'), ('allow-flight', 'true'), ('max-players', '8'), ('motd', 'unitTAS'),
                       ('player-idle-timeout', '0'), ('announce-player-achievements', 'false'),
                       ('enable-command-block', 'true'), ('difficulty', '1')):
      self.assertEqual(value, said.get(key), key)

  def test_written_fresh_never_merged(self) -> None:
    os.makedirs(self.folder)
    with open(os.path.join(self.folder, 'server.properties'), 'w', encoding='utf-8') as file:
      file.write('server-ip=0.0.0.0\nonline-mode=false\nenable-rcon=true\nrcon.password=x\n')
    with open(os.path.join(self.folder, 'ops.json'), 'w', encoding='utf-8') as file:
      json.dump([{'uuid': offlineId('mallory'), 'name': 'mallory', 'level': 4}], file)
    serverFiles(self.folder, 41301, ('alice',), eula=True)
    said = properties(self.folder)
    self.assertEqual('127.0.0.1', said['server-ip'])
    self.assertEqual('false', said['enable-rcon'])
    self.assertNotIn('rcon.password', said, 'nothing kept from the file before')
    with open(os.path.join(self.folder, 'ops.json'), encoding='utf-8') as file:
      ops = json.load(file)
    self.assertEqual(['alice'], [op['name'] for op in ops], "the run's players only, never merged")

  def test_ops_are_the_runs_players_by_their_offline_ids(self) -> None:
    serverFiles(self.folder, 41300, ('alice', 'bob'), eula=True)
    with open(os.path.join(self.folder, 'ops.json'), encoding='utf-8') as file:
      ops = json.load(file)
    self.assertEqual(['alice', 'bob'], [op['name'] for op in ops])
    hexId = offlineId('alice')
    self.assertEqual('%s-%s-%s-%s-%s' % (hexId[:8], hexId[8:12], hexId[12:16], hexId[16:20], hexId[20:]),
                     ops[0]['uuid'])
    self.assertEqual(4, ops[0]['level'])

  def test_the_eula_only_on_the_users_own_acceptance(self) -> None:
    with self.assertRaises(ServerSetupError) as raised:
      serverFiles(self.folder, 41300, ('alice',), eula=False)
    self.assertIn(EULA_URL, str(raised.exception))
    self.assertFalse(os.path.exists(os.path.join(self.folder, 'eula.txt')), 'nothing written for a refused server')
    self.assertFalse(os.path.exists(os.path.join(self.folder, 'server.properties')))
    serverFiles(self.folder, 41300, ('alice',), eula=True)
    with open(os.path.join(self.folder, 'eula.txt'), encoding='utf-8') as file:
      self.assertIn('eula=true', file.read().split('\n'))

  def test_a_player_name_the_game_wouldnt_take_is_refused(self) -> None:
    for name in ('', 'a' * 17, 'bob smith', 'bob\nop'):
      with self.assertRaises(ServerSetupError, msg=repr(name)):
        serverFiles(self.folder, 41300, ('alice', name), eula=True)

  def test_a_free_port_on_loopback(self) -> None:
    port = freePort()
    self.assertTrue(1024 < port < 65536, port)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
      probe.bind(('127.0.0.1', port))


class ListeningCheckTests(unittest.TestCase):
  """A fake dedicated server over a real connection, saying in its ready what it listens on."""

  def setUp(self) -> None:
    self.scratch = tempfile.mkdtemp(prefix='unittas-listening-')
    self.addCleanup(shutil.rmtree, self.scratch, True)
    self.listener = Listener()
    self.addCleanup(self.listener.close)
    expected = self.listener.prepare(self.scratch, 'server', Role.SERVER)
    self.fake = FakeProbe(expected.startFile)
    thread, _ = inThread(self.fake.connect)
    self.connection = self.listener.accept(timeout=10)
    thread.join(10)
    self.addCleanup(self.connection.close)
    self.addCleanup(self.fake.close)
    self.stops = []

  def ready(self, *listening) -> None:
    self.fake.event('ready', world='unittas', address=listening[0][0] if listening else None,
                    port=listening[0][1] if listening else None,
                    listening=[{'address': address, 'port': port} for address, port in listening], mods=[],
                    mixins={'applied': ['MixinDedicatedServer'], 'missing': []})

  def check(self, seconds: float = 5.0, since: int = 0):
    return awaitServerReady(self.connection, lambda: self.stops.append('stopped'), seconds, since)

  def test_loopback_alone_is_let_through(self) -> None:
    self.ready(('127.0.0.1', 41300))
    self.assertEqual('unittas', self.check()['world'])
    self.assertEqual([], self.stops)

  def test_loopback_through_an_ipv6_socket_is_let_through(self) -> None:
    self.ready(('::ffff:127.0.0.1', 41300))
    self.check()
    self.assertEqual([], self.stops)

  def test_any_other_address_stops_it(self) -> None:
    for listening in ((('0.0.0.0', 41300),), (('::', 41300),), (('192.168.1.20', 41300),),
                      (('127.0.0.1', 41300), ('0.0.0.0', 41301))):
      self.stops.clear()
      since = self.connection.events.mark()
      self.ready(*listening)
      with self.assertRaises(ServerSetupError, msg=repr(listening)) as raised:
        self.check(since=since)
      self.assertIn('127.0.0.1', str(raised.exception))
      self.assertIn('before any client joins', str(raised.exception))
      self.assertEqual(['stopped'], self.stops, 'stopped once: %r' % (listening,))

  def test_saying_nothing_it_listens_on_stops_it(self) -> None:
    self.ready()
    with self.assertRaises(ServerSetupError):
      self.check()
    self.assertEqual(['stopped'], self.stops)

  def test_no_ready_in_time_stops_it(self) -> None:
    with self.assertRaises(LinkTimeout):
      self.check(seconds=0.3)
    self.assertEqual(['stopped'], self.stops)


class ServerGameTests(unittest.TestCase):

  def setUp(self) -> None:
    self.scratch = tempfile.mkdtemp(prefix='unittas-servergame-launch-')
    self.addCleanup(shutil.rmtree, self.scratch, True)
    self.fixture = Fixture()
    self.home = self.fixture.gradleHome(self.scratch)
    self.folder = os.path.join(self.scratch, 'server')
    self.jars = []
    for name in ('unittas-0.1.0-dev9.jar', 'unimixins-1.7.10-0.3.1.jar'):
      path = os.path.join(self.scratch, name)
      with open(path, 'wb') as file:
        file.write(b'a mod')
      self.jars.append(path)

  def game(self, **given) -> ServerGame:
    arguments = dict(folder=self.folder, mods=self.jars, players=('alice', 'bob'), eula=True, memory='1G',
                     java=os.path.join(self.scratch, 'java'), sources=Sources(gradleHome=self.home))
    arguments.update(given)
    return ServerGame(self.scratch, os.path.join(self.scratch, 'results'), 'server', **arguments)

  def test_its_role_folder_and_command(self) -> None:
    game = self.game(port=41302)
    self.assertIs(Role.SERVER, game.role())
    self.assertEqual(self.folder, game.gameDir)
    self.assertEqual('server.log', game.outputName())
    self.assertEqual(serverCommand(self.folder, os.path.join(self.scratch, 'java'), Sources(gradleHome=self.home),
                                   '1G').java, game.command())
    os.makedirs(os.path.join(self.folder, 'mods'))
    with open(os.path.join(self.folder, 'mods', 'someone-elses.jar'), 'wb') as file:
      file.write(b'kept aside')
    game.prepare()
    self.assertEqual('41302', properties(self.folder)['server-port'])
    self.assertEqual(['unimixins-1.7.10-0.3.1.jar', 'unittas-0.1.0-dev9.jar'],
                     sorted(os.listdir(os.path.join(self.folder, 'mods'))))
    self.assertTrue(os.path.isfile(os.path.join(self.scratch, 'results', 'server', 'mods-before-this-run',
                                                'someone-elses.jar')), 'what mods/ held, kept aside')

  def test_a_free_port_unless_given(self) -> None:
    game = self.game()
    self.assertTrue(1024 < game.port < 65536)

  def test_its_start_file_says_server(self) -> None:
    game = self.game(port=41303)
    game.prepare()
    listener = Listener()
    self.addCleanup(listener.close)
    expected = listener.prepare(game.gameDir, game.name, game.role())
    self.assertEqual('server', readStartFile(expected.startFile)['role'])

  def test_the_eula_not_accepted_is_refused_before_anything(self) -> None:
    game = self.game(eula=False)
    with self.assertRaises(ServerSetupError):
      game.prepare()
    self.assertFalse(os.path.exists(os.path.join(self.folder, 'mods')))


if __name__ == '__main__':
  unittest.main()

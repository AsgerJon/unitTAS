"""
A modern dedicated server's launch and its folder (SPEC.md 19.7 step 10a),
with no game: 26.3 as Mojang ships it, its jars fake.
- the command: the version's server jar (its JSON's downloads.server, held
  to its sha1, into the download cache), run as its bundler runs (java
  -jar, nogui), the libraries it carries unpacked once into the download
  cache (bundlerRepoDir), on the version's own Java, its memory as asked,
  an agent before -jar with the server's folder its argument; a server
  obfuscated apart from its client, its own table of names (V21);
- the folder: server.properties as a modern server reads it: the flat test
  world by its layers (as JSON: bedrock, two dirt, grass, on plains), its
  game mode and difficulty by name, on 127.0.0.1 alone, no chat signing a
  test client can't do; 1.7.10's as before (test_servergame).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from test_modernlauncher import ModernFixture
from unittas.cache import Cache
from unittas.launcher import (FABRIC_SERVER_META, Missing, Sources,
                              serverVersionCommand)
from unittas.mojangnames import TABLE_FORMAT, TABLE_HEADER
from unittas.servergame import ServerGame, serverFiles
from unittas.versions import mavenPath
from unittas.wire import Role

SERVER = b'the 26.3 server jar: a bundler'
KNOT_SERVER = 'net.fabricmc.loader.impl.launch.knot.KnotServer'
#  a server's own obfuscation log, as Mojang writes one
SERVER_LOG = b"""\
# {"id":"com.android.tools.r8.mapping","version":"2.2"}
net.minecraft.server.MinecraftServer -> abc:
    void tickServer(java.util.function.BooleanSupplier) -> a
"""


def properties(folder: str) -> dict:
  """server.properties as the server reads it: key=value, # a comment."""
  with open(os.path.join(folder, 'server.properties'),
            encoding='utf-8') as file:
    lines = [line for line in file.read().splitlines()
             if line and not line.startswith('#')]
  return dict(line.split('=', 1) for line in lines)


class ModernServerCommandTests(unittest.TestCase):

  def setUp(self) -> None:
    self.scratch = tempfile.mkdtemp(prefix='unittas-modern-server-')
    self.addCleanup(shutil.rmtree, self.scratch)
    self.fixture = ModernFixture()
    self.fixture.withServer(SERVER)
    self.cache = Cache(os.path.join(self.scratch, 'cache'),
                       fetch=self.fixture.fetch)
    self.folder = os.path.join(self.scratch, 'server')
    self.java = os.path.join(self.scratch, 'java25', 'bin', 'java')

  def launch(self, **given):
    return serverVersionCommand(self.folder, self.java,
                                Sources(cache=self.cache), '26.3', **given)

  def test_the_command(self) -> None:
    java = self.launch(memory='3G', agents=('/agent.jar',)).java
    jar = self.cache.path('versions/26.3/server-26.3.jar')
    self.assertEqual(
      [self.java, '-Xmx3G',
       '-DbundlerRepoDir=' + self.cache.path('servers/26.3'),
       '-javaagent:/agent.jar=' + self.folder, '-jar', jar, 'nogui'], java)
    with open(jar, 'rb') as file:
      self.assertEqual(SERVER, file.read())

  def test_an_obfuscated_server_s_own_names(self) -> None:
    """
    A server obfuscated apart from its client (before 26.1; SPEC.md 19.7
    step 10, V21): its own table of names, from its server_mappings,
    written once into the download cache and named to the agent
    (-Dunittas.names) before it.
    """
    self.fixture.withServerMappings(SERVER_LOG)
    java = self.launch(agents=('/agent.jar',)).java
    table = self.cache.path('names/26.3-server-obfuscated-%s.txt' % TABLE_FORMAT)
    self.assertEqual('-Dunittas.names=' + table, java[3])
    self.assertEqual('-javaagent:/agent.jar=' + self.folder, java[4])
    with open(table, encoding='utf-8') as file:
      said = file.read().split('\n')
    self.assertEqual(TABLE_HEADER % ('obfuscated', '26.3'), said[0])
    self.assertIn('c\tnet/minecraft/server/MinecraftServer\tabc', said)

  def test_its_jar_held_to_its_sha1(self) -> None:
    url = self.fixture.vanilla['downloads']['server']['url']
    self.fixture.served[url] = b'not the server jar'
    with self.assertRaises(Missing):
      self.launch()

  def test_memory_as_xmx_takes_it(self) -> None:
    with self.assertRaises(ValueError):
      self.launch(memory='lots')

  def test_the_java_its_version_asks_for(self) -> None:
    os.makedirs(os.path.dirname(self.java))
    with open(self.java, 'w', encoding='utf-8') as file:
      file.write('#!/bin/sh\n')
    os.chmod(self.java, 0o755)
    java = serverVersionCommand(self.folder, None, Sources(cache=self.cache),
                                '26.3', javaCandidates={25: (self.java,)})
    self.assertEqual(self.java, java.java[0])


class FabricServerCommandTests(unittest.TestCase):
  """
  Fabric's dedicated server (SPEC.md 19.7 step 10f-i), its jars fake: its
  server profile from Fabric's meta server, its libraries and then the
  version's server jar on the class path, KnotServer (which runs the
  server's bundler itself), the client's table of names beside it.
  """

  def setUp(self) -> None:
    self.scratch = tempfile.mkdtemp(prefix='unittas-fabric-server-')
    self.addCleanup(shutil.rmtree, self.scratch)
    self.fixture = ModernFixture()
    self.fixture.withServer(SERVER)
    self.cache = Cache(os.path.join(self.scratch, 'cache'),
                       fetch=self.fixture.fetch)
    self.folder = os.path.join(self.scratch, 'server')
    self.java = os.path.join(self.scratch, 'java25', 'bin', 'java')

  def launch(self, **given):
    return serverVersionCommand(self.folder, self.java,
                                Sources(cache=self.cache), '26.3',
                                loader='fabric', loaderVersion='0.20.1',
                                **given)

  def test_the_command(self) -> None:
    java = self.launch(agents=('/agent.jar',)).java
    jar = self.cache.path('versions/26.3/server-26.3.jar')
    self.assertEqual(
      [self.java, '-Xmx2G',
       '-DbundlerRepoDir=' + self.cache.path('servers/26.3'),
       '-javaagent:/agent.jar=' + self.folder, '-cp'], java[:5])
    self.assertEqual([KNOT_SERVER, 'nogui'], java[6:])
    path = java[5].split(os.pathsep)
    self.assertEqual(jar, path[-1], 'the server jar last, as it is')
    profile = self.fixture.serverProfile['libraries']
    self.assertEqual(
      [self.cache.path('libraries/' + mavenPath(each['name']))
       for each in profile], path[:-1],
      "the server profile's libraries alone: none of the client's")
    with open(path[-2], 'rb') as file:
      self.assertEqual(b'a jar: net.fabricmc:fabric-loader:0.20.1',
                       file.read())

  def test_its_profile_kept_once(self) -> None:
    self.launch()
    meta = FABRIC_SERVER_META % ('26.3', '0.20.1')
    self.assertEqual(1, self.fixture.asked.count(meta))
    self.launch()
    self.assertEqual(1, self.fixture.asked.count(meta),
                     'fetched once, then the cache\'s')
    self.assertTrue(os.path.isfile(self.cache.path(
      'versions/fabric-loader-0.20.1-26.3/server-profile.json')))

  def test_a_profile_for_another_version_is_said(self) -> None:
    profile = dict(self.fixture.serverProfile, inheritsFrom='26.2')
    meta = FABRIC_SERVER_META % ('26.3', '0.20.1')
    self.fixture.served[meta] = json.dumps(profile).encode('utf-8')
    with self.assertRaises(Missing) as said:
      self.launch()
    self.assertIn('26.2', str(said.exception))

  def test_beside_fabric_the_client_s_intermediary_names(self) -> None:
    """
    A server's obfuscated names are its client's (SPEC.md 19.7 step 10f,
    checked on 1.21.1 and 1.20.1), so Fabric runs it under the same
    intermediary names: the agent is named the client's own table, not a
    server's (V26).
    """
    from test_intermediary import SUPERTYPES, TINY
    from test_mojangnames import LOG
    self.fixture.withMappings(LOG.encode('utf-8'))
    self.fixture.withServerMappings(SERVER_LOG)
    self.fixture.withIntermediary(TINY, SUPERTYPES)
    java = self.launch(agents=('/agent.jar',)).java
    table = self.cache.path('names/26.3-intermediary-%s.txt' % TABLE_FORMAT)
    self.assertEqual('-Dunittas.names=' + table, java[3])
    self.assertEqual('-javaagent:/agent.jar=' + self.folder, java[4])
    with open(table, encoding='utf-8') as file:
      self.assertEqual(TABLE_HEADER % ('intermediary', '26.3'),
                       file.readline().rstrip('\n'))
    plain = self.launch().java
    self.assertFalse([word for word in plain
                      if word.startswith('-Dunittas.names=')],
                     'no agent, no names')

  def test_a_loader_it_doesn_t_start_a_server_with(self) -> None:
    with self.assertRaises(ValueError) as said:
      serverVersionCommand(self.folder, self.java, Sources(cache=self.cache),
                           '26.3', loader='quilt', loaderVersion='1')
    self.assertIn('quilt', str(said.exception))


class ModernServerFilesTests(unittest.TestCase):

  def setUp(self) -> None:
    self.folder = tempfile.mkdtemp(prefix='unittas-modern-folder-')
    self.addCleanup(shutil.rmtree, self.folder)

  def test_the_flat_test_world_by_its_layers(self) -> None:
    serverFiles(self.folder, 25565, ['alice'], True, minecraft='26.3')
    said = properties(self.folder)
    self.assertEqual('minecraft:flat', said['level-type'])
    self.assertEqual({'layers': [
      {'block': 'minecraft:bedrock', 'height': 1},
      {'block': 'minecraft:dirt', 'height': 2},
      {'block': 'minecraft:grass_block', 'height': 1}],
      'biome': 'minecraft:plains'}, json.loads(said['generator-settings']))
    self.assertEqual('20261029', said['level-seed'])

  def test_1_16_1_s_flat_world_as_it_reads_it(self) -> None:
    """
    1.16.1's server (SPEC.md 19.7 step 11f) names a world type without a
    namespace (flat), and its flat layers' JSON needs its structures (none
    here), lakes and features said.
    """
    serverFiles(self.folder, 25565, ['alice'], True, minecraft='1.16.1')
    said = properties(self.folder)
    self.assertEqual('flat', said['level-type'])
    self.assertEqual({'structures': {'structures': {}},
                      'layers': [
                        {'block': 'minecraft:bedrock', 'height': 1},
                        {'block': 'minecraft:dirt', 'height': 2},
                        {'block': 'minecraft:grass_block', 'height': 1}],
                      'lakes': False, 'features': False,
                      'biome': 'minecraft:plains'},
                     json.loads(said['generator-settings']))
    self.assertEqual(('creative', 'easy', '127.0.0.1'),
                     (said['gamemode'], said['difficulty'], said['server-ip']))

  def test_by_name_on_loopback_alone(self) -> None:
    serverFiles(self.folder, 25565, ['alice'], True, minecraft='26.3')
    said = properties(self.folder)
    self.assertEqual(('creative', 'easy'),
                     (said['gamemode'], said['difficulty']))
    self.assertEqual(('127.0.0.1', '25565', 'false'),
                     (said['server-ip'], said['server-port'],
                      said['online-mode']))
    self.assertEqual('false', said['enforce-secure-profile'],
                     'a test client signs no chat')
    for gone in ('snooper-enabled', 'announce-player-achievements'):
      self.assertNotIn(gone, said, "1.7.10's, which a modern server hasn't")


class ModernServerGameTests(unittest.TestCase):
  """A modern server's launch with the probe, the agent its probe."""

  def setUp(self) -> None:
    self.scratch = tempfile.mkdtemp(prefix='unittas-modern-servergame-')
    self.addCleanup(shutil.rmtree, self.scratch)
    self.fixture = ModernFixture()
    self.fixture.withServer(SERVER)
    self.sources = Sources(cache=Cache(os.path.join(self.scratch, 'cache'),
                                       fetch=self.fixture.fetch))
    self.folder = os.path.join(self.scratch, 'server')
    self.java = os.path.join(self.scratch, 'java25', 'bin', 'java')

  def game(self) -> ServerGame:
    return ServerGame(self.scratch, os.path.join(self.scratch, 'results'),
                      'server', folder=self.folder, players=('alice',),
                      eula=True, memory='2G', java=self.java,
                      sources=self.sources, port=41305, minecraft='26.3',
                      probe='/agent.jar')

  def test_its_command_and_files(self) -> None:
    game = self.game()
    self.assertIs(Role.SERVER, game.role())
    self.assertEqual(serverVersionCommand(self.folder, self.java,
                                          self.sources, '26.3', '2G',
                                          agents=('/agent.jar',)).java,
                     game.command())
    game.prepare()
    said = properties(self.folder)
    self.assertEqual(('41305', 'minecraft:flat'),
                     (said['server-port'], said['level-type']))
    self.assertFalse(os.path.exists(os.path.join(self.folder, 'mods')),
                     'no mods/ for a vanilla server')

  def test_a_loader_s_server(self) -> None:
    """Fabric's (SPEC.md 19.7 step 10f-i): its launch, the agent in it."""
    game = ServerGame(self.scratch, os.path.join(self.scratch, 'results'),
                      'server', folder=self.folder, players=('alice',),
                      eula=True, memory='2G', java=self.java,
                      sources=self.sources, port=41305, minecraft='26.3',
                      probe='/agent.jar', loader='fabric',
                      loaderVersion='0.20.1')
    self.assertEqual(serverVersionCommand(self.folder, self.java,
                                          self.sources, '26.3', '2G',
                                          agents=('/agent.jar',),
                                          loader='fabric',
                                          loaderVersion='0.20.1').java,
                     game.command())


if __name__ == '__main__':
  unittest.main()

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
from unittas.launcher import Missing, Sources, serverVersionCommand
from unittas.mojangnames import TABLE_FORMAT, TABLE_HEADER
from unittas.servergame import ServerGame, serverFiles
from unittas.wire import Role

SERVER = b'the 26.3 server jar: a bundler'
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



if __name__ == '__main__':
  unittest.main()

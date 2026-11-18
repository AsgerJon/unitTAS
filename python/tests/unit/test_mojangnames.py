"""
Mojang's names for an obfuscated version (SPEC.md 19.7 step 6b), from
its obfuscation log (the version JSON's client_mappings), without a game
and without the network:
- the log read: each class, field and method by Mojang's name, keyed in
  the JVM's own terms (internal names, descriptors), to its obfuscated
  name; a name the game keeps (toString, a constructor, a kept class) is
  a line of its own;
- a descriptor turned into the running game's;
- a line it can't read, or one name given two ways, refused saying
  where;
- the table the agent reads written, the same bytes for the same log;
- the log fetched by the version JSON, held to its sha1; a version with
  none (26.1 on is unobfuscated) said.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest

from unittas.cache import Cache
from unittas.launcher import MANIFEST, Missing, Sources
from unittas.mojangnames import MojangNames

LOG = '''\
# (c) 2020 Microsoft Corporation. These mappings are provided "as-is".
# {"id":"com.android.tools.r8.mapping","version":"2.2"}
net.minecraft.client.Minecraft -> fgo:
# {"fileName":"Minecraft.java","id":"sourceFile"}
    net.minecraft.client.Minecraft instance -> E
    net.minecraft.client.player.LocalPlayer player -> s
    int[] counts -> q
    10:10:void <init>(net.minecraft.client.main.GameConfig) -> <init>
    1890:2012:void tick() -> t
    790:812:java.lang.String createTitle() -> bd
    void setScreen(net.minecraft.client.gui.screens.Screen) -> a
    java.lang.String toString() -> toString
    12:13:boolean[][] grid(long,double,net.minecraft.world.Box[]) -> a
net.minecraft.world.entity.Entity -> bvh:
    1:1:double getX() -> dt
net.minecraft.client.player.LocalPlayer -> gkx:
net.minecraft.client.main.Main -> net.minecraft.client.main.Main:
    void main(java.lang.String[]) -> main
net.minecraft.client.Minecraft$ChatStatus -> fgo$a:
    net.minecraft.client.Minecraft$ChatStatus ENABLED -> a
net.minecraft.client.gui.screens.Screen -> fod:
net.minecraft.client.main.GameConfig -> fva:
com.mojang.blaze3d.audio.package-info -> ezk:
'''
MINECRAFT = 'net/minecraft/client/Minecraft'


def sha1(data: bytes) -> str:
  return hashlib.sha1(data).hexdigest()


class ReadTests(unittest.TestCase):

  def setUp(self) -> None:
    self.names = MojangNames.fromText(LOG)

  def test_classes(self) -> None:
    self.assertEqual('fgo', self.names.classes[MINECRAFT])
    self.assertEqual('fgo$a', self.names.classes[MINECRAFT + '$ChatStatus'])
    self.assertEqual('net/minecraft/client/main/Main',
                     self.names.classes['net/minecraft/client/main/Main'],
                     'a class the game keeps by its name')
    self.assertEqual('ezk', self.names.classes[
      'com/mojang/blaze3d/audio/package-info'], "a package's own class")
    self.assertEqual(8, len(self.names.classes))

  def test_fields(self) -> None:
    fields = self.names.fields
    self.assertEqual('s', fields[(
      MINECRAFT, 'player', 'Lnet/minecraft/client/player/LocalPlayer;')])
    self.assertEqual('E', fields[(
      MINECRAFT, 'instance', 'Lnet/minecraft/client/Minecraft;')])
    self.assertEqual('q', fields[(MINECRAFT, 'counts', '[I')])
    self.assertEqual(4, len(fields))

  def test_methods(self) -> None:
    methods = self.names.methods
    self.assertEqual('t', methods[(MINECRAFT, 'tick', '()V')])
    self.assertEqual('bd', methods[(
      MINECRAFT, 'createTitle', '()Ljava/lang/String;')])
    self.assertEqual('a', methods[(
      MINECRAFT, 'grid', '(JD[Lnet/minecraft/world/Box;)[[Z')])
    self.assertEqual('a', methods[(
      MINECRAFT, 'setScreen',
      '(Lnet/minecraft/client/gui/screens/Screen;)V')])
    self.assertEqual('<init>', methods[(
      MINECRAFT, '<init>', '(Lnet/minecraft/client/main/GameConfig;)V')])
    self.assertEqual('toString', methods[(
      MINECRAFT, 'toString', '()Ljava/lang/String;')])
    self.assertEqual('dt', methods[(
      'net/minecraft/world/entity/Entity', 'getX', '()D')])
    self.assertEqual('main', methods[(
      'net/minecraft/client/main/Main', 'main', '([Ljava/lang/String;)V')])
    self.assertEqual(8, len(methods))

  def test_a_descriptor_as_the_game_runs(self) -> None:
    self.assertEqual('(Lfod;)V', self.names.running(
      '(Lnet/minecraft/client/gui/screens/Screen;)V'))
    self.assertEqual('(JD[Lbvh;Ljava/lang/String;)[[Lfgo$a;',
                     self.names.running(
                       '(JD[Lnet/minecraft/world/entity/Entity;'
                       'Ljava/lang/String;)[[Lnet/minecraft/client/'
                       'Minecraft$ChatStatus;'))
    self.assertEqual('Lfgo;', self.names.running(
      'Lnet/minecraft/client/Minecraft;'))

  def test_a_line_it_can_t_read_is_refused_saying_where(self) -> None:
    with self.assertRaises(ValueError) as said:
      MojangNames.fromText(LOG + '    void broken( -> x\n')
    self.assertIn('line 24', str(said.exception))
    with self.assertRaises(ValueError) as said:
      MojangNames.fromText('    void tick() -> t\n')
    self.assertIn('line 1', str(said.exception), 'a member with no class')

  def test_one_name_given_two_ways_is_refused(self) -> None:
    with self.assertRaises(ValueError) as said:
      MojangNames.fromText(LOG.replace(
        "    java.lang.String toString() -> toString\n",
        "    java.lang.String toString() -> toString\n"
        "    java.lang.String toString() -> b\n"))
    self.assertIn('toString', str(said.exception))


class TableTests(unittest.TestCase):

  def setUp(self) -> None:
    self.folder = tempfile.mkdtemp(prefix='unittas-names-')
    self.addCleanup(shutil.rmtree, self.folder, True)

  def written(self, name: str) -> str:
    path = os.path.join(self.folder, name)
    MojangNames.fromText(LOG).write(path, '1.21.1')
    with open(path, encoding='utf-8') as file:
      return file.read()

  def test_the_agent_s_table(self) -> None:
    lines = self.written('names.txt').splitlines()
    self.assertEqual('unittas-names\t1\tobfuscated\t1.21.1', lines[0])
    self.assertIn('c\t%s\tfgo' % MINECRAFT, lines)
    self.assertIn('c\t%s$ChatStatus\tfgo$a' % MINECRAFT, lines)
    self.assertIn('f\t%s\tplayer\tLnet/minecraft/client/player/'
                  'LocalPlayer;\ts' % MINECRAFT, lines)
    self.assertIn('m\t%s\ttick\t()V\tt' % MINECRAFT, lines)
    self.assertIn('m\tnet/minecraft/world/entity/Entity\tgetX\t()D\tdt',
                  lines)
    self.assertEqual(1 + 8 + 4 + 8, len(lines))
    self.assertEqual(sorted(lines[1:]), lines[1:], 'in a fixed order')

  def test_the_same_bytes_again(self) -> None:
    self.assertEqual(self.written('one.txt'), self.written('two.txt'))


class LoadTests(unittest.TestCase):
  """The log by the version JSON, as Mojang's servers serve them."""

  def setUp(self) -> None:
    self.folder = tempfile.mkdtemp(prefix='unittas-names-load-')
    self.addCleanup(shutil.rmtree, self.folder, True)
    self.log = LOG.encode('utf-8')
    self.version = {'id': '1.21.1', 'downloads': {'client_mappings': {
      'url': 'https://piston-data.mojang.com/client.txt',
      'sha1': sha1(self.log), 'size': len(self.log)}}}
    self.fetched = []

  def fetch(self, url: str) -> bytes:
    self.fetched.append(url)
    version = json.dumps(self.version).encode('utf-8')
    served = {
      MANIFEST: json.dumps({'versions': [
        {'id': '1.21.1', 'url': 'https://piston-meta.mojang.com/1.21.1.json',
         'sha1': sha1(version)}]}).encode('utf-8'),
      'https://piston-meta.mojang.com/1.21.1.json': version,
      'https://piston-data.mojang.com/client.txt': self.log}
    if url not in served:
      raise OSError('not served: ' + url)
    return served[url]

  def sources(self) -> Sources:
    return Sources(cache=Cache(os.path.join(self.folder, 'cache'),
                               fetch=self.fetch))

  def test_fetched_by_the_version_json_and_kept(self) -> None:
    names = MojangNames.load(self.sources(), '1.21.1')
    self.assertEqual('fgo', names.classes[MINECRAFT])
    MojangNames.load(self.sources(), '1.21.1')
    self.assertEqual(1, self.fetched.count(
      'https://piston-data.mojang.com/client.txt'), 'once, then kept')

  def test_a_log_whose_sha1_doesn_t_match_is_refused(self) -> None:
    self.version['downloads']['client_mappings']['sha1'] = '0' * 40
    with self.assertRaises(Missing):
      MojangNames.load(self.sources(), '1.21.1')

  def test_a_server_s_log_its_own(self) -> None:
    """
    A dedicated server's names (SPEC.md 19.7 step 10, V21): its own log
    (the version JSON's server_mappings), the server jar obfuscated apart
    from the client's; kept beside the client's, never in its place.
    """
    server = LOG.replace('-> bvh:', '-> zzq:').encode('utf-8')
    self.version['downloads']['server_mappings'] = {
      'url': 'https://piston-data.mojang.com/server.txt',
      'sha1': sha1(server), 'size': len(server)}
    fetch = self.fetch

    def withServer(url: str) -> bytes:
      if url == 'https://piston-data.mojang.com/server.txt':
        self.fetched.append(url)
        return server
      return fetch(url)

    self.fetch = withServer
    entity = 'net/minecraft/world/entity/Entity'
    self.assertEqual('zzq', MojangNames.load(self.sources(), '1.21.1',
                                             side='server').classes[entity])
    self.assertEqual('bvh', MojangNames.load(self.sources(),
                                             '1.21.1').classes[entity])
    MojangNames.load(self.sources(), '1.21.1', side='server')
    self.assertEqual(1, self.fetched.count(
      'https://piston-data.mojang.com/server.txt'), 'once, then kept')
    del self.version['downloads']['server_mappings']
    shutil.rmtree(os.path.join(self.folder, 'cache'))
    with self.assertRaises(Missing) as said:
      MojangNames.load(self.sources(), '1.21.1', side='server')
    self.assertIn('no server_mappings', str(said.exception))

  def test_a_version_with_no_log_is_said(self) -> None:
    del self.version['downloads']['client_mappings']
    with self.assertRaises(Missing) as said:
      MojangNames.load(self.sources(), '1.21.1')
    self.assertIn('no client_mappings', str(said.exception))


if __name__ == '__main__':
  unittest.main()

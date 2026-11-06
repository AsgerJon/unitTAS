"""
The launcher and its download cache (unittas.launcher, unittas.cache), without a game and without the network: a
fake fetcher serves the files. A 1.7.10 Forge client's command from the Gradle cache when it has the files, else from
the download cache, filled once and checked against each file's sha1. A file whose sha1 doesn't match is refused and
never kept; a half-written one is never used; Forge's old plain-HTTP maven is fetched over HTTPS; nothing is fetched
but over HTTPS.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
import unittest.mock
import zipfile

from unittas.cache import Cache, httpsFetch
from unittas.launcher import FORGE_SHA1_PINS, Missing, Sources, command, findJava, main, offlineId

FORGE_VERSION = '1.7.10-10.13.4.1614-1.7.10'


def sha1(data: bytes) -> str:
  return hashlib.sha1(data).hexdigest()


def jarBytes(name: str) -> bytes:
  return ('a jar: %s' % name).encode('utf-8')


def mavenPath(coordinates: str, classifier: str = '') -> str:
  group, artifact, version = coordinates.split(':')[:3]
  return '%s/%s/%s/%s-%s%s.jar' % (group.replace('.', '/'), artifact, version, artifact, version,
                                   '-' + classifier if classifier else '')


def nativesJar() -> bytes:
  out = io.BytesIO()
  with zipfile.ZipFile(out, 'w') as jar:
    jar.writestr('liblwjgl64.so', 'native code')
    jar.writestr('META-INF/MANIFEST.MF', 'Manifest-Version: 1.0\n')
  return out.getvalue()


class Fixture:
  """Mojang's and Forge's files for a small 1.7.10 Forge, as the servers would serve them, and as a Gradle cache holds them."""

  VANILLA_LIBRARIES = ('com.google.guava:guava:15.0', 'io.netty:netty-all:4.0.10.Final', 'org.lwjgl.lwjgl:lwjgl:2.9.1')
  FORGE_LIBRARIES = ('net.minecraft:launchwrapper:1.12', 'com.google.guava:guava:17.0',
                     'org.scala-lang:scala-library:2.11.1')

  def __init__(self) -> None:
    self.served = {}
    self.objects = {'a.png': b'an asset', 'sounds/b.ogg': b'another asset'}
    vanilla = {'id': '1.7.10', 'mainClass': 'net.minecraft.client.main.Main', 'assets': '1.7.10', 'libraries': []}
    for name in self.VANILLA_LIBRARIES:
      data = jarBytes(name)
      url = 'https://libraries.minecraft.net/' + mavenPath(name)
      self.served[url] = data
      vanilla['libraries'].append({'name': name, 'downloads': {'artifact': {
        'path': mavenPath(name), 'url': url, 'sha1': sha1(data), 'size': len(data)}}})
    natives = nativesJar()
    nativesUrl = 'https://libraries.minecraft.net/' + mavenPath('org.lwjgl.lwjgl:lwjgl-platform:2.9.1', 'natives-linux')
    self.served[nativesUrl] = natives
    vanilla['libraries'].append({
      'name': 'org.lwjgl.lwjgl:lwjgl-platform:2.9.1', 'natives': {'linux': 'natives-linux'},
      'extract': {'exclude': ['META-INF/']},
      'downloads': {'classifiers': {'natives-linux': {
        'path': mavenPath('org.lwjgl.lwjgl:lwjgl-platform:2.9.1', 'natives-linux'), 'url': nativesUrl,
        'sha1': sha1(natives), 'size': len(natives)}}}})
    vanilla['libraries'].append({'name': 'ca.weblite:java-objc-bridge:1.0',
                                 'rules': [{'action': 'allow', 'os': {'name': 'osx'}}]})
    client = b'the client jar'
    self.served['https://launcher.mojang.com/client.jar'] = client
    server = b'the server jar'
    self.served['https://launcher.mojang.com/server.jar'] = server
    vanilla['downloads'] = {'client': {'url': 'https://launcher.mojang.com/client.jar', 'sha1': sha1(client),
                                       'size': len(client)},
                            'server': {'url': 'https://launcher.mojang.com/server.jar', 'sha1': sha1(server),
                                       'size': len(server)}}
    index = json.dumps({'objects': {name: {'hash': sha1(data), 'size': len(data)}
                                    for name, data in self.objects.items()}}).encode('utf-8')
    self.served['https://launchermeta.mojang.com/indexes/1.7.10.json'] = index
    for data in self.objects.values():
      self.served['https://resources.download.minecraft.net/%s/%s' % (sha1(data)[:2], sha1(data))] = data
    vanilla['assetIndex'] = {'id': '1.7.10', 'url': 'https://launchermeta.mojang.com/indexes/1.7.10.json',
                             'sha1': sha1(index), 'size': len(index)}
    self.vanilla = vanilla
    versionJson = json.dumps(vanilla).encode('utf-8')
    self.served['https://piston-meta.mojang.com/v1/packages/x/1.7.10.json'] = versionJson
    self.served['https://piston-meta.mojang.com/mc/game/version_manifest_v2.json'] = json.dumps({'versions': [
      {'id': '1.7.10', 'url': 'https://piston-meta.mojang.com/v1/packages/x/1.7.10.json',
       'sha1': sha1(versionJson)}]}).encode('utf-8')
    forge = {
      'id': '1.7.10-Forge10.13.4.1614-1.7.10', 'mainClass': 'net.minecraft.launchwrapper.Launch',
      'minecraftArguments': '--username ${auth_player_name} --version ${version_name} --gameDir ${game_directory} '
                            '--assetsDir ${assets_root} --assetIndex ${assets_index_name} --uuid ${auth_uuid} '
                            '--accessToken ${auth_access_token} --userProperties ${user_properties} '
                            '--userType ${user_type} --tweakClass cpw.mods.fml.common.launcher.FMLTweaker',
      'libraries': [{'name': 'net.minecraftforge:forge:' + FORGE_VERSION, 'url': 'http://files.minecraftforge.net/maven/'}]}
    for name in self.FORGE_LIBRARIES:
      data = jarBytes(name)
      # as Forge's JSON marks them: every one of these is a server's too
      entry = {'name': name, 'serverreq': True}
      if name.startswith('org.scala-lang'):
        # as Forge's JSON has its Scala libraries: on its old maven, by plain HTTP, with their sha1s
        entry.update({'url': 'http://files.minecraftforge.net/maven/', 'checksums': [sha1(data)]})
        self.served['https://maven.minecraftforge.net/' + mavenPath(name)] = data
      else:
        url = 'https://libraries.minecraft.net/' + mavenPath(name)
        self.served[url] = data
        self.served[url + '.sha1'] = sha1(data).encode('ascii')
      forge['libraries'].append(entry)
    forge['libraries'].append({'name': 'some.server:only:1.0', 'clientreq': False, 'serverreq': True})
    onlyServer = jarBytes('some.server:only:1.0')
    self.served['https://libraries.minecraft.net/' + mavenPath('some.server:only:1.0')] = onlyServer
    self.served['https://libraries.minecraft.net/' + mavenPath('some.server:only:1.0') + '.sha1'] = sha1(
      onlyServer).encode('ascii')
    # a client's only (Forge's JSON gives no serverreq): never on a server's class path
    forge['libraries'].append({'name': 'some.client:clientonly:1.0', 'clientreq': True})
    self.served['https://libraries.minecraft.net/' + mavenPath('some.client:clientonly:1.0')] = jarBytes(
      'some.client:clientonly:1.0')
    self.served['https://libraries.minecraft.net/' + mavenPath('some.client:clientonly:1.0') + '.sha1'] = sha1(
      jarBytes('some.client:clientonly:1.0')).encode('ascii')
    universal = io.BytesIO()
    with zipfile.ZipFile(universal, 'w') as jar:
      jar.writestr('version.json', json.dumps(forge))
    self.universal = universal.getvalue()
    universalUrl = 'https://maven.minecraftforge.net/' + mavenPath('net.minecraftforge:forge:' + FORGE_VERSION,
                                                                    'universal')
    self.served[universalUrl] = self.universal
    self.served[universalUrl + '.sha1'] = sha1(self.universal).encode('ascii')
    self.asked = []

  def fetch(self, url: str) -> bytes:
    self.asked.append(url)
    if url not in self.served:
      raise OSError('404 for %s' % url)
    return self.served[url]

  def gradleHome(self, root: str, assets: bool = True) -> str:
    """A Gradle cache as unitTAS's build leaves it: Unimined's version JSON, client jar and assets, modules-2's jars."""
    home = os.path.join(root, 'gradle-home')
    unimined = os.path.join(home, 'caches', 'unimined', 'net', 'minecraft', 'minecraft', '1.7.10')
    os.makedirs(unimined)
    with open(os.path.join(unimined, 'version.json'), 'w', encoding='utf-8') as file:
      json.dump(self.vanilla, file)
    with open(os.path.join(unimined, 'minecraft-1.7.10-client.jar'), 'wb') as file:
      file.write(b'the client jar')
    with open(os.path.join(unimined, 'minecraft-1.7.10-server.jar'), 'wb') as file:
      file.write(b'the server jar')
    if assets:
      folder = os.path.join(home, 'caches', 'unimined', 'assets')
      os.makedirs(os.path.join(folder, 'indexes'))
      with open(os.path.join(folder, 'indexes', '1.7.10.json'), 'wb') as file:
        file.write(self.served['https://launchermeta.mojang.com/indexes/1.7.10.json'])
      for data in self.objects.values():
        objectPath = os.path.join(folder, 'objects', sha1(data)[:2], sha1(data))
        os.makedirs(os.path.dirname(objectPath), exist_ok=True)
        with open(objectPath, 'wb') as file:
          file.write(data)
    jars = [(name, '', jarBytes(name)) for name in self.VANILLA_LIBRARIES + self.FORGE_LIBRARIES +
            ('some.server:only:1.0', 'some.client:clientonly:1.0')]
    jars.append(('org.lwjgl.lwjgl:lwjgl-platform:2.9.1', 'natives-linux', nativesJar()))
    jars.append(('net.minecraftforge:forge:' + FORGE_VERSION, 'universal', self.universal))
    for name, classifier, data in jars:
      group, artifact, version = name.split(':')
      path = os.path.join(home, 'caches', 'modules-2', 'files-2.1', group, artifact, version, 'abc123',
                          os.path.basename(mavenPath(name, classifier)))
      os.makedirs(os.path.dirname(path), exist_ok=True)
      with open(path, 'wb') as file:
        file.write(data)
    return home


class LauncherTests(unittest.TestCase):

  def setUp(self) -> None:
    self.scratch = tempfile.mkdtemp(prefix='unittas-launcher-')
    self.addCleanup(shutil.rmtree, self.scratch)
    self.fixture = Fixture()
    self.game = os.path.join(self.scratch, 'game')
    self.java = os.path.join(self.scratch, 'java')

  def cache(self) -> Cache:
    return Cache(os.path.join(self.scratch, 'cache'), fetch=self.fixture.fetch)

  def names(self, launch) -> list:
    java = launch.java
    return [os.path.basename(jar) for jar in java[java.index('-cp') + 1].split(os.pathsep)]

  def test_from_the_gradle_cache_nothing_is_fetched(self) -> None:
    home = self.fixture.gradleHome(self.scratch)
    launch = command(self.game, self.java, Sources(gradleHome=home, cache=self.cache()))
    self.assertEqual([], self.fixture.asked)
    self.assertEqual(['forge-%s-universal.jar' % FORGE_VERSION, 'launchwrapper-1.12.jar', 'guava-17.0.jar',
                      'scala-library-2.11.1.jar', 'clientonly-1.0.jar', 'netty-all-4.0.10.Final.jar', 'lwjgl-2.9.1.jar',
                      'minecraft-1.7.10-client.jar'], self.names(launch))
    self.assertEqual(os.path.join(home, 'caches', 'unimined', 'assets'), launch.assets)
    self.assertEqual(self.java, launch.java[0])

  def test_from_an_empty_cache_each_file_once(self) -> None:
    cache = self.cache()
    launch = command(self.game, self.java, Sources(gradleHome=None, cache=cache))
    self.assertEqual(['forge-%s-universal.jar' % FORGE_VERSION, 'launchwrapper-1.12.jar', 'guava-17.0.jar',
                      'scala-library-2.11.1.jar', 'clientonly-1.0.jar', 'netty-all-4.0.10.Final.jar', 'lwjgl-2.9.1.jar', '1.7.10.jar'],
                     self.names(launch))
    classPath = launch.java[launch.java.index('-cp') + 1].split(os.pathsep)
    self.assertTrue(all(path.startswith(cache.root) for path in classPath), classPath)
    self.assertEqual(os.path.join(cache.root, 'assets'), launch.assets)
    for data in self.fixture.objects.values():
      self.assertTrue(os.path.isfile(os.path.join(launch.assets, 'objects', sha1(data)[:2], sha1(data))))
    self.assertTrue(all(url.startswith('https://') for url in self.fixture.asked), self.fixture.asked)
    self.assertIn('https://maven.minecraftforge.net/' + mavenPath('org.scala-lang:scala-library:2.11.1'),
                  self.fixture.asked, "Forge's old plain-HTTP maven is fetched over HTTPS")
    self.assertNotIn('some.server', ' '.join(self.fixture.asked), 'a server-only library is no client\'s')
    asked = len(self.fixture.asked)
    again = command(self.game, self.java, Sources(gradleHome=None, cache=cache))
    self.assertEqual(asked, len(self.fixture.asked), 'the second launch fetches nothing')
    self.assertEqual(launch.java, again.java)

  def test_the_gradle_cache_s_assets_incomplete_are_fetched(self) -> None:
    home = self.fixture.gradleHome(self.scratch, assets=False)
    launch = command(self.game, self.java, Sources(gradleHome=home, cache=self.cache()))
    self.assertTrue(launch.assets.startswith(os.path.join(self.scratch, 'cache')), launch.assets)
    self.assertTrue(all('resources.download.minecraft.net' in url or 'indexes' in url for url in self.fixture.asked),
                    self.fixture.asked)

  def test_a_sha1_that_doesn_t_match_is_refused_and_not_kept(self) -> None:
    url = 'https://libraries.minecraft.net/' + mavenPath('io.netty:netty-all:4.0.10.Final')
    self.fixture.served[url] = b'not what Mojang made'
    cache = self.cache()
    with self.assertRaises(Missing) as refused:
      command(self.game, self.java, Sources(gradleHome=None, cache=cache))
    self.assertIn('io.netty:netty-all:4.0.10.Final', str(refused.exception))
    self.assertIn('sha1', str(refused.exception))
    kept = os.path.join(cache.root, 'libraries', mavenPath('io.netty:netty-all:4.0.10.Final'))
    self.assertFalse(os.path.exists(kept))
    folder = os.path.dirname(kept)
    self.assertEqual([], [name for name in os.listdir(folder) if '.part' in name] if os.path.isdir(folder) else [])

  def test_a_half_written_file_is_never_used(self) -> None:
    cache = self.cache()
    kept = os.path.join(cache.root, 'libraries', mavenPath('io.netty:netty-all:4.0.10.Final'))
    os.makedirs(os.path.dirname(kept))
    with open(kept + '.part-12345', 'wb') as file:
      file.write(b'half a jar')
    command(self.game, self.java, Sources(gradleHome=None, cache=cache))
    with open(kept, 'rb') as file:
      self.assertEqual(jarBytes('io.netty:netty-all:4.0.10.Final'), file.read())

  def test_no_checksum_known_is_refused(self) -> None:
    url = 'https://libraries.minecraft.net/' + mavenPath('net.minecraft:launchwrapper:1.12') + '.sha1'
    del self.fixture.served[url]
    with self.assertRaises(Missing) as refused:
      command(self.game, self.java, Sources(gradleHome=None, cache=self.cache()))
    self.assertIn('net.minecraft:launchwrapper:1.12', str(refused.exception))
    self.assertIn('checksum', str(refused.exception))

  def test_a_stale_json_checksum_is_refused_unless_pinned(self) -> None:
    # Forge's 1.7.10 JSON pins two Scala jars at sha1s its maven no longer serves (found by the live download)
    name = 'org.scala-lang:scala-library:2.11.1'
    universal = zipfile.ZipFile(io.BytesIO(self.fixture.universal))
    forge = json.loads(universal.read('version.json'))
    for library in forge['libraries']:
      if library['name'] == name:
        library['checksums'] = ['0' * 40, '1' * 40]
    stale = io.BytesIO()
    with zipfile.ZipFile(stale, 'w') as jar:
      jar.writestr('version.json', json.dumps(forge))
    self.fixture.universal = stale.getvalue()
    universalUrl = 'https://maven.minecraftforge.net/' + mavenPath('net.minecraftforge:forge:' + FORGE_VERSION,
                                                                    'universal')
    self.fixture.served[universalUrl] = self.fixture.universal
    self.fixture.served[universalUrl + '.sha1'] = sha1(self.fixture.universal).encode('ascii')
    with self.assertRaises(Missing) as refused:
      command(self.game, self.java, Sources(gradleHome=None, cache=self.cache()))
    self.assertIn(name, str(refused.exception))
    with unittest.mock.patch.dict(FORGE_SHA1_PINS, {name: sha1(jarBytes(name))}):
      launch = command(self.game, self.java, Sources(gradleHome=None, cache=Cache(os.path.join(self.scratch, 'cache2'),
                                                                                  fetch=self.fixture.fetch)))
    self.assertIn('scala-library-2.11.1.jar', self.names(launch))

  def test_the_two_pins_are_the_jars_forge_serves(self) -> None:
    self.assertEqual({'org.scala-lang.plugins:scala-continuations-library_2.11:1.0.2':
                        '0e517c53a7e9acd6b1668c5a35eccbaa3bab9aac',
                      'org.scala-lang.plugins:scala-continuations-plugin_2.11.1:1.0.2':
                        'f361a3283452c57fa30c1ee69448995de23c60f7'}, FORGE_SHA1_PINS)

  def test_without_a_cache_what_the_gradle_cache_lacks_is_named(self) -> None:
    home = self.fixture.gradleHome(self.scratch)
    shutil.rmtree(os.path.join(home, 'caches', 'modules-2', 'files-2.1', 'io.netty'))
    with self.assertRaises(Missing) as refused:
      command(self.game, self.java, Sources(gradleHome=home, cache=None))
    self.assertIn('io.netty:netty-all:4.0.10.Final', str(refused.exception))
    self.assertEqual([], self.fixture.asked)

  def test_java_as_named_or_found(self) -> None:
    jdk = os.path.join(self.scratch, 'jdk8')
    binary = os.path.join(jdk, 'bin', 'java')
    os.makedirs(os.path.dirname(binary))
    with open(binary, 'w') as file:
      file.write('#!/bin/sh\n')
    os.chmod(binary, 0o755)
    self.assertEqual(binary, findJava(jdk), 'a JDK folder means its bin/java')
    self.assertEqual(binary, findJava(binary))
    self.assertEqual(binary, findJava(None, candidates=(os.path.join(self.scratch, 'nowhere'), binary)))
    with self.assertRaises(Missing) as missing:
      findJava(os.path.join(self.scratch, 'no-jdk'))
    self.assertIn('no-jdk', str(missing.exception))
    with self.assertRaises(Missing) as none:
      findJava(None, candidates=(os.path.join(self.scratch, 'a'), os.path.join(self.scratch, 'b')))
    self.assertIn(os.path.join(self.scratch, 'a'), str(none.exception))
    self.assertIn('Java 8', str(none.exception))
    self.assertIn('never downloaded', str(none.exception))

  def test_the_command_line_takes_a_java(self) -> None:
    home = self.fixture.gradleHome(self.scratch)
    java = os.path.join(self.scratch, 'jdk', 'bin', 'java')
    os.makedirs(os.path.dirname(java))
    with open(java, 'w') as file:
      file.write('#!/bin/sh\n')
    os.chmod(java, 0o755)
    printed = io.StringIO()
    with unittest.mock.patch('sys.stdout', printed):
      code = main('--game', self.game, '--dry-run', '--java', os.path.join(self.scratch, 'jdk'), gradleHome=home)
    self.assertEqual(0, code, printed.getvalue())
    self.assertTrue(printed.getvalue().startswith(java + ' '), printed.getvalue()[:200])

  def test_a_player_of_its_own(self) -> None:
    """The player's name, and the offline id it has, as the client is launched (SPEC.md 11.3, step 4)."""
    home = self.fixture.gradleHome(self.scratch)
    launch = command(self.game, self.java, Sources(gradleHome=home), username='bob')
    words = launch.java
    self.assertEqual('bob', words[words.index('--username') + 1])
    self.assertEqual(offlineId('bob'), words[words.index('--uuid') + 1])
    self.assertEqual('unitTAS', command(self.game, self.java, Sources(gradleHome=home)).java[
      words.index('--username') + 1], 'unitTAS unless told')
    for name in ('', 'bob smith', 'a' * 17):
      with self.assertRaises(ValueError, msg=repr(name)):
        command(self.game, self.java, Sources(gradleHome=home), username=name)
    printed = io.StringIO()
    with unittest.mock.patch('sys.stdout', printed):
      code = main('--game', self.game, '--dry-run', '--username', 'alice', gradleHome=home)
    self.assertEqual(0, code, printed.getvalue())
    self.assertIn('--username alice ', printed.getvalue())

  def test_https_only(self) -> None:
    for url in ('http://libraries.minecraft.net/x.jar', 'ftp://example.com/x', 'file:///etc/passwd'):
      with self.assertRaises(ValueError):
        httpsFetch(url)


if __name__ == '__main__':
  unittest.main()

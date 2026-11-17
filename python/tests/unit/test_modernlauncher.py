"""
The launcher for any version with a loader on top (SPEC.md 12.3, step 2): 26.3 with Fabric Loader 0.20.1, without a
game and without the network. The fixture is the real 26.3 version JSON and Fabric's real profile (fixtures/versions),
each jar in them replaced by fake bytes and its sha1 by theirs, served as Mojang's and Fabric's servers would:
- the command: Fabric's main class, its libraries then vanilla's for this system, the client jar last; the natives
  as jars on the class path; vanilla's JVM arguments then the loader's; the game's own memory flags replaced by the
  run's; the window's size; no placeholder left;
- each file fetched once, each held to its sha1 (the loader's own jar to its maven's .sha1), Fabric's profile kept
  whole; a file whose sha1 doesn't match is refused and never kept;
- the logging config by its argument; the Java the version needs.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import tempfile
import unittest

from unittas.cache import Cache
from unittas.launcher import FABRIC_META, MANIFEST, Missing, Sources, classPath, findJavaFor, main, versionCommand

VERSIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'versions')


def sha1(data: bytes) -> str:
  return hashlib.sha1(data).hexdigest()


def recorded(name: str) -> dict:
  with open(os.path.join(VERSIONS, name), encoding='utf-8') as file:
    return json.load(file)


class ModernFixture:
  """26.3 and Fabric Loader 0.20.1 as their servers would serve them, every jar fake and its sha1 its own."""

  def __init__(self) -> None:
    self.served = {}
    vanilla = copy.deepcopy(recorded('26.3.json'))
    for library in vanilla['libraries']:
      artifact = library['downloads']['artifact']
      data = ('a jar: %s' % library['name']).encode('utf-8')
      artifact.update({'sha1': sha1(data), 'size': len(data)})
      self.served[artifact['url']] = data
    client = b'the 26.3 client jar'
    vanilla['downloads']['client'].update({'sha1': sha1(client), 'size': len(client)})
    self.served[vanilla['downloads']['client']['url']] = client
    self.objects = {'minecraft/lang/en_us.json': b'{}', 'minecraft/sounds/x.ogg': b'a sound'}
    index = json.dumps({'objects': {name: {'hash': sha1(data), 'size': len(data)}
                                    for name, data in self.objects.items()}}).encode('utf-8')
    vanilla['assetIndex'].update({'sha1': sha1(index), 'size': len(index)})
    self.served[vanilla['assetIndex']['url']] = index
    for data in self.objects.values():
      self.served['https://resources.download.minecraft.net/%s/%s' % (sha1(data)[:2], sha1(data))] = data
    logging = b'<Configuration/>'
    vanilla['logging']['client']['file'].update({'sha1': sha1(logging), 'size': len(logging)})
    self.served[vanilla['logging']['client']['file']['url']] = logging
    self.vanilla = vanilla
    versionJson = json.dumps(vanilla).encode('utf-8')
    self.served['https://piston-meta.mojang.com/v1/packages/x/26.3.json'] = versionJson
    self.served[MANIFEST] = json.dumps({'versions': [
      {'id': '26.3', 'url': 'https://piston-meta.mojang.com/v1/packages/x/26.3.json', 'sha1': sha1(versionJson)}
    ]}).encode('utf-8')
    profile = copy.deepcopy(recorded('fabric-loader-0.20.1-26.3.json'))
    for library in profile['libraries']:
      group, artifact, version = library['name'].split(':')
      path = '%s/%s/%s/%s-%s.jar' % (group.replace('.', '/'), artifact, version, artifact, version)
      data = ('a jar: %s' % library['name']).encode('utf-8')
      url = library['url'].rstrip('/') + '/' + path
      self.served[url] = data
      if 'sha1' in library:
        library.update({'sha1': sha1(data), 'size': len(data)})
      else:
        # as Fabric's profile has the loader's own jar: no checksum there, its maven's .sha1 beside it
        self.served[url + '.sha1'] = sha1(data).encode('ascii')
    self.profile = profile
    self.served[FABRIC_META % ('26.3', '0.20.1')] = json.dumps(profile).encode('utf-8')
    self.asked = []

  def withMappings(self, log: bytes) -> None:
    """The version as an obfuscated one is served (before 26.1): its JSON names its obfuscation log."""
    url = 'https://piston-data.mojang.com/v1/objects/x/client.txt'
    self.vanilla['downloads']['client_mappings'] = {'sha1': sha1(log), 'size': len(log), 'url': url}
    self.served[url] = log
    versionJson = json.dumps(self.vanilla).encode('utf-8')
    self.served['https://piston-meta.mojang.com/v1/packages/x/26.3.json'] = versionJson
    self.served[MANIFEST] = json.dumps({'versions': [
      {'id': '26.3', 'url': 'https://piston-meta.mojang.com/v1/packages/x/26.3.json', 'sha1': sha1(versionJson)}
    ]}).encode('utf-8')

  def withIntermediary(self, tiny: str, classes: dict) -> None:
    """
    Fabric's profile with its intermediary jar (as for a version before 26.1), and the client jar as class files of
    those classes ({name: (superclass, interfaces)}), whose supertypes the names are composed along.
    """
    import io
    import zipfile
    from test_classheaders import classFile
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, 'w') as archive:
      archive.writestr('mappings/mappings.tiny', tiny)
    data = inner.getvalue()
    maven = 'https://maven.fabricmc.net/'
    self.served[maven + 'net/fabricmc/intermediary/26.3/intermediary-26.3.jar'] = data
    self.profile['libraries'].append({'name': 'net.fabricmc:intermediary:26.3', 'url': maven, 'sha1': sha1(data),
                                      'size': len(data)})
    self.served[FABRIC_META % ('26.3', '0.20.1')] = json.dumps(self.profile).encode('utf-8')
    client = io.BytesIO()
    with zipfile.ZipFile(client, 'w') as archive:
      for name, (superclass, interfaces) in classes.items():
        archive.writestr(name + '.class', classFile(name, superclass, interfaces))
    jar = client.getvalue()
    self.vanilla['downloads']['client'].update({'sha1': sha1(jar), 'size': len(jar)})
    self.served[self.vanilla['downloads']['client']['url']] = jar
    versionJson = json.dumps(self.vanilla).encode('utf-8')
    self.served['https://piston-meta.mojang.com/v1/packages/x/26.3.json'] = versionJson
    self.served[MANIFEST] = json.dumps({'versions': [
      {'id': '26.3', 'url': 'https://piston-meta.mojang.com/v1/packages/x/26.3.json', 'sha1': sha1(versionJson)}
    ]}).encode('utf-8')

  def fetch(self, url: str) -> bytes:
    self.asked.append(url)
    if url not in self.served:
      raise OSError('404 for %s' % url)
    return self.served[url]


class ModernLauncherTests(unittest.TestCase):

  def setUp(self) -> None:
    self.scratch = tempfile.mkdtemp(prefix='unittas-modern-')
    self.addCleanup(shutil.rmtree, self.scratch)
    self.fixture = ModernFixture()
    self.game = os.path.join(self.scratch, 'game')
    self.java = os.path.join(self.scratch, 'java25', 'bin', 'java')

  def sources(self) -> Sources:
    return Sources(cache=Cache(os.path.join(self.scratch, 'cache'), fetch=self.fixture.fetch))

  def launch(self, sources=None, **given):
    return versionCommand(self.game, self.java, sources or self.sources(), '26.3', 'fabric', '0.20.1', **given)

  def test_the_command(self) -> None:
    java = self.launch(memory='3G', width=640, height=360).java
    self.assertEqual(self.java, java[0])
    self.assertIn('net.fabricmc.loader.impl.launch.knot.KnotClient', java)
    main = java.index('net.fabricmc.loader.impl.launch.knot.KnotClient')
    jvm, game = java[1:main], java[main + 1:]
    self.assertFalse([word for word in java if '${' in word], 'no placeholder left')
    classPath = [os.path.basename(jar) for jar in jvm[jvm.index('-cp') + 1].split(os.pathsep)]
    self.assertEqual('asm-9.10.1.jar', classPath[0], "the loader's libraries first")
    self.assertIn('fabric-loader-0.20.1.jar', classPath)
    self.assertIn('lwjgl-sdl-3.4.3-natives-linux.jar', classPath)
    self.assertNotIn('lwjgl-sdl-3.4.3-natives-windows.jar', classPath)
    self.assertEqual('26.3.jar', classPath[-1], "the client jar last, as versions/26.3/26.3.jar (the vanilla launcher's way)")
    self.assertIn('-Djava.library.path=' + os.path.join(self.game, 'natives') + '/java', jvm)
    self.assertEqual('-DFabricMcEmu= net.minecraft.client.main.Main ', jvm[-1], "the loader's after vanilla's")
    self.assertIn('-Xmx3G', jvm)
    self.assertNotIn('-Xmx4G', jvm, "the version's own default memory replaced by the run's")
    self.assertIn('-XX:+UseZGC', jvm, "the version's own collector flags kept")
    pairs = dict(zip(game[::2], game[1::2]))
    self.assertEqual('unitTAS', pairs['--username'])
    self.assertEqual('fabric-loader-0.20.1-26.3', pairs['--version'])
    self.assertEqual(self.game, pairs['--gameDir'])
    self.assertEqual('34', pairs['--assetIndex'])
    self.assertEqual(('640', '360'), (pairs['--width'], pairs['--height']))
    self.assertNotIn('--demo', game)

  def test_vanilla_with_no_loader(self) -> None:
    """26.3 as Mojang ships it (SPEC.md 19.7 step 5): no loader, vanilla's own main class and libraries."""
    java = versionCommand(self.game, self.java, self.sources(), '26.3', None, None).java
    self.assertIn('net.minecraft.client.main.Main', java)
    main = java.index('net.minecraft.client.main.Main')
    jvm, game = java[1:main], java[main + 1:]
    classPath = [os.path.basename(jar) for jar in jvm[jvm.index('-cp') + 1].split(os.pathsep)]
    self.assertNotIn('fabric-loader-0.20.1.jar', classPath)
    self.assertNotIn('asm-9.10.1.jar', classPath, "no loader's libraries")
    self.assertEqual('26.3.jar', classPath[-1])
    self.assertFalse([word for word in jvm if 'Fabric' in word], "no loader's JVM arguments")
    pairs = dict(zip(game[::2], game[1::2]))
    self.assertEqual('26.3', pairs['--version'])

  def test_the_probe_as_a_java_agent(self) -> None:
    """The loader-free probe (SPEC.md 19.7 step 5): -javaagent:<its jar>=<the game folder>, before the main class."""
    probe = os.path.join(self.scratch, 'unittas-probe-26.3.jar')
    for loader, version, mainClass in ((None, None, 'net.minecraft.client.main.Main'),
                                       ('fabric', '0.20.1', 'net.fabricmc.loader.impl.launch.knot.KnotClient')):
      with self.subTest(loader=loader):
        java = versionCommand(self.game, self.java, self.sources(), '26.3', loader, version, agents=(probe,)).java
        agent = '-javaagent:%s=%s' % (probe, self.game)
        self.assertIn(agent, java)
        self.assertLess(java.index(agent), java.index(mainClass))

  def test_no_names_for_a_version_under_mojang_s_own(self) -> None:
    """26.x is unobfuscated: its JSON names no obfuscation log, and the agent is given no table of names."""
    probe = os.path.join(self.scratch, 'unittas-probe-26.3.jar')
    java = versionCommand(self.game, self.java, self.sources(), '26.3', None, None, agents=(probe,)).java
    self.assertFalse([word for word in java if word.startswith('-Dunittas.names=')])

  def test_an_obfuscated_version_s_names_for_the_agent(self) -> None:
    """
    Before 26.1 (SPEC.md 19.7 step 6b): the agent renames its probe by a table of the version's names, written once
    into the download cache from the version's obfuscation log, and named to it by -Dunittas.names before the agent.
    """
    from test_mojangnames import LOG
    self.fixture.withMappings(LOG.encode('utf-8'))
    probe = os.path.join(self.scratch, 'unittas-probe-x.jar')
    java = versionCommand(self.game, self.java, self.sources(), '26.3', None, None, agents=(probe,)).java
    table = os.path.join(self.scratch, 'cache', 'names', '26.3-obfuscated-1.txt')
    self.assertIn('-Dunittas.names=' + table, java)
    self.assertLess(java.index('-Dunittas.names=' + table), java.index('-javaagent:%s=%s' % (probe, self.game)))
    with open(table, encoding='utf-8') as file:
      self.assertEqual('unittas-names\t1\tobfuscated\t26.3\n', file.readline())
    again = versionCommand(self.game, self.java, self.sources(), '26.3', None, None, agents=(probe,)).java
    self.assertIn('-Dunittas.names=' + table, again)
    plain = versionCommand(self.game, self.java, self.sources(), '26.3', None, None).java
    self.assertFalse([word for word in plain if word.startswith('-Dunittas.names=')], 'no agent, no names')

  def test_beside_fabric_an_obfuscated_version_s_intermediary_names(self) -> None:
    """
    Fabric runs a version before 26.1 under intermediary names (SPEC.md 19.7 step 6d): the agent's table goes from
    Mojang's names through the obfuscated ones on to intermediary's, from the intermediary jar Fabric's profile names,
    an override by its root's name along the client jar's classes; written once, kept apart from vanilla's.
    """
    from test_intermediary import SUPERTYPES, TINY
    from test_mojangnames import LOG
    self.fixture.withMappings(LOG.encode('utf-8'))
    self.fixture.withIntermediary(TINY, SUPERTYPES)
    probe = os.path.join(self.scratch, 'unittas-probe-x.jar')
    java = versionCommand(self.game, self.java, self.sources(), '26.3', 'fabric', '0.20.1', agents=(probe,)).java
    table = os.path.join(self.scratch, 'cache', 'names', '26.3-intermediary-1.txt')
    self.assertIn('-Dunittas.names=' + table, java)
    with open(table, encoding='utf-8') as file:
      lines = file.read().splitlines()
    self.assertEqual('unittas-names\t1\tintermediary\t26.3', lines[0])
    self.assertIn('m\tnet/minecraft/client/Minecraft\ttick\t()V\tmethod_1574', lines)

  def test_beside_fabric_without_its_intermediary_jar_is_said(self) -> None:
    """A Fabric profile for an obfuscated version names its intermediary jar: one that doesn't is said, not guessed."""
    from test_mojangnames import LOG
    self.fixture.withMappings(LOG.encode('utf-8'))
    probe = os.path.join(self.scratch, 'unittas-probe-x.jar')
    with self.assertRaises(Missing) as said:
      versionCommand(self.game, self.java, self.sources(), '26.3', 'fabric', '0.20.1', agents=(probe,))
    self.assertIn('intermediary', str(said.exception))

  def test_the_class_path_to_compile_against(self) -> None:
    """The version's own libraries for this system and its client jar, each held to its sha1: what the agent's build
    compiles the probe against (SPEC.md 19.7 step 5)."""
    jars = classPath(self.sources(), '26.3')
    names = [os.path.basename(jar) for jar in jars]
    self.assertEqual('26.3.jar', names[-1])
    self.assertIn('lwjgl-sdl-3.4.3.jar', names)
    self.assertNotIn('fabric-loader-0.20.1.jar', names)
    self.assertTrue(all(os.path.isfile(jar) for jar in jars))

  def test_each_file_once_and_then_none(self) -> None:
    sources = self.sources()
    self.launch(sources)
    first = list(self.fixture.asked)
    self.assertEqual(len(first), len(set(first)), 'each fetched once')
    self.assertIn(FABRIC_META % ('26.3', '0.20.1'), first)
    loader = [url for url in first if url.endswith('fabric-loader-0.20.1.jar.sha1')]
    self.assertEqual(1, len(loader), "the loader's own jar held to its maven's .sha1")
    del self.fixture.asked[:]
    self.launch(sources)
    self.assertEqual([MANIFEST] if MANIFEST in self.fixture.asked else [], self.fixture.asked,
                     'all kept: nothing fetched again (at most the manifest, which is never kept)')

  def test_a_jar_whose_sha1_doesn_t_match_is_refused_and_not_kept(self) -> None:
    library = self.fixture.vanilla['libraries'][0]['downloads']['artifact']
    self.fixture.served[library['url']] = b'something else'
    with self.assertRaises(Missing) as refused:
      self.launch()
    self.assertIn('sha1', str(refused.exception))
    self.assertFalse(os.path.exists(os.path.join(self.scratch, 'cache', 'libraries', library['path'])))

  def test_the_logging_config(self) -> None:
    java = self.launch().java
    config = [word for word in java if word.startswith('-Dlog4j.configurationFile=')]
    self.assertEqual(1, len(config))
    with open(config[0].split('=', 1)[1], 'rb') as file:
      self.assertEqual(b'<Configuration/>', file.read())

  def test_the_java_it_needs_and_the_assets(self) -> None:
    launched = self.launch()
    self.assertEqual(25, launched.javaMajor)
    with open(os.path.join(launched.assets, 'indexes', '34.json'), 'rb') as file:
      self.assertIn(b'en_us.json', file.read())
    self.assertEqual((), tuple(launched.natives), 'nothing to extract: the natives are jars on the class path')

  def test_an_unknown_version_or_loader_is_said(self) -> None:
    with self.assertRaises(Missing) as unknown:
      versionCommand(self.game, self.java, self.sources(), '26.9', 'fabric', '0.20.1')
    self.assertIn('26.9', str(unknown.exception))
    with self.assertRaises(ValueError) as loader:
      versionCommand(self.game, self.java, self.sources(), '26.3', 'quilt', '1.0')
    self.assertIn('quilt', str(loader.exception))

  def test_the_java_named_by_the_version_when_none_is_given(self) -> None:
    java25 = os.path.join(self.scratch, 'jdk25', 'bin', 'java')
    os.makedirs(os.path.dirname(java25))
    with open(java25, 'w') as file:
      file.write('#!/bin/sh\n')
    os.chmod(java25, 0o755)
    launched = versionCommand(self.game, None, self.sources(), '26.3', 'fabric', '0.20.1',
                              javaCandidates={25: (java25,)})
    self.assertEqual(java25, launched.java[0], "26.3's JSON asks for Java 25")

  def test_a_java_by_its_major_version(self) -> None:
    java25 = os.path.join(self.scratch, 'jdk25', 'bin', 'java')
    os.makedirs(os.path.dirname(java25))
    with open(java25, 'w') as file:
      file.write('#!/bin/sh\n')
    os.chmod(java25, 0o755)
    self.assertEqual(java25, findJavaFor(25, {25: ('/no/such/java', java25)}))
    with self.assertRaises(Missing) as none:
      findJavaFor(21, {21: ('/no/such/java',)})
    self.assertIn('Java 21', str(none.exception))
    self.assertIn('/no/such/java', str(none.exception))

  def test_the_command_line(self) -> None:
    """bin/launch_client.py --minecraft 26.3 --loader fabric --loader-version 0.20.1, on a cache already filled."""
    cache = os.path.join(self.scratch, 'cache')
    os.makedirs(os.path.dirname(self.java))
    with open(self.java, 'w') as file:
      file.write('#!/bin/sh\n')
    os.chmod(self.java, 0o755)
    versionCommand(self.game, self.java, Sources(cache=Cache(cache, fetch=self.fixture.fetch)), '26.3', 'fabric',
                   '0.20.1')
    import contextlib
    import io
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
      code = main('--game', self.game, '--dry-run', '--no-gradle-cache', '--cache', cache, '--java', self.java,
                  '--minecraft', '26.3', '--loader', 'fabric', '--loader-version', '0.20.1', '--memory', '3G',
                  '--width', '640', '--height', '360')
    self.assertEqual(0, code, printed.getvalue())
    said = printed.getvalue()
    self.assertIn('net.fabricmc.loader.impl.launch.knot.KnotClient', said)
    self.assertIn('-Xmx3G', said)
    self.assertIn('--width 640', said)
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
      code = main('--game', self.game, '--dry-run', '--no-gradle-cache', '--cache', cache, '--java', self.java,
                  '--minecraft', '26.3', '--agent', '/opt/probe.jar')
    self.assertEqual(0, code, printed.getvalue())
    said = printed.getvalue()
    self.assertIn('net.minecraft.client.main.Main', said, 'no loader named: vanilla')
    self.assertIn('-javaagent:/opt/probe.jar=' + self.game, said)


if __name__ == '__main__':
  unittest.main()

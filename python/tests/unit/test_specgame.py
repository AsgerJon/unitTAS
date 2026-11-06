"""
Games from an instance spec (unittas.specgame), without a game: what a real client's launch puts in its folder (the
probe, the mods, the spec's file and maven libraries, its config and options), the commands both kinds run, and the
refusals: a mod jar older than its project's sources, a probe that isn't there.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import textwrap
import time
import unittest

from unittas.cache import Cache
from unittas.spec import InstanceSpec, SpecError
from unittas.specgame import GradleGame, RealGame, gameFor

LIBRARY = b'a library from a maven'
LIBRARY_URL = 'https://maven.example.com/repo/com/example/lib/1.0/lib-1.0.jar'


def touch(path: str, data: bytes = b'', age: float = 0.0) -> str:
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, 'wb') as file:
    file.write(data)
  when = time.time() - age
  os.utime(path, (when, when))
  return path


class SpecGameTests(unittest.TestCase):

  def setUp(self) -> None:
    self.folder = tempfile.mkdtemp(prefix='unittas-specgame-')
    self.addCleanup(shutil.rmtree, self.folder, True)
    self.results = os.path.join(self.folder, 'results')
    touch(os.path.join(self.folder, 'src', 'main', 'java', 'Mod.java'), b'class Mod {}', age=100)
    self.mod = touch(os.path.join(self.folder, 'build', 'libs', 'mod-1.0.jar'), b'the mod', age=10)
    self.probe = touch(os.path.join(self.folder, 'probe', 'unittas-probe.jar'), b'the probe', age=10)
    touch(os.path.join(self.folder, 'libs', 'unimixins.jar'), b'unimixins', age=10)
    touch(os.path.join(self.folder, 'test-config', 'mod.cfg'), b'B:fast=true\n')
    self.asked = []
    served = {LIBRARY_URL: LIBRARY, LIBRARY_URL + '.sha1': hashlib.sha1(LIBRARY).hexdigest().encode('ascii')}

    def fetch(url: str) -> bytes:
      self.asked.append(url)
      if url not in served:
        raise OSError('404 for %s' % url)
      return served[url]

    self.cache = Cache(os.path.join(self.folder, 'cache'), fetch=fetch)

  def spec(self, extra: str = '', client: str = 'real') -> InstanceSpec:
    path = os.path.join(self.folder, 'unittas.toml')
    with open(path, 'w', encoding='utf-8') as file:
      file.write(textwrap.dedent('''
        minecraft = "1.7.10"
        loader = { forge = "10.13.4.1614" }
        client = "%s"
      ''' % client) + textwrap.dedent(extra))
    return InstanceSpec.read(path)

  def realSpec(self, extra: str = '') -> InstanceSpec:
    return self.spec('''
      mods = ["build/libs/mod-*.jar"]
      libraries = ["libs/unimixins.jar", "maven:com.example:lib:1.0"]
      repositories = ["https://maven.example.com/repo/"]
      config = "test-config"
      options = { autoJump = false, renderDistance = 4 }
      probe = "probe/unittas-probe.jar"
      window = { display = "plain" }
    ''' + extra)

  def test_a_real_client_s_folder(self) -> None:
    game = RealGame(self.realSpec(), self.results, 'real', cache=self.cache)
    options = os.path.join(game.gameDir, 'options.txt')
    touch(options, b'autoJump:true\nfov:0.5\n')
    game.prepare()
    self.assertEqual(['lib-1.0.jar', 'mod-1.0.jar', 'unimixins.jar', 'unittas-probe.jar'],
                     sorted(os.listdir(os.path.join(game.gameDir, 'mods'))))
    self.assertEqual([LIBRARY_URL + '.sha1', LIBRARY_URL], self.asked)
    with open(os.path.join(game.gameDir, 'config', 'mod.cfg')) as file:
      self.assertEqual('B:fast=true\n', file.read())
    with open(options) as file:
      self.assertEqual(['autoJump:false', 'fov:0.5', 'renderDistance:4'], sorted(file.read().split()))

  def test_a_real_client_s_command(self) -> None:
    game = RealGame(self.realSpec('java = "/opt/jdk8"\n'), self.results, 'real', cache=self.cache)
    self.assertEqual([sys.executable, '-I', '-m', 'unittas.launcher', '--game', game.gameDir, '--cache', self.cache.root,
                      '--java', '/opt/jdk8'], game.command())
    self.assertEqual('client.log', game.outputName())

  def test_a_client_of_its_own_for_a_multiplayer_run(self) -> None:
    """Several real clients at once (SPEC.md 11.3, step 5): each its own folder and player; the server's mods."""
    spec = self.realSpec('''
      [server]
      exclude = ["unimix*.jar"]
    ''')
    bob = RealGame(spec, self.results, 'client-bob', cache=self.cache, folder=os.path.join(self.results, 'bob-game'),
                   username='bob')
    self.assertEqual(os.path.join(self.results, 'bob-game'), bob.gameDir)
    self.assertEqual(['--username', 'bob'], bob.command()[-2:])
    jars = [os.path.basename(jar) for jar in bob.modJars()]
    self.assertEqual(['lib-1.0.jar', 'mod-1.0.jar', 'unimixins.jar', 'unittas-probe.jar'], sorted(jars))
    self.assertEqual(['lib-1.0.jar', 'mod-1.0.jar', 'unittas-probe.jar'],
                     sorted(os.path.basename(jar) for jar in bob.serverMods()), 'the spec\'s [server] exclude left out')
    with self.assertRaises(ValueError):
      RealGame(spec, self.results, 'x', cache=self.cache, username='bob smith')

  def test_a_mod_jar_older_than_its_sources_is_refused(self) -> None:
    touch(os.path.join(self.folder, 'src', 'main', 'java', 'Mod.java'), b'class Mod { int changed; }')
    game = RealGame(self.realSpec(), self.results, 'real', cache=self.cache)
    with self.assertRaises(SpecError) as stale:
      game.prepare()
    self.assertIn('mod-1.0.jar', str(stale.exception))
    self.assertIn('older than', str(stale.exception))

  def test_the_build_runs_first(self) -> None:
    touch(os.path.join(self.folder, 'src', 'main', 'java', 'Mod.java'), b'class Mod { int changed; }')
    remake = "import os; os.utime(%r, None)" % self.mod
    game = RealGame(self.realSpec('build = "%s -c \\"%s\\""\n' % (sys.executable, remake)), self.results, 'real',
                    cache=self.cache)
    game.prepare()
    self.assertIn('mod-1.0.jar', os.listdir(os.path.join(game.gameDir, 'mods')))
    self.assertTrue(os.path.isfile(os.path.join(self.results, 'real', 'build.log')))

  def test_a_further_client_doesnt_build_again(self) -> None:
    """A multiplayer run's further client (built=True) takes the mods the run's own client built, as they are."""
    marker = os.path.join(self.results, 'builds.txt')
    spec = self.realSpec('build = "%s -c \\"open(%r, \'a\').write(\'b\')\\""\n' % (sys.executable, marker))
    RealGame(spec, self.results, 'real', cache=self.cache).prepare()
    bob = RealGame(spec, self.results, 'client-bob', cache=self.cache, folder=os.path.join(self.results, 'bob-game'),
                   username='bob', built=True)
    bob.prepare()
    with open(marker, encoding='ascii') as file:
      self.assertEqual('b', file.read(), 'built once, for the run\'s own client')
    self.assertIn('mod-1.0.jar', os.listdir(os.path.join(bob.gameDir, 'mods')))

  def test_a_build_that_fails_stops_the_launch(self) -> None:
    game = RealGame(self.realSpec('build = "%s -c \\"raise SystemExit(3)\\""\n' % sys.executable), self.results,
                    'real', cache=self.cache)
    with self.assertRaises(SpecError) as failed:
      game.prepare()
    self.assertIn('exit 3', str(failed.exception))

  def test_no_probe_bundled_says_so(self) -> None:
    game = RealGame(self.spec('mods = ["build/libs/mod-*.jar"]\nwindow = { display = "plain" }\n'), self.results,
                    'real', cache=self.cache, bundled=os.path.join(self.folder, 'no-probes-here'))
    with self.assertRaises(SpecError) as missing:
      game.prepare()
    self.assertIn('probe', str(missing.exception))

  def test_a_gradle_client(self) -> None:
    touch(os.path.join(self.folder, 'gradlew'), b'#!/bin/sh\n')
    with open(os.path.join(self.folder, 'gradle.properties'), 'w') as file:
      file.write('org.gradle.jvmargs=-Xmx3G\n')
    spec = self.spec('window = { display = "plain" }\n[gradle]\ntask = "runClient"\ngame = "run/client"\n',
                     client='gradle')
    game = gameFor(spec, self.results, 'dev')
    self.assertIsInstance(game, GradleGame)
    self.assertEqual(self.folder, game.workingDir())
    self.assertEqual(os.path.join(self.folder, 'run', 'client'), game.gameDir)
    self.assertEqual([os.path.join(self.folder, 'gradlew'), '--console=plain',
                      '-Dorg.gradle.jvmargs=-Xmx3G -Dunittas.daemon=desktop', 'runClient'], game.command())
    self.assertEqual('gradle.log', game.outputName())

  def test_the_display_goes_in_front(self) -> None:
    game = RealGame(self.realSpec().replace(display='headless'), self.results, 'real', cache=self.cache,
                    which=lambda name: '/usr/bin/gamescope' if name == 'gamescope' else None)
    self.assertEqual(['/usr/bin/gamescope', '--backend', 'headless'], game.command()[:3])


if __name__ == '__main__':
  unittest.main()

"""
Tests of bin/launch_client.py, unitTAS's own launcher for a real 1.7.10 Forge client: on a made-up Gradle cache (the
files the launcher looks for, empty jars and two version.json files), run as the scripts run it.

  python -m unittest discover -s bin/tests
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'launch_client.py')

VANILLA = {
  'id': '1.7.10', 'mainClass': 'net.minecraft.client.main.Main', 'assets': '1.7.10',
  'libraries': [
    {'name': 'com.google.guava:guava:15.0'},
    {'name': 'org.apache.commons:commons-lang3:3.1'},
    {'name': 'io.netty:netty-all:4.0.10.Final'},
    {'name': 'org.lwjgl.lwjgl:lwjgl:2.9.1', 'rules': [{'action': 'allow'}, {'action': 'disallow', 'os': {'name': 'osx'}}]},
    {'name': 'org.lwjgl.lwjgl:lwjgl-platform:2.9.1', 'natives': {'linux': 'natives-linux', 'osx': 'natives-osx'},
     'extract': {'exclude': ['META-INF/']}},
    {'name': 'tv.twitch:twitch-platform:5.16', 'natives': {'linux': 'natives-linux'},
     'rules': [{'action': 'allow'}, {'action': 'disallow', 'os': {'name': 'linux'}}]},
    {'name': 'ca.weblite:java-objc-bridge:1.0', 'rules': [{'action': 'allow', 'os': {'name': 'osx'}}]},
  ],
}
FORGE = {
  'id': '1.7.10-Forge10.13.4.1614-1.7.10', 'mainClass': 'net.minecraft.launchwrapper.Launch',
  'minecraftArguments': '--username ${auth_player_name} --version ${version_name} --gameDir ${game_directory} '
                        '--assetsDir ${assets_root} --assetIndex ${assets_index_name} --uuid ${auth_uuid} '
                        '--accessToken ${auth_access_token} --userProperties ${user_properties} '
                        '--userType ${user_type} --tweakClass cpw.mods.fml.common.launcher.FMLTweaker',
  'libraries': [
    {'name': 'net.minecraftforge:forge:1.7.10-10.13.4.1614-1.7.10'},
    {'name': 'net.minecraft:launchwrapper:1.12'},
    {'name': 'com.google.guava:guava:17.0'},
    {'name': 'org.apache.commons:commons-lang3:3.3.2'},
    {'name': 'org.scala-lang:scala-library:2.11.1', 'clientreq': True, 'serverreq': True},
    {'name': 'some.server:only:1.0', 'clientreq': False, 'serverreq': True},
  ],
}
JARS = [
  ('com.google.guava', 'guava', '15.0', ''), ('org.apache.commons', 'commons-lang3', '3.1', ''),
  ('io.netty', 'netty-all', '4.0.10.Final', ''), ('org.lwjgl.lwjgl', 'lwjgl', '2.9.1', ''),
  ('net.minecraft', 'launchwrapper', '1.12', ''), ('com.google.guava', 'guava', '17.0', ''),
  ('org.apache.commons', 'commons-lang3', '3.3.2', ''), ('org.scala-lang', 'scala-library', '2.11.1', ''),
]


def modulePath(cache: str, group: str, artifact: str, version: str, classifier: str) -> str:
  name = '%s-%s%s.jar' % (artifact, version, '-' + classifier if classifier else '')
  return os.path.join(cache, 'caches', 'modules-2', 'files-2.1', group, artifact, version, 'abc123', name)


class LauncherTests(unittest.TestCase):

  def setUp(self) -> None:
    self.root = tempfile.mkdtemp(prefix='launch-client-')
    self.addCleanup(shutil.rmtree, self.root)
    self.cache = os.path.join(self.root, 'gradle-home')
    self.game = os.path.join(self.root, 'game')
    unimined = os.path.join(self.cache, 'caches', 'unimined', 'net', 'minecraft', 'minecraft', '1.7.10')
    os.makedirs(unimined)
    with open(os.path.join(unimined, 'version.json'), 'w') as f:
      json.dump(VANILLA, f)
    self.client = os.path.join(unimined, 'minecraft-1.7.10-client.jar')
    open(self.client, 'w').close()
    os.makedirs(os.path.join(self.cache, 'caches', 'unimined', 'assets', 'indexes'))
    open(os.path.join(self.cache, 'caches', 'unimined', 'assets', 'indexes', '1.7.10.json'), 'w').close()
    for group, artifact, version, classifier in JARS:
      path = modulePath(self.cache, group, artifact, version, classifier)
      os.makedirs(os.path.dirname(path), exist_ok=True)
      open(path, 'w').close()
    self.forge = modulePath(self.cache, 'net.minecraftforge', 'forge', '1.7.10-10.13.4.1614-1.7.10', 'universal')
    os.makedirs(os.path.dirname(self.forge))
    with zipfile.ZipFile(self.forge, 'w') as jar:
      jar.writestr('version.json', json.dumps(FORGE))
    natives = modulePath(self.cache, 'org.lwjgl.lwjgl', 'lwjgl-platform', '2.9.1', 'natives-linux')
    os.makedirs(os.path.dirname(natives))
    with zipfile.ZipFile(natives, 'w') as jar:
      jar.writestr('liblwjgl64.so', 'native code')
      jar.writestr('META-INF/MANIFEST.MF', 'Manifest-Version: 1.0\n')
    # a java that writes down what it was given, for the runs that aren't dry
    self.java = os.path.join(self.root, 'java')
    with open(self.java, 'w') as f:
      f.write('#!/bin/sh\nprintf "%s\\n" "$@" > "' + os.path.join(self.root, 'java-args.txt') + '"\n')
    os.chmod(self.java, os.stat(self.java).st_mode | stat.S_IEXEC)

  def launch(self, *args: str):
    env = dict(os.environ, UNITTAS_GRADLE_HOME=self.cache, UNITTAS_JAVA8=self.java)
    return subprocess.run([sys.executable, '-I', SCRIPT, '--game', self.game, *args],
                          capture_output=True, text=True, env=env)

  def dryRun(self) -> list:
    result = self.launch('--dry-run')
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    return shlex.split(result.stdout.strip().split('\n')[-1])

  def classPath(self, command: list) -> list:
    return command[command.index('-cp') + 1].split(os.pathsep)

  def test_the_class_path(self) -> None:
    path = self.classPath(self.dryRun())
    names = [os.path.basename(jar) for jar in path]
    self.assertEqual(names, [
      'forge-1.7.10-10.13.4.1614-1.7.10-universal.jar', 'launchwrapper-1.12.jar', 'guava-17.0.jar',
      'commons-lang3-3.3.2.jar', 'scala-library-2.11.1.jar', 'netty-all-4.0.10.Final.jar', 'lwjgl-2.9.1.jar',
      'minecraft-1.7.10-client.jar',
    ])
    self.assertTrue(all(os.path.isabs(jar) for jar in path))

  def test_the_arguments(self) -> None:
    command = self.dryRun()
    self.assertEqual(command[0], self.java)
    main = command.index('net.minecraft.launchwrapper.Launch')
    self.assertIn('-Djava.library.path=' + os.path.join(self.game, 'natives'), command[:main])
    args = command[main + 1:]
    pairs = dict(zip(args[0::2], args[1::2]))
    self.assertEqual(pairs['--username'], 'unitTAS')
    self.assertEqual(pairs['--version'], '1.7.10-Forge10.13.4.1614-1.7.10')
    self.assertEqual(pairs['--gameDir'], self.game)
    self.assertEqual(pairs['--assetsDir'], os.path.join(self.cache, 'caches', 'unimined', 'assets'))
    self.assertEqual(pairs['--assetIndex'], '1.7.10')
    self.assertEqual(pairs['--tweakClass'], 'cpw.mods.fml.common.launcher.FMLTweaker')
    self.assertEqual(pairs['--accessToken'], '0')
    self.assertRegex(pairs['--uuid'], r'^[0-9a-f]{32}$')
    self.assertNotIn('${', ' '.join(args))

  def test_a_dry_run_changes_nothing(self) -> None:
    self.dryRun()
    self.assertFalse(os.path.exists(self.game))
    self.assertFalse(os.path.exists(os.path.join(self.root, 'java-args.txt')))

  def test_a_run_extracts_the_natives_and_starts_java(self) -> None:
    result = self.launch()
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertEqual(os.listdir(os.path.join(self.game, 'natives')), ['liblwjgl64.so'])
    with open(os.path.join(self.root, 'java-args.txt')) as f:
      given = f.read().split('\n')
    self.assertIn('net.minecraft.launchwrapper.Launch', given)
    self.assertIn('cpw.mods.fml.common.launcher.FMLTweaker', given)

  def test_a_missing_library_is_named(self) -> None:
    os.remove(modulePath(self.cache, 'io.netty', 'netty-all', '4.0.10.Final', ''))
    result = self.launch('--dry-run')
    self.assertEqual(result.returncode, 2)
    self.assertIn('io.netty:netty-all:4.0.10.Final', result.stdout + result.stderr)

  def test_no_cache(self) -> None:
    shutil.rmtree(self.cache)
    result = self.launch('--dry-run')
    self.assertEqual(result.returncode, 2)
    self.assertIn('./gradlew build', result.stdout + result.stderr)


if __name__ == '__main__':
  unittest.main()

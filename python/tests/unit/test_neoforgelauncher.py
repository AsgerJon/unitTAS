"""
The launcher beside NeoForge (SPEC.md 19.7 step 7a): 1.21.1 with NeoForge
21.1.267, without a game, without the network and without Java. The
fixtures are the real 1.21.1 version JSON and the version JSON NeoForge's
own installer writes, each jar in them fake and its sha1 its own, served
as Mojang's and NeoForge's servers would; NeoForge's installer is a fake
'java' that, run as the real one is ('-jar' it '--install-client'
FOLDER), refuses a folder without a launcher_profiles.json, as the real
one does, and else writes the version JSON and the patched client there:
- the installer fetched from NeoForge's maven, held to its .sha1, and run
  once into the download cache, on the version's Java; the folder's
  launcher_profiles.json written first; installed when the version JSON
  and the patched client its install profile names (PATCHED: NeoForge
  21.1's neoforge client, 26.x's minecraft-client-patched) are there;
- the command: NeoForge's main class (BootstrapLauncher), its module
  path's library folder the cache's, the client jar on the class path by
  the version's own name (which NeoForge's ignore list names), its game
  arguments; no placeholder left;
- every library from the download cache, never the Gradle cache's copy:
  NeoForge's module path names jars by their place in the library folder,
  and its BootstrapLauncher refuses a module on the class path from
  another file (found by the first game);
- no table of names beside it: NeoForge runs the game under Mojang's;
- an installer that fails, or a profile for another version, said and
  never taken as installed.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
import zipfile

from unittas.cache import Cache
from unittas.launcher import (MANIFEST, NEOFORGE_MAVEN, Missing, Sources,
                              versionCommand)

VERSIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'fixtures', 'versions')
NEOFORGE = '21.1.267'
NAME = 'neoforge-' + NEOFORGE
VANILLA_URL = 'https://piston-meta.mojang.com/v1/packages/x/1.21.1.json'
INSTALLER = NEOFORGE_MAVEN + '%s/neoforge-%s-installer.jar' % (NEOFORGE,
                                                             NEOFORGE)
PATCHED = 'libraries/net/neoforged/neoforge/%s/neoforge-%s-client.jar' % (
  NEOFORGE, NEOFORGE)

#  the installer's stand-in: run as 'java -jar INSTALLER --install-client
#  FOLDER', each call recorded beside it; it fails as the real one does
#  without the folder's launcher_profiles.json, or when told to ('fail'
#  beside it), and else writes the version JSON and the patched client
FAKE_JAVA = '''#!%(python)s
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, 'calls.txt'), 'a') as calls:
  calls.write(json.dumps(sys.argv[1:]) + '\\n')
if '--install-client' not in sys.argv:
  sys.exit(0)
root = sys.argv[sys.argv.index('--install-client') + 1]
if not os.path.isfile(os.path.join(root, 'launcher_profiles.json')):
  print('There is no minecraft launcher profile in ' + root)
  sys.exit(1)
if os.path.exists(os.path.join(here, 'fail')):
  print('Processor failed, invalid outputs')
  sys.exit(1)
folder = os.path.join(root, 'versions', %(name)r)
os.makedirs(folder, exist_ok=True)
with open(os.path.join(here, 'profile.json')) as given:
  profile = given.read()
with open(os.path.join(folder, %(name)r + '.json'), 'w') as written:
  written.write(profile)
with open(os.path.join(here, 'patched.txt')) as given:
  patched = os.path.join(root, given.read())
os.makedirs(os.path.dirname(patched), exist_ok=True)
with open(patched, 'wb') as written:
  written.write(b'the patched client')
'''


def sha1(data: bytes) -> str:
  return hashlib.sha1(data).hexdigest()


def recorded(name: str) -> dict:
  with open(os.path.join(VERSIONS, name), encoding='utf-8') as file:
    return json.load(file)


def installerJar(patched: str) -> bytes:
  """An installer jar: its install profile naming its patched client."""
  data = io.BytesIO()
  with zipfile.ZipFile(data, 'w') as jar:
    jar.writestr('install_profile.json', json.dumps(
      {'version': NAME, 'data': {'PATCHED': {'client': '[%s]' % patched,
                                             'server': '[%s]' % patched}}}))
  return data.getvalue()


def faked(libraries: list, served: dict) -> None:
  """Each library's jar fake, served at its url, its sha1 its own."""
  for library in libraries:
    artifact = library.get('downloads', {}).get('artifact')
    if not artifact:
      continue
    data = ('a jar: %s' % library['name']).encode('utf-8')
    artifact.update({'sha1': sha1(data), 'size': len(data)})
    served[artifact['url']] = data


class NeoForgeFixture:
  """1.21.1 and NeoForge 21.1.267 as their servers would serve them."""

  def __init__(self) -> None:
    self.served = {}
    vanilla = copy.deepcopy(recorded('1.21.1.json'))
    faked(vanilla['libraries'], self.served)
    client = b'the 1.21.1 client jar'
    vanilla['downloads']['client'].update(
      {'sha1': sha1(client), 'size': len(client)})
    self.served[vanilla['downloads']['client']['url']] = client
    index = json.dumps({'objects': {}}).encode('utf-8')
    vanilla['assetIndex'].update({'sha1': sha1(index), 'size': len(index)})
    self.served[vanilla['assetIndex']['url']] = index
    logging = b'<Configuration/>'
    vanilla['logging']['client']['file'].update(
      {'sha1': sha1(logging), 'size': len(logging)})
    self.served[vanilla['logging']['client']['file']['url']] = logging
    versionJson = json.dumps(vanilla).encode('utf-8')
    self.served[VANILLA_URL] = versionJson
    self.served[MANIFEST] = json.dumps({'versions': [
      {'id': '1.21.1', 'url': VANILLA_URL, 'sha1': sha1(versionJson)}
    ]}).encode('utf-8')
    self.profile = copy.deepcopy(recorded(NAME + '.json'))
    faked(self.profile['libraries'], self.served)
    self.serveInstaller('net.neoforged:neoforge:%s:client' % NEOFORGE)

  def serveInstaller(self, patched: str) -> None:
    """The installer, its install profile naming that patched client."""
    self.installer = installerJar(patched)
    self.served[INSTALLER] = self.installer
    self.served[INSTALLER + '.sha1'] = sha1(self.installer).encode('ascii')
    self.asked = []

  def fetch(self, url: str) -> bytes:
    self.asked.append(url)
    if url not in self.served:
      raise OSError('404 for %s' % url)
    return self.served[url]


class NeoForgeLauncherTests(unittest.TestCase):

  def setUp(self) -> None:
    self.scratch = tempfile.mkdtemp(prefix='unittas-neoforge-')
    self.addCleanup(shutil.rmtree, self.scratch)
    self.fixture = NeoForgeFixture()
    self.game = os.path.join(self.scratch, 'game')
    self.bin = os.path.join(self.scratch, 'java21', 'bin')
    os.makedirs(self.bin)
    self.java = os.path.join(self.bin, 'java')
    with open(self.java, 'w', encoding='utf-8') as file:
      file.write(FAKE_JAVA % {'python': sys.executable, 'name': NAME})
    os.chmod(self.java, os.stat(self.java).st_mode | stat.S_IXUSR)
    self.setProfile(self.fixture.profile)
    self.setPatched(PATCHED)
    self.cache = Cache(os.path.join(self.scratch, 'cache'),
                       fetch=self.fixture.fetch)

  def setProfile(self, profile: dict) -> None:
    """The version JSON the stand-in installer writes."""
    with open(os.path.join(self.bin, 'profile.json'), 'w',
              encoding='utf-8') as file:
      json.dump(profile, file)

  def setPatched(self, relative: str) -> None:
    """Where the stand-in installer writes the patched client."""
    with open(os.path.join(self.bin, 'patched.txt'), 'w',
              encoding='utf-8') as file:
      file.write(relative)

  def calls(self) -> list:
    path = os.path.join(self.bin, 'calls.txt')
    if not os.path.isfile(path):
      return []
    with open(path, encoding='utf-8') as file:
      return [json.loads(line) for line in file]

  def launch(self, gradleHome: str = None, **given):
    return versionCommand(self.game, self.java,
                          Sources(gradleHome=gradleHome, cache=self.cache),
                          '1.21.1', 'neoforge', NEOFORGE, **given)

  def test_installed_once_by_its_own_installer(self) -> None:
    self.launch()
    installer = self.cache.path(
      'libraries/net/neoforged/neoforge/%s/%s-installer.jar'
      % (NEOFORGE, NAME))
    self.assertEqual([['-jar', installer, '--install-client',
                       self.cache.path('')]], self.calls())
    self.assertIn(INSTALLER + '.sha1', self.fixture.asked,
                  'held to its maven sha1')
    with open(self.cache.path('launcher_profiles.json'),
              encoding='utf-8') as file:
      self.assertIn('profiles', json.load(file))
    self.launch()
    self.assertEqual(1, len(self.calls()), 'installed once')

  def test_installed_by_the_patched_client_its_profile_names(self) -> None:
    """26.x's installer makes minecraft-client-patched instead."""
    coordinates = 'net.neoforged:minecraft-client-patched:%s' % NEOFORGE
    self.fixture.serveInstaller(coordinates)
    self.setPatched('libraries/net/neoforged/minecraft-client-patched/'
                    '%s/minecraft-client-patched-%s.jar'
                    % (NEOFORGE, NEOFORGE))
    self.launch()
    self.launch()
    self.assertEqual(1, len(self.calls()), 'installed once')

  def test_the_command(self) -> None:
    java = self.launch(memory='3G').java
    main = java.index('cpw.mods.bootstraplauncher.BootstrapLauncher')
    jvm, game = java[1:main], java[main + 1:]
    self.assertFalse([word for word in java if '${' in word],
                     'no placeholder left')
    modules = jvm[jvm.index('-p') + 1].split(os.pathsep)
    self.assertTrue(all(each.startswith(self.cache.path('libraries'))
                        for each in modules), modules)
    self.assertIn('-DignoreList=client-extra,%s.jar' % NAME, jvm)
    classPath = jvm[jvm.index('-cp') + 1].split(os.pathsep)
    self.assertEqual(self.cache.path('versions/%s/%s.jar' % (NAME, NAME)),
                     classPath[-1], "the client by the version's own name")
    with open(classPath[-1], 'rb') as file:
      self.assertEqual(b'the 1.21.1 client jar', file.read())
    pairs = dict(zip(game[::2], game[1::2]))
    self.assertEqual(NAME, pairs['--version'])
    self.assertEqual(NEOFORGE, pairs['--fml.neoForgeVersion'])
    self.assertEqual('forgeclient', pairs['--launchTarget'])

  def test_every_library_from_the_library_folder(self) -> None:
    home = os.path.join(self.scratch, 'gradle-home')
    held = os.path.join(home, 'caches', 'modules-2', 'files-2.1',
                        'org.ow2.asm', 'asm-commons', '9.10.1', 'abc',
                        'asm-commons-9.10.1.jar')
    os.makedirs(os.path.dirname(held))
    open(held, 'wb').close()
    java = self.launch(gradleHome=home).java
    main = java.index('cpw.mods.bootstraplauncher.BootstrapLauncher')
    jvm = java[1:main]
    classPath = jvm[jvm.index('-cp') + 1].split(os.pathsep)
    modules = jvm[jvm.index('-p') + 1].split(os.pathsep)
    commons = [each for each in modules
               if each.endswith('asm-commons-9.10.1.jar')]
    self.assertEqual(1, len(commons), modules)
    self.assertTrue(commons[0] in classPath,
                    'the same file on the module path and the class path')
    self.assertFalse(held in classPath, "not the Gradle cache's copy")

  def test_no_table_of_names_beside_neoforge(self) -> None:
    """Its installer renames the game by Mojang's names: none to give."""
    vanilla = recorded('1.21.1.json')
    self.assertIn('client_mappings', vanilla['downloads'],
                  '1.21.1 itself is obfuscated')
    java = self.launch(agents=('/agent.jar',)).java
    self.assertIn('-javaagent:/agent.jar=' + self.game, java)
    self.assertFalse([word for word in java if 'unittas.names' in word])

  def test_an_installer_that_fails_is_said(self) -> None:
    open(os.path.join(self.bin, 'fail'), 'w').close()
    with self.assertRaises(Missing) as failed:
      self.launch()
    self.assertIn("NeoForge %s's installer" % NEOFORGE,
                  str(failed.exception))
    log = self.cache.path('versions/%s/install.log' % NAME)
    self.assertIn(log, str(failed.exception))
    with open(log, encoding='utf-8') as file:
      self.assertIn('Processor failed', file.read())
    os.remove(os.path.join(self.bin, 'fail'))
    self.launch()
    self.assertEqual(2, len(self.calls()), 'not taken as installed')

  def test_its_installer_held_to_its_sha1(self) -> None:
    self.fixture.served[INSTALLER] = installerJar('not:the:installer')
    with self.assertRaises(Missing) as refused:
      self.launch()
    self.assertIn('sha1', str(refused.exception))
    self.assertEqual([], self.calls(), 'never run')

  def test_a_profile_for_another_version_is_refused(self) -> None:
    other = copy.deepcopy(self.fixture.profile)
    other['inheritsFrom'] = '26.3'
    self.setProfile(other)
    with self.assertRaises(Missing) as refused:
      self.launch()
    self.assertIn('26.3', str(refused.exception))


if __name__ == '__main__':
  unittest.main()

"""
The launcher beside Forge on 1.16.1 (SPEC.md 19.7 step 11e): Forge 32.0.108,
without a game, the network or Java, as 1.20.1's Forge is
(test_forgelauncher). The fixtures are the real 1.16.1 version JSON and the
version JSON Forge's own installer writes, each jar in them fake; the
installer a fake 'java' run as the real one is ('-jar' it '--installClient'
FOLDER), which writes the version JSON, the patched client, the MCP
config's names (MAPPINGS, tsrg v1 before 1.17) and Forge's own jar (its
version JSON gives it no URL: the installer carries it):
- installed once by its installer, on the version's Java;
- the command: ModLauncher with Forge's game arguments (fmlclient), every
  library from the download cache's libraries/, where FML looks for them
  (from ModLauncher's own jar), never from a Gradle cache that has one;
- beside Forge the agent's table goes on to MCP's class names and SRG's
  members, as Forge ran the game before 1.17.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import copy
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
import zipfile

from test_mojangnames import LOG
from test_neoforgelauncher import recorded, sha1
from test_srgnames import TSRG1
from unittas.cache import Cache
from unittas.launcher import FORGE_MAVEN, MANIFEST, Sources, versionCommand

MINECRAFT = '1.16.1'
FORGE = '32.0.108'
NAME = '1.16.1-forge-' + FORGE
VANILLA_URL = 'https://piston-meta.mojang.com/v1/packages/x/1.16.1.json'
INSTALLER = FORGE_MAVEN + (
  'net/minecraftforge/forge/1.16.1-%s/forge-1.16.1-%s-installer.jar'
  % (FORGE, FORGE))
PATCHED = ('libraries/net/minecraftforge/forge/1.16.1-%s/'
           'forge-1.16.1-%s-client.jar' % (FORGE, FORGE))
MAPPINGS = ('libraries/de/oceanlabs/mcp/mcp_config/1.16.1-20200625.160719/'
            'mcp_config-1.16.1-20200625.160719-mappings.txt')

#  Forge's installer, faked: it writes each file it was given, as the real
#  one's install does
FAKE_JAVA = '''#!%(python)s
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, 'calls.txt'), 'a') as calls:
  calls.write(json.dumps(sys.argv[1:]) + '\\n')
if '--installClient' not in sys.argv:
  sys.exit(2)
root = sys.argv[sys.argv.index('--installClient') + 1]
if not os.path.isfile(os.path.join(root, 'launcher_profiles.json')):
  sys.exit(1)
with open(os.path.join(here, 'writes.json')) as given:
  writes = json.load(given)
for relative, data in writes.items():
  target = os.path.join(root, relative)
  os.makedirs(os.path.dirname(target), exist_ok=True)
  with open(target, 'wb') as written:
    written.write(data.encode('utf-8'))
'''


def fakedAll(libraries: list, served: dict, carried: dict) -> None:
  """
  Each library's jar fake, its sha1 its own: served at its URL, a natives
  jar too; one with no URL (Forge's own) kept in 'carried', which the
  installer writes, by its path.
  """
  for library in libraries:
    downloads = library.get('downloads', {})
    artifacts = [downloads['artifact']] if downloads.get('artifact') else []
    artifacts += list(downloads.get('classifiers', {}).values())
    for artifact in artifacts:
      text = 'a jar: %s %s' % (library['name'], artifact['path'])
      data = text.encode('utf-8')
      artifact.update({'sha1': sha1(data), 'size': len(data)})
      if artifact.get('url'):
        served[artifact['url']] = data
      else:
        carried['libraries/' + artifact['path']] = text


def installerJar() -> bytes:
  """Forge's installer: its install profile, as the real one's names."""
  data = io.BytesIO()
  with zipfile.ZipFile(data, 'w') as jar:
    named = {
      'PATCHED': {'client': '[net.minecraftforge:forge:1.16.1-%s:client]'
                            % FORGE},
      'MAPPINGS': {'client': '[de.oceanlabs.mcp:mcp_config:'
                             '1.16.1-20200625.160719:mappings@txt]'}}
    jar.writestr('install_profile.json',
                 json.dumps({"version": NAME, "data": named}))
  return data.getvalue()


class Forge1161LauncherTests(unittest.TestCase):

  def setUp(self) -> None:
    self.scratch = tempfile.mkdtemp(prefix='unittas-forge1161-')
    self.addCleanup(shutil.rmtree, self.scratch)
    self.served = {}
    carried = {}
    vanilla = copy.deepcopy(recorded('1.16.1.json'))
    fakedAll(vanilla['libraries'], self.served, carried)
    for name, data in (('client', b'the 1.16.1 client jar'),
                       ('client_mappings', LOG.encode('utf-8'))):
      vanilla['downloads'][name].update({'sha1': sha1(data),
                                         'size': len(data)})
      self.served[vanilla['downloads'][name]['url']] = data
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
      {'id': MINECRAFT, 'url': VANILLA_URL, 'sha1': sha1(versionJson)}
    ]}).encode('utf-8')
    profile = copy.deepcopy(recorded(NAME + '.json'))
    fakedAll(profile['libraries'], self.served, carried)
    self.assertTrue(carried, "Forge's own jar has no URL: its installer carries it")
    installer = installerJar()
    self.served[INSTALLER] = installer
    self.served[INSTALLER + '.sha1'] = sha1(installer).encode('ascii')
    self.bin = os.path.join(self.scratch, 'java8', 'bin')
    os.makedirs(self.bin)
    writes = dict(carried)
    writes.update({'versions/%s/%s.json' % (NAME, NAME): json.dumps(profile),
                   PATCHED: 'the patched client', MAPPINGS: TSRG1})
    with open(os.path.join(self.bin, 'writes.json'), 'w', encoding='utf-8') as file:
      json.dump(writes, file)
    self.java = os.path.join(self.bin, 'java')
    with open(self.java, 'w', encoding='utf-8') as file:
      file.write(FAKE_JAVA % {'python': sys.executable})
    os.chmod(self.java, os.stat(self.java).st_mode | stat.S_IXUSR)
    self.cache = Cache(os.path.join(self.scratch, 'cache'), fetch=self.fetch)
    self.game = os.path.join(self.scratch, 'game')

  def fetch(self, url: str) -> bytes:
    if url not in self.served:
      raise OSError('404 for %s' % url)
    return self.served[url]

  def calls(self) -> list:
    path = os.path.join(self.bin, 'calls.txt')
    if not os.path.isfile(path):
      return []
    with open(path, encoding='utf-8') as file:
      return [json.loads(line) for line in file]

  def launch(self, gradleHome=None, **given):
    return versionCommand(self.game, self.java,
                          Sources(gradleHome=gradleHome, cache=self.cache),
                          MINECRAFT, 'forge', FORGE, **given)

  def test_installed_once_by_forge_s_installer(self) -> None:
    self.launch()
    installer = self.cache.path(
      'libraries/net/minecraftforge/forge/1.16.1-%s/'
      'forge-1.16.1-%s-installer.jar' % (FORGE, FORGE))
    self.assertEqual([['-jar', installer, '--installClient',
                       self.cache.path('')]], self.calls())
    self.launch()
    self.assertEqual(1, len(self.calls()), 'installed once')

  def test_the_command_every_library_from_the_download_cache(self) -> None:
    """
    FML 1.16 finds its libraries by where ModLauncher's jar is: every one
    from the download cache's libraries/, a Gradle cache's copy of one
    (ASM, say) never taken.
    """
    gradle = os.path.join(self.scratch, 'gradle')
    held = os.path.join(gradle, 'caches', 'modules-2', 'files-2.1',
                        'org.ow2.asm', 'asm', '7.2', 'abc', 'asm-7.2.jar')
    os.makedirs(os.path.dirname(held))
    with open(held, 'wb') as file:
      file.write(b'a Gradle copy')
    java = self.launch(gradleHome=gradle).java
    main = java.index('cpw.mods.modlauncher.Launcher')
    jvm, game = java[1:main], java[main + 1:]
    path = jvm[jvm.index('-cp') + 1].split(os.pathsep)
    libraries = self.cache.path('libraries')
    self.assertNotIn(held, path)
    self.assertEqual([], [each for each in path[:-1]
                          if not each.startswith(libraries)])
    self.assertIn(self.cache.path(
      'libraries/net/minecraftforge/forge/1.16.1-%s/forge-1.16.1-%s.jar'
      % (FORGE, FORGE)), path)
    pairs = dict(zip(game[::2], game[1::2]))
    self.assertEqual('fmlclient', pairs['--launchTarget'])
    self.assertEqual(FORGE, pairs['--fml.forgeVersion'])

  def test_beside_forge_classes_by_mcp_members_by_srg(self) -> None:
    java = self.launch(agents=('/agent.jar',)).java
    named = [word for word in java if word.startswith('-Dunittas.names=')]
    self.assertEqual(1, len(named), java)
    table = named[0].split('=', 1)[1]
    self.assertEqual(self.cache.path('names/1.16.1-srg-1.txt'), table)
    with open(table, encoding='utf-8') as file:
      lines = file.read().splitlines()
    self.assertEqual('unittas-names\t1\tsrg\t1.16.1', lines[0])
    self.assertIn('c\tnet/minecraft/client/gui/screens/Screen\t'
                  'net/minecraft/client/gui/screen/Screen', lines)
    self.assertIn('m\tnet/minecraft/client/Minecraft\ttick\t()V\t'
                  'func_71407_l', lines)


if __name__ == '__main__':
  unittest.main()

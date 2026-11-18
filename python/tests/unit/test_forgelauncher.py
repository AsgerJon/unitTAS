"""
The launcher beside Forge on a modern version (SPEC.md 19.7 step 8a): 1.20.1
with Forge 47.4.28, without a game, the network or Java, as NeoForge's are
(test_neoforgelauncher). The fixtures are the real 1.20.1 version JSON and
the version JSON Forge's own installer writes, each jar in them fake; the
installer a fake 'java' run as the real one is ('-jar' it '--installClient'
FOLDER), which writes the version JSON, the patched client and the MCP
config's names (MAPPINGS) its install profile names:
- the installer fetched from Forge's maven, held to its .sha1, run once into
  the download cache; the profile by the id its install profile gives;
- the command: BootstrapLauncher, Forge's game arguments, the client jar
  by the version's own name;
- beside Forge the agent's table goes on to SRG's names (Mojang's classes,
  SRG's members), from the names Forge's install keeps: its kind, srg;
- on a system whose zlib isn't classic zlib (zlib-ng: Arch's, Fedora's),
  the installer refuses the jars it makes ('Processor failed, invalid
  outputs': its sha1s are of classic zlib's bytes, and Forge won't take
  others). It is then run once more on classic zlib (ZLIB), built once
  into the download cache from zlib's own source, held to its sha1, by
  the system's C compiler (here a fake 'cc'); without one, or refused on
  classic zlib too, one clear error says why, naming Forge's refusal.
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
import tarfile
import tempfile
import unittest
import zipfile
from unittest import mock

from test_mojangnames import LOG
from test_neoforgelauncher import faked, recorded, sha1
from test_srgnames import TSRG
from unittas import launcher
from unittas.cache import Cache
from unittas.launcher import (FORGE_MAVEN, MANIFEST, ZLIB, ZLIB_SOURCE,
                              Missing, Sources, versionCommand)

FORGE = '47.4.28'
NAME = '1.20.1-forge-' + FORGE
VANILLA_URL = 'https://piston-meta.mojang.com/v1/packages/x/1.20.1.json'
LOG_URL = 'https://piston-data.mojang.com/v1/objects/x/client.txt'
INSTALLER = FORGE_MAVEN + (
  'net/minecraftforge/forge/1.20.1-%s/forge-1.20.1-%s-installer.jar'
  % (FORGE, FORGE))
PATCHED = ('libraries/net/minecraftforge/forge/1.20.1-%s/'
           'forge-1.20.1-%s-client.jar' % (FORGE, FORGE))
MAPPINGS = ('libraries/de/oceanlabs/mcp/mcp_config/1.20.1-20230612.114412/'
            'mcp_config-1.20.1-20230612.114412-mappings.txt')

#  the installer's stand-in: as Forge's, it wants '--installClient'
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
found = os.environ.get('LD_LIBRARY_PATH', '')
with open(os.path.join(here, 'libraries.txt'), 'a') as libraries:
  libraries.write(found + '\\n')
classic = False
for folder in found.split(os.pathsep):
  library = os.path.join(folder, 'libz.so.1')
  if folder and os.path.isfile(library):
    with open(library, 'rb') as zlib:
      classic = zlib.read() == b'classic zlib'
if (os.path.exists(os.path.join(here, 'refuse'))
    or os.path.exists(os.path.join(here, 'zlib-ng')) and not classic):
  #  as Forge's installer says it, its jars made with another zlib
  print('  Processor failed, invalid outputs:')
  print('      Expected: de86b035d2da0f78940796bb95c39a932ed84834')
  print('      Actual:   65de7c2f734b5288bfaff943eb9849b979332c47')
  print('There was an error during installation')
  sys.exit(1)
for relative, given in ((%(profile)r, 'profile.json'),
                        (%(patched)r, 'patched.bin'),
                        (%(mappings)r, 'mappings.txt')):
  target = os.path.join(root, relative)
  os.makedirs(os.path.dirname(target), exist_ok=True)
  with open(os.path.join(here, given), 'rb') as source:
    data = source.read()
  with open(target, 'wb') as written:
    written.write(data)
'''
#  the system's C compiler's stand-in: it 'builds' the -o it is given
FAKE_CC = '''#!%(python)s
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, 'calls.txt'), 'a') as calls:
  calls.write(json.dumps(sys.argv[1:]) + '\\n')
with open(sys.argv[sys.argv.index('-o') + 1], 'wb') as built:
  built.write(b'classic zlib')
'''


def zlibSource() -> bytes:
  """zlib's source as its tarball holds it (the files the build names)."""
  data = io.BytesIO()
  with tarfile.open(fileobj=data, mode='w:gz') as tarball:
    for name in ('zlib.map', 'zlib.h', 'deflate.c', 'inflate.c'):
      text = ('/* %s */\n' % name).encode('ascii')
      member = tarfile.TarInfo('zlib-%s/%s' % (ZLIB, name))
      member.size = len(text)
      tarball.addfile(member, io.BytesIO(text))
  return data.getvalue()


def installerJar() -> bytes:
  """Forge's installer: its install profile, as the real one's names."""
  data = io.BytesIO()
  with zipfile.ZipFile(data, 'w') as jar:
    named = {
      'PATCHED': {'client': '[net.minecraftforge:forge:1.20.1-%s:client]'
                            % FORGE},
      'MAPPINGS': {'client': '[de.oceanlabs.mcp:mcp_config:'
                             '1.20.1-20230612.114412:mappings@txt]'}}
    jar.writestr('install_profile.json',
                 json.dumps({"version": NAME, "data": named}))
  return data.getvalue()


class ForgeLauncherTests(unittest.TestCase):

  def setUp(self) -> None:
    self.scratch = tempfile.mkdtemp(prefix='unittas-forge-')
    self.addCleanup(shutil.rmtree, self.scratch)
    self.served = {}
    vanilla = copy.deepcopy(recorded('1.20.1.json'))
    faked(vanilla['libraries'], self.served)
    for name, data in (('client', b'the 1.20.1 client jar'),
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
      {'id': '1.20.1', 'url': VANILLA_URL, 'sha1': sha1(versionJson)}
    ]}).encode('utf-8')
    profile = copy.deepcopy(recorded(NAME + '.json'))
    faked(profile['libraries'], self.served)
    installer = installerJar()
    self.served[INSTALLER] = installer
    self.served[INSTALLER + '.sha1'] = sha1(installer).encode('ascii')
    self.asked = []
    self.bin = os.path.join(self.scratch, 'java17', 'bin')
    os.makedirs(self.bin)
    for name, data in (('profile.json', json.dumps(profile)),
                       ('patched.bin', 'the patched client'),
                       ('mappings.txt', TSRG)):
      with open(os.path.join(self.bin, name), 'w', encoding='utf-8') as file:
        file.write(data)
    self.java = os.path.join(self.bin, 'java')
    with open(self.java, 'w', encoding='utf-8') as file:
      file.write(FAKE_JAVA % {
        'python': sys.executable, 'profile': 'versions/%s/%s.json'
        % (NAME, NAME), 'patched': PATCHED, 'mappings': MAPPINGS})
    os.chmod(self.java, os.stat(self.java).st_mode | stat.S_IXUSR)
    #  the C compiler the PATH gives: the fake one, never the real
    self.compilers = os.path.join(self.scratch, 'compilers')
    os.makedirs(self.compilers)
    compiler = os.path.join(self.compilers, 'cc')
    with open(compiler, 'w', encoding='utf-8') as file:
      file.write(FAKE_CC % {'python': sys.executable})
    os.chmod(compiler, os.stat(compiler).st_mode | stat.S_IXUSR)
    self.path = mock.patch.dict(os.environ, {'PATH': self.compilers})
    self.path.start()
    self.addCleanup(self.path.stop)
    source = zlibSource()
    self.served[ZLIB_SOURCE] = source
    pinned = mock.patch.object(launcher, 'ZLIB_SHA1', sha1(source))
    pinned.start()
    self.addCleanup(pinned.stop)
    self.cache = Cache(os.path.join(self.scratch, 'cache'), fetch=self.fetch)
    self.game = os.path.join(self.scratch, 'game')

  def fetch(self, url: str) -> bytes:
    self.asked.append(url)
    if url not in self.served:
      raise OSError('404 for %s' % url)
    return self.served[url]

  def calls(self) -> list:
    path = os.path.join(self.bin, 'calls.txt')
    if not os.path.isfile(path):
      return []
    with open(path, encoding='utf-8') as file:
      return [json.loads(line) for line in file]

  def lines(self, folder: str, name: str) -> list:
    path = os.path.join(folder, name)
    if not os.path.isfile(path):
      return []
    with open(path, encoding='utf-8') as file:
      return file.read().splitlines()

  def compiled(self) -> list:
    """Each run of the C compiler, its arguments."""
    return [json.loads(line)
            for line in self.lines(self.compilers, 'calls.txt')]

  def launch(self, **given):
    return versionCommand(self.game, self.java, Sources(cache=self.cache),
                          '1.20.1', 'forge', FORGE, **given)

  def test_installed_once_by_forge_s_installer(self) -> None:
    self.launch()
    installer = self.cache.path(
      'libraries/net/minecraftforge/forge/1.20.1-%s/'
      'forge-1.20.1-%s-installer.jar' % (FORGE, FORGE))
    self.assertEqual([['-jar', installer, '--installClient',
                       self.cache.path('')]], self.calls())
    self.assertIn(INSTALLER + '.sha1', self.asked)
    self.launch()
    self.assertEqual(1, len(self.calls()), 'installed once')

  def test_the_command(self) -> None:
    java = self.launch().java
    main = java.index('cpw.mods.bootstraplauncher.BootstrapLauncher')
    jvm, game = java[1:main], java[main + 1:]
    self.assertFalse([word for word in java if '${' in word])
    classPath = jvm[jvm.index('-cp') + 1].split(os.pathsep)
    self.assertEqual(self.cache.path('versions/%s/%s.jar' % (NAME, NAME)),
                     classPath[-1])
    pairs = dict(zip(game[::2], game[1::2]))
    self.assertEqual(NAME, pairs['--version'])
    self.assertEqual(FORGE, pairs['--fml.forgeVersion'])
    self.assertEqual('forgeclient', pairs['--launchTarget'])

  def test_beside_forge_the_names_go_on_to_srg(self) -> None:
    java = self.launch(agents=('/agent.jar',)).java
    named = [word for word in java if word.startswith('-Dunittas.names=')]
    self.assertEqual(1, len(named), java)
    table = named[0].split('=', 1)[1]
    self.assertEqual(self.cache.path('names/1.20.1-srg-1.txt'), table)
    with open(table, encoding='utf-8') as file:
      lines = file.read().splitlines()
    self.assertEqual('unittas-names\t1\tsrg\t1.20.1', lines[0])
    self.assertIn('m\tnet/minecraft/client/Minecraft\ttick\t()V\tm_91398_',
                  lines)

  def test_on_zlib_ng_it_installs_again_on_classic_zlib(self) -> None:
    open(os.path.join(self.bin, 'zlib-ng'), 'w').close()
    said = []
    self.cache.said = said.append
    self.launch()
    self.assertEqual(2, len(self.calls()), 'refused, then installed')
    zlib = self.cache.path('zlib/' + ZLIB)
    first, second = self.lines(self.bin, 'libraries.txt')
    self.assertNotIn(zlib, first.split(os.pathsep))
    self.assertEqual(zlib, second.split(os.pathsep)[0])
    [words] = self.compiled()
    source = self.cache.path('zlib/zlib-%s.tar.gz' % ZLIB)
    self.assertTrue(os.path.isfile(source), 'its source kept')
    self.assertIn('-shared', words)
    self.assertIn('-Wl,-soname,libz.so.1', words)
    self.assertTrue([word for word in words if word.startswith(
      '-Wl,--version-script,') and word.endswith('/zlib.map')],
      "its symbols' versions by zlib's own map: libzip asks for them")
    self.assertIn('deflate.c', [os.path.basename(word) for word in words])
    self.assertTrue(words[words.index('-o') + 1].startswith(zlib + os.sep),
                    'built in the cache')
    with open(os.path.join(zlib, 'libz.so.1'), 'rb') as file:
      self.assertEqual(b'classic zlib', file.read(), 'moved in once whole')
    self.assertEqual(['libz.so.1'], os.listdir(zlib), 'its build gone')
    told = [line for line in said if 'classic zlib %s' % ZLIB in line]
    self.assertEqual(1, len(told), said[-5:])
    self.assertIn("Forge %s's installer" % FORGE, told[0])
    self.assertIn('MinecraftForge/Installer/pull/77', told[0])
    os.remove(self.cache.path('versions/%s/%s.json' % (NAME, NAME)))
    self.launch()
    self.assertEqual(1, len(self.compiled()), 'classic zlib built once')

  def test_refused_on_classic_zlib_too_is_one_clear_error(self) -> None:
    open(os.path.join(self.bin, 'refuse'), 'w').close()
    with self.assertRaises(Missing) as refused:
      self.launch()
    said = str(refused.exception)
    self.assertNotIn('\n', said, 'one line')
    self.assertIn("Forge %s's installer" % FORGE, said)
    self.assertIn('even on classic zlib %s' % ZLIB, said)
    self.assertIn('Processor failed, invalid outputs', said)
    self.assertIn(self.cache.path('versions/%s/install.log' % NAME), said)
    self.assertEqual(2, len(self.calls()))

  def test_without_a_c_compiler_it_says_so(self) -> None:
    open(os.path.join(self.bin, 'zlib-ng'), 'w').close()
    os.remove(os.path.join(self.compilers, 'cc'))
    with self.assertRaises(Missing) as refused:
      self.launch()
    said = str(refused.exception)
    self.assertNotIn('\n', said, 'one line')
    self.assertIn("Forge %s's installer" % FORGE, said)
    self.assertIn('C compiler', said)
    self.assertIn('https://github.com/MinecraftForge/Installer/pull/77',
                  said)
    self.assertIn('https://github.com/MinecraftForge/Installer/issues/80',
                  said)
    self.assertIn(self.cache.path('versions/%s/install.log' % NAME), said)
    self.assertEqual(1, len(self.calls()), 'not run again in vain')

  def test_zlib_s_source_held_to_its_sha1(self) -> None:
    open(os.path.join(self.bin, 'zlib-ng'), 'w').close()
    self.served[ZLIB_SOURCE] = b'not zlib'
    with self.assertRaises(Missing) as refused:
      self.launch()
    self.assertIn('zlib %s' % ZLIB, str(refused.exception))
    self.assertEqual([], self.compiled(), 'nothing built from it')



if __name__ == '__main__':
  unittest.main()

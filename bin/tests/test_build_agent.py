"""
The loader-free probe's build (bin/build_agent.py, SPEC.md 19.7 step 5), its assembly without javac or a game: the
agent's jar holds its bootstrap's classes, its manifest naming the premain class and the version, and the probe's own
classes as a jar inside it, with its own manifest (the probe's version, for its hello). Same input, same bytes.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import build_agent  # noqa: E402


def touch(path: str, data: bytes) -> None:
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, 'wb') as file:
    file.write(data)


class AssemblyTests(unittest.TestCase):

  def setUp(self) -> None:
    self.folder = tempfile.mkdtemp(prefix='unittas-agent-build-')
    self.addCleanup(shutil.rmtree, self.folder, True)
    self.bootstrap = os.path.join(self.folder, 'bootstrap')
    self.probe = os.path.join(self.folder, 'probe')
    touch(os.path.join(self.bootstrap, 'io/github/asgerjon/unittas/agent/Agent.class'), b'agent')
    touch(os.path.join(self.bootstrap, 'io/github/asgerjon/unittas/agent/Bridge.class'), b'bridge')
    touch(os.path.join(self.probe, 'io/github/asgerjon/unittas/probe/V26Entry.class'), b'entry')
    touch(os.path.join(self.probe, 'io/github/asgerjon/unittas/probe/Probe.class'), b'probe')

  def assembled(self, name: str = 'agent.jar') -> str:
    return build_agent.assemble(self.bootstrap, self.probe, '0.1.0-dev18', os.path.join(self.folder, name),
                                b'entry\tx.Entry\n', '26.3')

  def test_the_agent_s_jar(self) -> None:
    with zipfile.ZipFile(self.assembled()) as jar:
      names = jar.namelist()
      self.assertEqual('META-INF/MANIFEST.MF', names[0], 'the manifest first')
      manifest = jar.read('META-INF/MANIFEST.MF').decode('utf-8')
      self.assertIn('Premain-Class: io.github.asgerjon.unittas.agent.Agent\r\n', manifest)
      self.assertIn('Implementation-Version: 0.1.0-dev18\r\n', manifest)
      self.assertIn('io/github/asgerjon/unittas/agent/Agent.class', names)
      self.assertNotIn('io/github/asgerjon/unittas/probe/Probe.class', names,
                       "the probe's classes only inside: never on the application class path")
      inner = zipfile.ZipFile(io.BytesIO(jar.read(build_agent.INNER)))
    with inner:
      self.assertEqual(b'entry', inner.read('io/github/asgerjon/unittas/probe/V26Entry.class'))
      self.assertIn('Implementation-Version: 0.1.0-dev18\r\n', inner.read('META-INF/MANIFEST.MF').decode('utf-8'))

  def test_its_version_s_hooks_beside_the_bootstrap(self) -> None:
    """The version's hooks as data (SPEC.md 19.7 step 6c): read by the bootstrap at premain, which is the same for
    every version, so at the agent's top level, not inside the probe's jar (loaded only at the first hook)."""
    with zipfile.ZipFile(self.assembled()) as jar:
      self.assertEqual(b'entry\tx.Entry\n', jar.read(build_agent.HOOKS_FILE))
      self.assertIn('Implementation-Title: unitTAS probe for 26.3 (a Java agent)\r\n',
                    jar.read('META-INF/MANIFEST.MF').decode('utf-8'))
      inner = zipfile.ZipFile(io.BytesIO(jar.read(build_agent.INNER)))
    with inner:
      self.assertNotIn(build_agent.HOOKS_FILE, inner.namelist())

  def test_a_dedicated_server_s_hooks_beside_them(self) -> None:
    """A dedicated server's hooks (SPEC.md 19.7 step 10b) beside the client's, which the bootstrap reads instead when
    its start file says role server; none where none is given."""
    path = build_agent.assemble(self.bootstrap, self.probe, '0.1.0-dev18', os.path.join(self.folder, 'server.jar'),
                                b'entry\tx.Entry\n', '26.3', b'entry\tx.ServerEntry\n')
    with zipfile.ZipFile(path) as jar:
      self.assertEqual(b'entry\tx.ServerEntry\n', jar.read(build_agent.SERVER_HOOKS_FILE))
      self.assertEqual(b'entry\tx.Entry\n', jar.read(build_agent.HOOKS_FILE))
    with zipfile.ZipFile(self.assembled()) as jar:
      self.assertNotIn(build_agent.SERVER_HOOKS_FILE, jar.namelist())

  def test_the_declarers_inside_the_probe_s_jar(self) -> None:
    """An obfuscated version's declarers (SPEC.md 19.7 step 6b): in the probe's jar, where its renaming loader reads them."""
    touch(os.path.join(self.probe, build_agent.DECLARERS), b'a\tb\t()V\tc\n')
    with zipfile.ZipFile(self.assembled()) as jar:
      self.assertNotIn(build_agent.DECLARERS, jar.namelist())
      inner = zipfile.ZipFile(io.BytesIO(jar.read(build_agent.INNER)))
    with inner:
      self.assertEqual(b'a\tb\t()V\tc\n', inner.read(build_agent.DECLARERS))

  def test_the_same_bytes_again(self) -> None:
    with open(self.assembled('one.jar'), 'rb') as one, open(self.assembled('two.jar'), 'rb') as two:
      self.assertEqual(one.read(), two.read())

  def test_the_sources_it_compiles(self) -> None:
    touch(os.path.join(self.folder, 'src', 'a', 'B.java'), b'class B {}')
    touch(os.path.join(self.folder, 'src', 'A.java'), b'class A {}')
    touch(os.path.join(self.folder, 'src', 'notes.txt'), b'')
    self.assertEqual([os.path.join(self.folder, 'src', 'A.java'), os.path.join(self.folder, 'src', 'a', 'B.java')],
                     build_agent.sourcesUnder(os.path.join(self.folder, 'src')))


class VersionsTests(unittest.TestCase):
  """Each version the builder makes an agent for: its folders, its Java, its hooks."""

  def test_26_3(self) -> None:
    version = build_agent.VERSIONS['26.3']
    self.assertEqual('25', version.release)
    self.assertFalse(version.obfuscated, '26.x runs under Mojang\'s own names')
    self.assertTrue(all(os.path.isdir(folder) for folder in version.sources))

  def test_1_21_1(self) -> None:
    """Java 21, obfuscated (compiled against its stubs, its probe renamed as it loads), the shared code and its own."""
    version = build_agent.VERSIONS['1.21.1']
    self.assertEqual('21', version.release)
    self.assertTrue(version.obfuscated)
    self.assertIn(build_agent.MODERN, version.sources)
    self.assertTrue(all(os.path.isdir(folder) for folder in version.sources))

  def test_1_20_1(self) -> None:
    """Java 17, obfuscated, as 1.21.1: the shared code and its own folder."""
    version = build_agent.VERSIONS['1.20.1']
    self.assertEqual('17', version.release)
    self.assertTrue(version.obfuscated)
    self.assertIn(build_agent.MODERN, version.sources)
    self.assertIn(os.path.join(build_agent.AGENT, 'v1_20_1', 'java'), version.sources)
    self.assertTrue(all(os.path.isdir(folder) for folder in version.sources))

  def test_1_16_1(self) -> None:
    """Java 8, its own (SPEC.md 19.7 step 11, V30), obfuscated, as 1.20.1: the shared code and its own folder."""
    version = build_agent.VERSIONS['1.16.1']
    self.assertEqual('8', version.release)
    self.assertTrue(version.obfuscated)
    self.assertIn(build_agent.MODERN, version.sources)
    self.assertIn(os.path.join(build_agent.AGENT, 'v1_16_1', 'java'), version.sources)
    self.assertTrue(all(os.path.isdir(folder) for folder in version.sources))

  def test_each_version_s_hooks_file(self) -> None:
    counts = {'26.3': 21, '1.21.1': 22, '1.20.1': 22, '1.16.1': 22}
    for minecraft, version in build_agent.VERSIONS.items():
      with self.subTest(minecraft=minecraft):
        with open(version.hooks, encoding='utf-8') as file:
          lines = [line.rstrip('\n') for line in file if line.strip() and not line.startswith('#')]
        entry = lines[0].split('\t')
        self.assertEqual('entry', entry[0])
        source = entry[1].replace('.', os.sep) + '.java'
        self.assertTrue(any(os.path.isfile(os.path.join(folder, source)) for folder in version.sources),
                        'its entry class is one of its own: %s' % entry[1])
        for line in lines[1:]:
          parts = line.split('\t')
          self.assertEqual(5, len(parts), line)
          self.assertIn(parts[0], ('BEFORE', 'AFTER'), line)
        self.assertEqual(counts[minecraft], len(lines) - 1, "%s's hooks" % minecraft)

  def test_each_version_s_server_hooks_file(self) -> None:
    """A dedicated server's hooks (SPEC.md 19.7 step 10b): the server's entry, its own hooks, no client class; what
    a command's source is told (command.heard) as the client's hooks have it, so a console command's lines come back;
    a player in and out (player.joined, player.left: PROTOCOL.md 9.4)."""
    for minecraft, version in build_agent.VERSIONS.items():
      with self.subTest(minecraft=minecraft):
        with open(version.serverHooks, encoding='utf-8') as file:
          lines = [line.rstrip('\n') for line in file if line.strip() and not line.startswith('#')]
        self.assertEqual(['entry', 'io.github.asgerjon.unittas.probe.ModernServerEntry'], lines[0].split('\t'))
        hooks = [line.split('\t') for line in lines[1:]]
        self.assertEqual(['server.starting', 'server.tick.start', 'server.tick.end', 'crash.saved', 'command.heard',
                          'command.heard', 'player.joined', 'player.left'], [hook[4] for hook in hooks])
        with open(version.hooks, encoding='utf-8') as file:
          client = [line.rstrip('\n').split('\t') for line in file if line.strip() and not line.startswith('#')]
        self.assertEqual([hook for hook in client if hook[4:] == ['command.heard']],
                         [hook for hook in hooks if hook[4] == 'command.heard'])
        self.assertEqual([], [hook for hook in hooks if hook[1].startswith('net/minecraft/client/')],
                         'a dedicated server has no client class')



if __name__ == '__main__':
  unittest.main()

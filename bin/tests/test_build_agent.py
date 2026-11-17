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
    return build_agent.assemble(self.bootstrap, self.probe, '0.1.0-dev18', os.path.join(self.folder, name))

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

  def test_the_same_bytes_again(self) -> None:
    with open(self.assembled('one.jar'), 'rb') as one, open(self.assembled('two.jar'), 'rb') as two:
      self.assertEqual(one.read(), two.read())

  def test_the_sources_it_compiles(self) -> None:
    touch(os.path.join(self.folder, 'src', 'a', 'B.java'), b'class B {}')
    touch(os.path.join(self.folder, 'src', 'A.java'), b'class A {}')
    touch(os.path.join(self.folder, 'src', 'notes.txt'), b'')
    self.assertEqual([os.path.join(self.folder, 'src', 'A.java'), os.path.join(self.folder, 'src', 'a', 'B.java')],
                     build_agent.sourcesUnder(os.path.join(self.folder, 'src')))


if __name__ == '__main__':
  unittest.main()

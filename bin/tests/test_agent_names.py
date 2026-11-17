"""
The agent's names (SPEC.md 19.7 step 6b) with no game: agent/src/test/
java's RenameCheck obfuscates a small game of its own, renames it and the
probe written against it as the agent renames its probe at run time, runs
them, and turns the obfuscated game back into stubs, on every Java the
agent runs on (17, 21, 25). The probe is then compiled against those
stubs alone, as bin/build_agent.py compiles a port against a version's.
A Java not installed is skipped, saying so; no javac fails.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_agent_wrap import JAVAS, ROOT, java, javac  # noqa: E402

AGENT = os.path.join(ROOT, 'agent', 'src')
SOURCES = (os.path.join(AGENT, 'bootstrap', 'java'),
           os.path.join(AGENT, 'build', 'java'),
           os.path.join(AGENT, 'test', 'java'))
PROBE = os.path.join(AGENT, 'test', 'java', 'io', 'github', 'asgerjon',
                     'unittas', 'agent', 'probe')
CHECK = 'io.github.asgerjon.unittas.agent.RenameCheck'
#  RenameCheck's checks, in the order it runs them: each must say ok
EXPECTED = [
  'renamed', 'renamed-run', 'renaming-loader', 'no-mojang-names-left',
  'stubs', 'signatures',
  'refuses-unknown-member', 'refuses-unresolved', 'refuses-bad-table',
  'lookup', 'hooks-renamed',
]


def sources(folders: tuple) -> list:
  """Every .java file under the folders, in a fixed order."""
  found = []
  for folder in folders:
    for where, _, names in os.walk(folder):
      found += [os.path.join(where, name) for name in names
                if name.endswith('.java')]
  return sorted(found)


class NamesTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.homes = {major: java(major) for major in JAVAS}
    cls.javac = javac(cls.homes)
    cls.folder = tempfile.mkdtemp(prefix='unittas-names-')
    cls.classes = os.path.join(cls.folder, 'classes')
    cls.compiled = None
    if cls.javac is None:
      return
    cls.compiled = subprocess.run(
      [cls.javac, '--release', '17', '-encoding', 'UTF-8', '-nowarn', '-d',
       cls.classes] + sources(SOURCES),
      stdin=subprocess.DEVNULL, capture_output=True, text=True)

  @classmethod
  def tearDownClass(cls) -> None:
    shutil.rmtree(cls.folder, ignore_errors=True)

  def check(self, major: int, stubs: str) -> None:
    home = self.homes[major]
    if home is None:
      self.skipTest('no Java %d installed' % major)
    self.assertIsNotNone(self.javac, 'no javac from 17 on found')
    self.assertEqual(0, self.compiled.returncode,
                     'javac --release 17:\n' + self.compiled.stdout
                     + self.compiled.stderr)
    done = subprocess.run(
      [os.path.join(home, 'bin', 'java'), '-cp', self.classes, CHECK,
       stubs], stdin=subprocess.DEVNULL, capture_output=True, text=True,
      timeout=120)
    lines = done.stdout.splitlines()
    self.assertEqual([], [line for line in lines
                          if not line.startswith('ok ')], done.stderr)
    self.assertEqual(EXPECTED, [line[3:] for line in lines])
    self.assertEqual(0, done.returncode, done.stderr)

  def test_on_java_17(self) -> None:
    self.check(17, os.path.join(self.folder, 'stubs-17'))

  def test_on_java_21(self) -> None:
    self.check(21, os.path.join(self.folder, 'stubs-21'))

  def test_on_java_25(self) -> None:
    self.check(25, os.path.join(self.folder, 'stubs-25'))

  def test_the_probe_compiles_against_the_stubs_alone(self) -> None:
    major = next((each for each in JAVAS if self.homes[each]), None)
    if major is None:
      self.skipTest('no Java installed')
    stubs = os.path.join(self.folder, 'stubs-compile')
    self.check(major, stubs)
    into = os.path.join(self.folder, 'probe-classes')
    done = subprocess.run(
      [self.javac, '--release', '17', '-encoding', 'UTF-8', '-nowarn',
       '-cp', stubs, '-d', into] + sources((PROBE,)),
      stdin=subprocess.DEVNULL, capture_output=True, text=True)
    self.assertEqual(0, done.returncode, done.stdout + done.stderr)


if __name__ == '__main__':
  unittest.main()

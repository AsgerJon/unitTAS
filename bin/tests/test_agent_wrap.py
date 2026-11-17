"""
The agent's rewriter (SPEC.md 19.7 step 6a) on class files of its own, with
no game: agent/src/test/java's WrapCheck has it wrap the samples' methods,
loads them under the JVM's verifier and runs them, on every Java the agent
runs on (17 for 1.20.1, 21 for 1.21.1, 25 for 26.3). The bootstrap and the
check are compiled for Java 17, as the agent's jar is. A Java not installed
is skipped, saying so; none at all, or no javac, fails.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(
  __file__))))

import build_agent  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
  os.path.abspath(__file__))))
SOURCES = (os.path.join(ROOT, 'agent', 'src', 'bootstrap', 'java'),
           os.path.join(ROOT, 'agent', 'src', 'build', 'java'),
           os.path.join(ROOT, 'agent', 'src', 'test', 'java'))
CHECK = 'io.github.asgerjon.unittas.agent.WrapCheck'
#  WrapCheck's checks, in the order it runs them: each must say ok
EXPECTED = [
  'wrapped', 'before-passes', 'before-answers', 'before-and-after',
  'static-arguments', 'reference-answer', 'boolean-answer',
  'after-primitive', 'overloads', 'own-branches', 'super-call',
  'reflection', 'refuses-missing', 'refuses-constructor',
  'refuses-abstract', 'refuses-interface', 'others-untouched', 'hooks-read',
]
JAVAS = (17, 21, 25)


def java(major: int) -> Optional[str]:
  """
  A Java of that major version, its home: CI's JAVA_HOME_N_X64, else the
  usual places. A runtime is enough to run the check.
  """
  homes = [os.environ.get('JAVA_HOME_%d_X64' % major, '')]
  homes += ['/usr/lib/jvm/java-%d-openjdk' % major,
            '/usr/lib/jvm/java-%d-openjdk-amd64' % major,
            '/usr/lib/jvm/jdk-%d' % major]
  for home in homes:
    if home and os.access(os.path.join(home, 'bin', 'java'), os.X_OK):
      return home
  return None


def javac(homes: dict) -> Optional[str]:
  """The newest javac among the Javas found: any from 17 compiles for 17."""
  for major in sorted(homes, reverse=True):
    home = homes[major]
    binary = os.path.join(home, 'bin', 'javac') if home else ''
    if binary and os.access(binary, os.X_OK):
      return binary
  return None


def sources() -> list:
  """Every .java file of the bootstrap, the build's tools and the checks."""
  found = []
  for folder in SOURCES:
    for where, _, names in os.walk(folder):
      found += [os.path.join(where, name) for name in names
                if name.endswith('.java')]
  return sorted(found)


class WrapTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.homes = {major: java(major) for major in JAVAS}
    cls.javac = javac(cls.homes)
    cls.classes = tempfile.mkdtemp(prefix='unittas-wrap-')
    cls.compiled = None
    if cls.javac is None:
      return
    done = subprocess.run(
      [cls.javac, '--release', '17', '-encoding', 'UTF-8', '-nowarn', '-d',
       cls.classes] + sources(),
      stdin=subprocess.DEVNULL, capture_output=True, text=True)
    cls.compiled = done

  @classmethod
  def tearDownClass(cls) -> None:
    shutil.rmtree(cls.classes, ignore_errors=True)

  def run_on(self, major: int) -> None:
    home = self.homes[major]
    if home is None:
      self.skipTest('no Java %d installed' % major)
    self.assertIsNotNone(self.javac, 'no javac from 17 on found')
    self.assertEqual(0, self.compiled.returncode,
                     'javac --release 17:\n' + self.compiled.stdout
                     + self.compiled.stderr)
    done = subprocess.run(
      [os.path.join(home, 'bin', 'java'), '-cp', self.classes, CHECK],
      stdin=subprocess.DEVNULL, capture_output=True, text=True,
      timeout=120)
    lines = done.stdout.splitlines()
    failed = [line for line in lines if not line.startswith('ok ')]
    self.assertEqual([], failed, done.stderr)
    self.assertEqual(EXPECTED, [line[3:] for line in lines])
    self.assertEqual(0, done.returncode, done.stderr)

  def test_some_java_is_installed(self) -> None:
    self.assertTrue(any(self.homes.values()),
                    'no Java 17, 21 or 25 found: the rewriter is unchecked')
    self.assertIsNotNone(self.javac, 'no javac from 17 on found')

  def test_the_built_bootstrap_is_for_java_17(self) -> None:
    self.assertIsNotNone(self.javac, 'no javac from 17 on found')
    into = os.path.join(self.classes, 'built')
    build_agent.compileBootstrap(self.javac, into)
    majors = set()
    for where, _, names in os.walk(into):
      for name in names:
        with open(os.path.join(where, name), 'rb') as file:
          majors.add(struct.unpack('>4xHH', file.read(8))[1])
    self.assertEqual({61}, majors, "class files for Java 17 (61): 1.20.1's")

  def test_on_java_17(self) -> None:
    self.run_on(17)

  def test_on_java_21(self) -> None:
    self.run_on(21)

  def test_on_java_25(self) -> None:
    self.run_on(25)


if __name__ == '__main__':
  unittest.main()

"""
Tests that the scripts which run the release jar build it first: `./gradlew remapJar`, which makes the release jar
(Searge names) from the dev jar. `./gradlew assemble` makes only the dev jar here, so a release jar beside it can be
an earlier build's. They take the jar by its name, unittas-<mod_version>.jar, and refuse one older than its dev jar.

  python -m unittest discover -s bin/tests
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GRADLE = re.compile(r'\./gradlew\b[^\n]*')


def read(name: str) -> str:
  with open(os.path.join(ROOT, name), encoding='utf-8') as file:
    return file.read()


class OldSavesBuildsTheReleaseJarTests(unittest.TestCase):

  def setUp(self) -> None:
    self.script = read('unittas-oldsaves.sh')

  def test_it_builds_with_remap_jar(self) -> None:
    builds = GRADLE.findall(self.script)
    self.assertTrue(builds, 'unittas-oldsaves.sh runs no ./gradlew')
    self.assertTrue(any(re.search(r'\bremapJar\b', line) for line in builds), builds)
    self.assertFalse(any(re.search(r'\bassemble\b', line) for line in builds), builds)

  def test_it_takes_the_jar_by_its_name_and_age(self) -> None:
    for wanted in ('unittas-$VERSION.jar', 'unittas-$VERSION-dev.jar', '[ "$JAR" -ot "$DEV_JAR" ]'):
      self.assertTrue(wanted in self.script, 'unittas-oldsaves.sh has no %s' % wanted)


class TheProbesReleaseGameBuildsItTooTests(unittest.TestCase):

  def test_release_py_builds_with_remap_jar(self) -> None:
    source = read(os.path.join('python', 'src', 'unittas', 'release.py'))
    self.assertIn("'remapJar'", source)
    self.assertNotIn("'assemble'", source)


if __name__ == '__main__':
  unittest.main()

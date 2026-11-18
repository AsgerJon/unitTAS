"""
Tests of unitTAS's own stamp, version_stamp.py: the version written into
gradle.properties (mod_version), UnitTasMod.VERSION, README.md's jar
names, and the Python package's python/pyproject.toml and __version__
(as WorkToy's stamp writes its own: the version as it is, which the
build spells as Python does), as the publish job of every button runs it,
and its --check. Each
test builds a small repository of its own in a temporary folder (the
stamped files and a copy of the script), runs the script there as a
separate process, and checks what it printed and wrote. Nothing in the
real repository is touched.
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

TOOLING = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(
  'src', 'main', 'java', 'io', 'github', 'asgerjon', 'unittas',
  'UnitTasMod.java'
)

PROPERTIES = """# unitTAS's build
org.gradle.jvmargs=-Xmx3G

mod_version=%s

# not unitTAS's version
unimixins_version=1.7.10-0.3.1
"""

CONSTANT = """package io.github.asgerjon.unittas;

@Mod(modid = UnitTasMod.MODID, version = UnitTasMod.VERSION)
public final class UnitTasMod {

\tpublic static final String MODID = "unittas";
\tpublic static final String VERSION = "%s";
}
"""

#  The Python package's: its version line the one stamped
PACKAGE = """[build-system]
requires = ["setuptools>=77"]

[project]
name = "unittas"
version = "%s"
requires-python = ">=3.14"
dependencies = ["worktoy>=1.2.2", "mcdex>=0.2.0"]
"""

#  The package's own __version__
INIT = """\"\"\"The 'unittas' package.\"\"\"
from __future__ import annotations

__version__ = '%s'
"""
PACKAGE_INIT = os.path.join('python', 'src', 'unittas', '__init__.py')

#  Every unitTAS version here is '{v}'; the rest must never be stamped.
MANUAL = """# unitTAS

`./gradlew build` makes `build/libs/unittas-<version>.jar` and
`unittas-<version>-dev.jar`. The results are in `unittas-results/`.

   devOnlyNonPublishable(rfg.deobf(files('/path/to/unittas-{v}.jar')))

`rfg.deobf("io.github.asgerjon:unittas:{v}")` from a local repository
resolves; the dev jar is `unittas-{v}-dev.jar`. UniMixins 1.7.10-0.3.1,
JitPack: `com.github.AsgerJon:unitTAS:<tag>`, as in
   devOnlyNonPublishable(rfg.deobf('com.github.AsgerJon:unitTAS:{v}'))
"""


def _read(path: str) -> str:
  with open(path, 'r', encoding='utf-8') as f:
    return f.read()


def _write(path: str, text: str) -> None:
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, 'w', encoding='utf-8') as f:
    f.write(text)


class _Repository(unittest.TestCase):
  """A temporary repository: the stamped files at version '0.1.0-beta'."""

  def setUp(self) -> None:
    self.root = tempfile.mkdtemp(prefix='release-tooling-')
    self.addCleanup(shutil.rmtree, self.root)
    self.tooling = os.path.join(self.root, 'bin', 'release_tooling')
    os.makedirs(self.tooling)
    shutil.copy(os.path.join(TOOLING, 'version_stamp.py'), self.tooling)
    _write(self.path('settings.gradle'), "rootProject.name = 'unittas'\n")
    self.setTree('0.1.0-beta')
    self.githubEnv = os.path.join(self.root, 'github-env')
    _write(self.githubEnv, '')

  def path(self, *parts: str) -> str:
    return os.path.join(self.root, *parts)

  def setTree(self, version: str, constant: str = None,
              manual: str = None, package: str = None) -> None:
    _write(self.path('gradle.properties'), PROPERTIES % version)
    _write(self.path(MOD), CONSTANT % (constant or version))
    _write(self.path('README.md'), MANUAL.format(v=manual or version))
    _write(self.path('python', 'pyproject.toml'), PACKAGE % (package or version))
    _write(self.path(PACKAGE_INIT), INIT % (package or version))

  def tree(self) -> tuple:
    return (
      _read(self.path('gradle.properties')),
      _read(self.path(MOD)),
      _read(self.path('README.md')),
      _read(self.path('python', 'pyproject.toml')),
      _read(self.path(PACKAGE_INIT)),
    )

  def run_(self, script: str, *args: str, **env: str):
    environ = dict(os.environ, GITHUB_ENV=self.githubEnv, **env)
    return subprocess.run(
      [sys.executable, '-I', os.path.join(self.tooling, script), *args],
      capture_output=True, text=True, env=environ, cwd=self.root,
    )


class VersionStampTests(_Repository):

  def stamp(self, version: str):
    return self.run_('version_stamp.py', 'VERSION_INFO', VERSION_INFO=version)

  def test_stamps_the_five_files(self) -> None:
    result = self.stamp('0.1.0-dev0')
    self.assertEqual(result.returncode, 0, result.stdout)
    self.assertIn('0.1.0-dev0 (was 0.1.0-beta)', result.stdout)
    self.assertEqual(self.tree(), (
      PROPERTIES % '0.1.0-dev0',
      CONSTANT % '0.1.0-dev0',
      MANUAL.format(v='0.1.0-dev0'),
      PACKAGE % '0.1.0-dev0',
      INIT % '0.1.0-dev0',
    ))

  def test_the_dev_jars_classifier_stays(self) -> None:
    self.setTree('0.1.0')
    self.assertIn('unittas-0.1.0-dev.jar', self.tree()[2])
    self.assertEqual(self.stamp('0.1.1-dev0').returncode, 0)
    self.assertIn('unittas-0.1.1-dev0-dev.jar', self.tree()[2])
    self.assertEqual(self.tree()[2], MANUAL.format(v='0.1.1-dev0'))

  def test_one_release_after_another(self) -> None:
    for version in ('0.1.0-dev0', '0.1.0-rc0', '0.1.0', '0.1.1-dev0'):
      result = self.stamp(version)
      self.assertEqual(result.returncode, 0, result.stdout)
    self.assertEqual(self.tree(), (
      PROPERTIES % '0.1.1-dev0',
      CONSTANT % '0.1.1-dev0',
      MANUAL.format(v='0.1.1-dev0'),
      PACKAGE % '0.1.1-dev0',
      INIT % '0.1.1-dev0',
    ))

  def test_check(self) -> None:
    result = self.run_('version_stamp.py', '--check')
    self.assertEqual(result.returncode, 0, result.stdout)
    self.assertIn('0.1.0-beta', result.stdout)
    self.setTree('0.1.0-beta', constant='0.1.0-rc0')
    self.assertEqual(self.run_('version_stamp.py', '--check').returncode, 5)
    self.setTree('0.1.0-dev2', package='0.1.0-dev1')
    result = self.run_('version_stamp.py', '--check')
    self.assertEqual(result.returncode, 5, result.stdout)
    self.assertIn('pyproject.toml', result.stdout)

  def test_refuses_files_that_disagree(self) -> None:
    for constant, manual, package in (('0.1.0-rc0', None, None),
                                      (None, '0.0.9', None),
                                      (None, None, '0.0.9')):
      self.setTree('0.1.0-beta', constant=constant, manual=manual,
                   package=package)
      before = self.tree()
      result = self.stamp('0.1.0-dev0')
      self.assertEqual(result.returncode, 5, result.stdout)
      self.assertIn('disagree', result.stdout)
      self.assertEqual(self.tree(), before)

  def test_refuses_a_manual_naming_no_version(self) -> None:
    _write(self.path('README.md'), '# unitTAS\n\n`unittas-<version>.jar`\n')
    before = self.tree()
    self.assertEqual(self.stamp('0.1.0-dev0').returncode, 5)
    self.assertEqual(self.run_('version_stamp.py', '--check').returncode, 5)
    self.assertEqual(self.tree(), before)

  def test_refuses_a_version_off_the_scheme(self) -> None:
    before = self.tree()
    for version in ('v0.1.0', '0.1.0-beta', '0.1', '0.1.0-dev', '0.1.0.1'):
      self.assertEqual(self.stamp(version).returncode, 6, version)
    self.assertEqual(self.tree(), before)

  def test_usage_errors(self) -> None:
    self.assertEqual(self.run_('version_stamp.py', 'A', 'B').returncode, 1)
    result = self.run_('version_stamp.py', 'NOT_SET_HERE')
    self.assertEqual(result.returncode, 2)


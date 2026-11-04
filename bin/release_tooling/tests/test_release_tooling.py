"""
Tests of the release tooling beside this folder. Each test builds a small
repository of its own in a temporary folder (the files the scripts read
and stamp, and a copy of the scripts), runs the scripts there as the
release workflows do, as separate processes, and checks what they printed,
exported and wrote. Nothing in the real repository is touched.

Run from the repository root:
  python -m unittest discover -s bin/release_tooling/tests
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
SCRIPTS = (
  'version_get.py', 'version_bump.py', 'version_stamp.py',
  'safety_check.py', 'safety_lock.py',
)
CHANNELS = ('rc', 'micro', 'minor', 'major')
MOD = os.path.join(
  'src', 'main', 'java', 'io', 'github', 'asgerjon', 'unittas',
  'UnitTasMod.java'
)

COMMENT = '#  The counters (a comment the bump keeps).'

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

#  Every unitTAS version here is '{v}'; the rest must never be stamped.
MANUAL = """# unitTAS

`./gradlew build` makes `build/libs/unittas-<version>.jar` and
`unittas-<version>-dev.jar`. The results are in `unittas-results/`.

   devOnlyNonPublishable(rfg.deobf(files('/path/to/unittas-{v}.jar')))

`rfg.deobf("io.github.asgerjon:unittas:{v}")` from a local repository
resolves; the dev jar is `unittas-{v}-dev.jar`. UniMixins 1.7.10-0.3.1,
JitPack: `com.github.AsgerJon:unitTAS:<tag>`.
"""


def _read(path: str) -> str:
  with open(path, 'r', encoding='utf-8') as f:
    return f.read()


def _write(path: str, text: str) -> None:
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, 'w', encoding='utf-8') as f:
    f.write(text)


class _Repository(unittest.TestCase):
  """
  A temporary repository: the stamped files at version '0.1.0-beta', the
  counters at 0.1.0 with nothing published yet, every safety locked.
  """

  def setUp(self) -> None:
    self.root = tempfile.mkdtemp(prefix='release-tooling-')
    self.addCleanup(shutil.rmtree, self.root)
    self.tooling = os.path.join(self.root, 'bin', 'release_tooling')
    os.makedirs(self.tooling)
    for script in SCRIPTS:
      shutil.copy(os.path.join(TOOLING, script), self.tooling)
    _write(self.path('settings.gradle'), "rootProject.name = 'unittas'\n")
    self.setTree('0.1.0-beta')
    self.setCounters(0, 1, 0, 0, 0)
    for channel in CHANNELS:
      self.setSafety(channel, 'STOP\n')
    self.githubEnv = os.path.join(self.root, 'github-env')
    _write(self.githubEnv, '')

  def path(self, *parts: str) -> str:
    return os.path.join(self.root, *parts)

  def setTree(self, version: str, constant: str = None,
              manual: str = None) -> None:
    _write(self.path('gradle.properties'), PROPERTIES % version)
    _write(self.path(MOD), CONSTANT % (constant or version))
    _write(self.path('README.md'), MANUAL.format(v=manual or version))

  def tree(self) -> tuple[str, str, str]:
    return (
      _read(self.path('gradle.properties')),
      _read(self.path(MOD)),
      _read(self.path('README.md')),
    )

  def setCounters(self, major: int, minor: int, micro: int, rc: int,
                  dev: int) -> None:
    text = '%s\nMAJOR=%d\nMINOR=%d\nMICRO=%d\nRC=%d\nDEV=%d\n' % (
      COMMENT, major, minor, micro, rc, dev)
    _write(os.path.join(self.tooling, 'VERSION'), text)

  def counters(self) -> str:
    return _read(os.path.join(self.tooling, 'VERSION'))

  def setSafety(self, channel: str, text: str = None) -> None:
    path = os.path.join(self.tooling, '%s.safety' % channel)
    if text is None:
      os.remove(path)
    else:
      _write(path, text)

  def safety(self, channel: str) -> str:
    return _read(os.path.join(self.tooling, '%s.safety' % channel))

  def run_(self, script: str, *args: str, **env: str):
    environ = dict(os.environ, GITHUB_ENV=self.githubEnv, **env)
    return subprocess.run(
      [sys.executable, '-I', os.path.join(self.tooling, script), *args],
      capture_output=True, text=True, env=environ, cwd=self.root,
    )

  def exported(self) -> str:
    return _read(self.githubEnv)

  def get(self, channel: str) -> str:
    result = self.run_('version_get.py', channel)
    self.assertEqual(result.returncode, 0, result.stdout)
    return result.stdout.strip()


class VersionGetTests(_Repository):

  def test_each_channel(self) -> None:
    self.assertEqual(self.get('dev'), '0.1.0-dev0')
    self.assertEqual(self.get('rc'), '0.1.0-rc0')
    self.assertEqual(self.get('lts'), '0.1.0')
    self.assertEqual(self.get('minor'), '0.2.0')
    self.assertEqual(self.get('major'), '1.0.0')

  def test_exports_through_github_env(self) -> None:
    result = self.run_('version_get.py', 'dev', 'VERSION_INFO')
    self.assertEqual(result.returncode, 0, result.stdout)
    self.assertEqual(result.stdout, '')
    self.assertEqual(self.exported(), 'VERSION_INFO=0.1.0-dev0\n')

  def test_dev_refused_once_an_rc_is_out(self) -> None:
    self.setCounters(0, 1, 0, 1, 3)
    result = self.run_('version_get.py', 'dev', 'VERSION_INFO')
    self.assertEqual(result.returncode, 5)
    self.assertEqual(self.exported(), '')
    self.assertEqual(self.get('rc'), '0.1.0-rc1')

  def test_usage_errors(self) -> None:
    self.assertEqual(self.run_('version_get.py').returncode, 1)
    self.assertEqual(self.run_('version_get.py', 'dev', 'A', 'B').returncode,
                     2)
    self.assertEqual(self.run_('version_get.py', 'beta').returncode, 3)


class VersionBumpTests(_Repository):

  def test_a_release_history(self) -> None:
    history = [
      ('dev', '0.1.0-dev0'), ('dev', '0.1.0-dev1'), ('rc', '0.1.0-rc0'),
      ('rc', '0.1.0-rc1'), ('lts', '0.1.0'), ('dev', '0.1.1-dev0'),
      ('lts', '0.1.1'), ('minor', '0.2.0'), ('lts', '0.2.1'),
      ('major', '1.0.0'), ('rc', '1.0.1-rc0'), ('lts', '1.0.1'),
    ]
    for channel, version in history:
      self.assertEqual(self.get(channel), version, channel)
      result = self.run_('version_bump.py', channel)
      self.assertEqual(result.returncode, 0, result.stdout)

  def test_keeps_the_comments(self) -> None:
    self.run_('version_bump.py', 'minor')
    self.assertEqual(
      self.counters(),
      '%s\nMAJOR=0\nMINOR=2\nMICRO=1\nRC=0\nDEV=0\n' % COMMENT)

  def test_dev_refused_once_an_rc_is_out(self) -> None:
    self.setCounters(0, 1, 0, 1, 3)
    before = self.counters()
    self.assertEqual(self.run_('version_bump.py', 'dev').returncode, 5)
    self.assertEqual(self.counters(), before)

  def test_usage_errors(self) -> None:
    self.assertEqual(self.run_('version_bump.py').returncode, 1)
    self.assertEqual(self.run_('version_bump.py', 'dev', 'x').returncode, 2)
    self.assertEqual(self.run_('version_bump.py', 'beta').returncode, 3)


class VersionStampTests(_Repository):

  def stamp(self, version: str):
    return self.run_('version_stamp.py', 'VERSION_INFO', VERSION_INFO=version)

  def test_stamps_the_three_files(self) -> None:
    result = self.stamp('0.1.0-dev0')
    self.assertEqual(result.returncode, 0, result.stdout)
    self.assertIn('0.1.0-dev0 (was 0.1.0-beta)', result.stdout)
    self.assertEqual(self.tree(), (
      PROPERTIES % '0.1.0-dev0',
      CONSTANT % '0.1.0-dev0',
      MANUAL.format(v='0.1.0-dev0'),
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
    ))

  def test_check(self) -> None:
    result = self.run_('version_stamp.py', '--check')
    self.assertEqual(result.returncode, 0, result.stdout)
    self.assertIn('0.1.0-beta', result.stdout)
    self.setTree('0.1.0-beta', constant='0.1.0-rc0')
    self.assertEqual(self.run_('version_stamp.py', '--check').returncode, 5)

  def test_refuses_files_that_disagree(self) -> None:
    for constant, manual in (('0.1.0-rc0', None), (None, '0.0.9')):
      self.setTree('0.1.0-beta', constant=constant, manual=manual)
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


class SafetyTests(_Repository):

  def checkSafety(self, channel: str):
    return self.run_('safety_check.py', channel, 'SAFETY_VERDICT')

  def assertAllLocked(self) -> None:
    for channel in CHANNELS:
      self.assertEqual(self.safety(channel), 'STOP\n', channel)

  def test_allow_passes_and_is_spent(self) -> None:
    self.setSafety('rc', 'ALLOW\n')
    result = self.checkSafety('rc')
    self.assertEqual(result.returncode, 0, result.stdout)
    self.assertEqual(self.exported(), 'SAFETY_VERDICT=ALLOW\n')
    self.assertAllLocked()

  def test_anything_else_stops(self) -> None:
    for text in ('STOP\n', 'allow\n', 'ALLOW please\n', '', None):
      self.setSafety('micro', text)
      _write(self.githubEnv, '')
      result = self.checkSafety('micro')
      self.assertEqual(result.returncode, 0, result.stdout)
      self.assertEqual(self.exported(), 'SAFETY_VERDICT=STOP\n', repr(text))
      self.assertAllLocked()

  def test_another_channels_arming_is_spent_too(self) -> None:
    self.setSafety('minor', 'ALLOW\n')
    self.checkSafety('rc')
    self.assertEqual(self.exported(), 'SAFETY_VERDICT=STOP\n')
    self.assertAllLocked()

  def test_lock(self) -> None:
    self.setSafety('micro', 'ALLOW\n')
    self.setSafety('major', None)
    result = self.run_('safety_lock.py')
    self.assertEqual(result.returncode, 0, result.stdout)
    self.assertAllLocked()

  def test_usage_errors(self) -> None:
    self.assertEqual(self.run_('safety_check.py').returncode, 1)
    self.assertEqual(self.run_('safety_check.py', 'rc', 'A', 'B').returncode,
                     2)
    self.assertEqual(self.run_('safety_check.py', 'dev').returncode, 3)
    self.assertEqual(self.run_('safety_lock.py', 'x').returncode, 1)


if __name__ == '__main__':
  unittest.main()

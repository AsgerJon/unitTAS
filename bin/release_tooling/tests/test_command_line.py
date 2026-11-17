"""
TestCommandLine tests 'version_get.py' and 'version_bump.py'.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import release_state

from . import ReleaseToolingTest


class TestCommandLine(ReleaseToolingTest):
  """
  The publish job of every button runs 'version_get.py' with the button
  before the build and 'version_bump.py' with the button after the
  publish. Each decides the press again from VERSION as the publish job
  checked it out, so a press another run made obsolete is refused there
  too, with the same words, and a refused bump leaves VERSION as it was.
  """

  def test_get_prints_or_exports(self) -> None:
    code, output = self.runScript('version_get.py', 'minor-dev')
    self.assertEqual((code, output), (0, '1.2.0-dev0\n'))
    code, output = self.runScript('version_get.py', 'minor-dev',
                                  'VERSION_INFO')
    self.assertEqual((code, output), (0, ''))
    self.assertEqual(self.readEnv(), dict(VERSION_INFO='1.2.0-dev0'))

  def test_get_refused(self) -> None:
    code, output = self.runScript('version_get.py', 'micro-rc',
                                  'VERSION_INFO')
    self.assertEqual(code, 5)
    press = release_state.decide(self.info(), 'micro-rc')
    self.assertEqual(output, press.message + '\n')
    self.assertEqual(self.readEnv(), dict())

  def test_bump(self) -> None:
    code, output = self.runScript('version_bump.py', 'minor-dev')
    self.assertEqual(code, 0, output)
    self.assertEqual(self.readCounters(), self.info(level='minor', dev=1))
    self.assertIn('LEVEL=minor', self.readText(self.versionPath))
    self.assertIn('#  A copy of VERSION', self.readText(self.versionPath))

  def test_bump_refused(self) -> None:
    before = self.readText(self.versionPath)
    code, output = self.runScript('version_bump.py', 'minor-lts')
    self.assertEqual(code, 5)
    press = release_state.decide(self.info(), 'minor-lts')
    self.assertEqual(output, press.message + '\n')
    self.assertEqual(self.readText(self.versionPath), before)

  def test_unreadable_version(self) -> None:
    self.writeText(self.versionPath, 'MAJOR=1\n')
    for script in ('version_get.py', 'version_bump.py'):
      with self.subTest(script=script):
        code, output = self.runScript(script, 'micro-dev')
        self.assertEqual(code, 4)
        self.assertIn('VERSION lacks the lines for MINOR', output)

  def test_usage(self) -> None:
    for script in ('version_get.py', 'version_bump.py'):
      with self.subTest(script=script):
        code, output = self.runScript(script)
        self.assertEqual(code, 1)
        self.assertIn('Usage: python bin/release_tooling/%s' % script,
                      output)
        code, output = self.runScript(script, 'lts')
        self.assertEqual(code, 3)
        self.assertIn("Unrecognized button: 'lts'!", output)
    code, output = self.runScript('version_get.py', 'micro-dev', 'A', 'B')
    self.assertEqual(code, 2)
    self.assertIn("Received unexpected extra arguments: 'B'!", output)
    code, output = self.runScript('version_bump.py', 'micro-dev', 'A')
    self.assertEqual(code, 2)
    self.assertIn("Received unexpected extra arguments: 'A'!", output)

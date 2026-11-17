"""
TestSafetyCheck tests 'safety_check.py', the first job of every button.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os

import release_state

from . import ReleaseToolingTest, SAFETY


class TestSafetyCheck(ReleaseToolingTest):
  """
  The 'safety' job of every button runs 'safety_check.py' with the button
  and the name to export the verdict under. On any branch but 'main' it
  must refuse before it touches anything. Otherwise it decides the press
  from VERSION and, for a press that needs one, from the safety of the
  button; locks all nine safeties whatever it decided; and exports the
  verdict, 'ALLOW', 'STOP' or 'REFUSED', with a message in plain words,
  exiting 0 so the job can push the lock before it enforces the verdict.
  """

  def assertAllLocked(self) -> None:
    for name in SAFETY.values():
      with self.subTest(safety=name):
        self.assertEqual(self.readSafety(name), 'STOP')

  def check(self, button: str, **kwargs) -> tuple:
    code, output = self.runScript('safety_check.py', button,
                                  'SAFETY_VERDICT', **kwargs)
    env = self.readEnv()
    return code, output, env

  def test_armed_and_allowed(self) -> None:
    self.writeSafety('minor-dev', 'ALLOW\n')
    code, output, env = self.check('minor-dev')
    self.assertEqual(code, 0, output)
    self.assertEqual(env['SAFETY_VERDICT'], 'ALLOW')
    self.assertEqual(env['SAFETY_VERDICT_MESSAGE'], """'minor-dev' publishes
    1.2.0-dev0 and needs minor-dev.safety to read 'ALLOW'. It read
    'ALLOW'.""".replace('\n   ', ''))
    self.assertIn("minor-dev.safety read 'ALLOW', verdict: ALLOW", output)
    self.assertAllLocked()
    self.assertEqual(self.readCounters()['level'], 'none')

  def test_armed_and_stopped(self) -> None:
    code, output, env = self.check('micro-dev')
    self.assertEqual(code, 0, output)
    self.assertEqual(env['SAFETY_VERDICT'], 'STOP')
    self.assertEqual(env['SAFETY_VERDICT_MESSAGE'], """'micro-dev' would
    publish 1.1.1-dev0 but needs micro-dev.safety to read 'ALLOW' in the
    commit it was pressed on, and it read 'STOP'.""".replace('\n   ', ''))
    self.assertAllLocked()

  def test_armed_and_missing(self) -> None:
    os.remove(self.safetyPath('micro-lts'))
    self.writeVersion(level='micro', dev=1, rc=1)
    code, output, env = self.check('micro-lts')
    self.assertEqual(code, 0, output)
    self.assertEqual(env['SAFETY_VERDICT'], 'STOP')
    self.assertIn("and it read '<missing>'", env['SAFETY_VERDICT_MESSAGE'])
    self.assertAllLocked()

  def test_another_arming_is_spent(self) -> None:
    self.writeSafety('micro-rc', 'ALLOW\n')
    self.writeVersion(level='micro', dev=1)
    code, output, env = self.check('micro-dev')
    self.assertEqual(code, 0, output)
    self.assertEqual(env['SAFETY_VERDICT'], 'ALLOW')
    self.assertAllLocked()

  def test_free(self) -> None:
    self.writeVersion(level='minor', dev=2)
    code, output, env = self.check('minor-dev')
    self.assertEqual(code, 0, output)
    self.assertEqual(env['SAFETY_VERDICT'], 'ALLOW')
    self.assertEqual(env['SAFETY_VERDICT_MESSAGE'], """'minor-dev' publishes
    1.2.0-dev2 and needs no safety.""".replace('\n   ', ''))
    self.assertNotIn('.safety read', output)
    self.assertAllLocked()

  def test_refused(self) -> None:
    self.writeSafety('micro-lts', 'ALLOW\n')
    code, output, env = self.check('micro-lts')
    self.assertEqual(code, 0, output)
    self.assertEqual(env['SAFETY_VERDICT'], 'REFUSED')
    press = release_state.decide(self.info(), 'micro-lts')
    self.assertEqual(env['SAFETY_VERDICT_MESSAGE'], press.message)
    self.assertIn(press.message, output)
    self.assertAllLocked()
    self.assertEqual(self.readCounters(), self.info())

  def test_unreadable_version(self) -> None:
    self.writeText(self.versionPath, 'MAJOR=1\n')
    self.writeSafety('micro-dev', 'ALLOW\n')
    code, output, env = self.check('micro-dev')
    self.assertEqual(code, 0, output)
    self.assertEqual(env['SAFETY_VERDICT'], 'REFUSED')
    self.assertEqual(env['SAFETY_VERDICT_MESSAGE'], """'micro-dev' is
    refused, since VERSION cannot be read: VERSION lacks the lines for
    MINOR, MICRO, RC, DEV and LEVEL.""".replace('\n   ', ''))
    self.assertAllLocked()

  def test_main_only(self) -> None:
    self.writeSafety('minor-dev', 'ALLOW\n')
    code, output, env = self.check('minor-dev', ref='refs/heads/threading')
    self.assertEqual(code, 6)
    self.assertIn("""The release buttons run from 'main' alone, but
    'minor-dev' was pressed on 'threading'. Nothing was locked, tested or
    published.""".replace('\n   ', ''), output)
    self.assertEqual(env, dict())
    self.assertEqual(self.readSafety('minor-dev'), 'ALLOW')
    code, output, env = self.check('minor-dev', ref='refs/tags/1.1.0')
    self.assertEqual(code, 6)
    self.assertIn("was pressed on 'refs/tags/1.1.0'.", output)

  def test_outside_github_actions(self) -> None:
    self.writeSafety('micro-dev', 'ALLOW\n')
    code, output, env = self.check('micro-dev', ref=None)
    self.assertEqual(code, 0, output)
    self.assertEqual(env['SAFETY_VERDICT'], 'ALLOW')

  def test_printed_only(self) -> None:
    code, output = self.runScript('safety_check.py', 'micro-dev')
    self.assertEqual(code, 0, output)
    self.assertIn('Verdict: STOP', output)
    self.assertEqual(self.readEnv(), dict())

  def test_usage(self) -> None:
    code, output = self.runScript('safety_check.py')
    self.assertEqual(code, 1)
    self.assertIn('Usage: python bin/release_tooling/safety_check.py', output)
    code, output = self.runScript('safety_check.py', 'micro-dev', 'A', 'B')
    self.assertEqual(code, 2)
    self.assertIn("Received unexpected extra arguments: 'B'!", output)
    for old in ('dev', 'dev-minor', 'lts-micro', 'micro'):
      with self.subTest(button=old):
        code, output = self.runScript('safety_check.py', old)
        self.assertEqual(code, 3)
        self.assertIn("""Unrecognized button: '%s'! Expected one of:
        micro-dev, micro-rc, micro-lts, minor-dev, minor-rc, minor-lts,
        major-dev, major-rc or major-lts""".replace('\n       ', '') % old,
                      output)
    self.assertEqual(self.readSafety('micro-lts'), 'STOP')

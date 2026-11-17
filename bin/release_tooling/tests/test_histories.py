"""
TestHistories walks whole release histories through the scripts.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from . import ReleaseToolingTest, SAFETY


class TestHistories(ReleaseToolingTest):
  """
  A release history is a row of presses, each run as the workflows run
  it: 'safety_check.py', then 'version_get.py', then 'version_bump.py'
  once the publish would have succeeded. A press that needs its safety
  is armed first, as Asger arms it by hand before pressing. The walks
  start from the counters after 1.1.0.
  """

  def check(self, button: str) -> str:
    code, output = self.runScript('safety_check.py', button,
                                  'SAFETY_VERDICT')
    self.assertEqual(code, 0, output)
    return self.readEnv()['SAFETY_VERDICT']

  def press(self, button: str) -> tuple:
    verdict = self.check(button)
    armed = False
    if verdict == 'STOP':
      armed = True
      self.writeSafety(SAFETY[button], 'ALLOW\n')
      verdict = self.check(button)
    self.assertEqual(verdict, 'ALLOW', button)
    code, name = self.runScript('version_get.py', button)
    self.assertEqual(code, 0, name)
    code, output = self.runScript('version_bump.py', button)
    self.assertEqual(code, 0, output)
    return str.strip(name), armed

  def walk(self, *buttons: str) -> list:
    return [self.press(button) for button in buttons]

  def test_the_minor_release(self) -> None:
    walked = self.walk('minor-dev', 'minor-dev', 'minor-rc', 'minor-rc',
                       'minor-lts')
    self.assertEqual(walked, [
      ('1.2.0-dev0', True),
      ('1.2.0-dev1', False),
      ('1.2.0-rc0', True),
      ('1.2.0-rc1', False),
      ('1.2.0', True),
    ])
    self.assertEqual(self.readCounters(), self.info(minor=2, micro=1))

  def test_a_micro_line_climbing_to_minor(self) -> None:
    walked = self.walk('micro-dev', 'minor-dev', 'minor-rc', 'minor-lts')
    self.assertEqual(walked, [
      ('1.1.1-dev0', True),
      ('1.2.0-dev0', True),
      ('1.2.0-rc0', True),
      ('1.2.0', True),
    ])
    self.assertEqual(self.readCounters(), self.info(minor=2, micro=1))

  def test_a_micro_release_then_the_next_line(self) -> None:
    walked = self.walk('micro-dev', 'micro-dev', 'micro-rc', 'micro-lts',
                       'micro-dev')
    self.assertEqual(walked, [
      ('1.1.1-dev0', True),
      ('1.1.1-dev1', False),
      ('1.1.1-rc0', True),
      ('1.1.1', True),
      ('1.1.2-dev0', True),
    ])
    self.assertEqual(self.readCounters(),
                     self.info(micro=2, level='micro', dev=1))

  def test_a_major_release(self) -> None:
    walked = self.walk('minor-dev', 'major-dev', 'major-rc', 'major-lts')
    self.assertEqual([name for name, _ in walked],
                     ['1.2.0-dev0', '2.0.0-dev0', '2.0.0-rc0', '2.0.0'])
    self.assertEqual(self.readCounters(),
                     self.info(major=2, minor=0, micro=1))

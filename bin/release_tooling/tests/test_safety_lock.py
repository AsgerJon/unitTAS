"""
TestSafetyLock tests 'safety_lock.py'.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os

from . import ReleaseToolingTest, SAFETY


class TestSafetyLock(ReleaseToolingTest):
  """
  'safety_lock.py' locks every safety by hand, as a button does: all
  nine read 'STOP' afterwards, a missing one included, and it takes no
  arguments.
  """

  def test_locks_all_nine(self) -> None:
    self.writeSafety('micro-dev', 'ALLOW\n')
    self.writeSafety('major-lts', 'ALLOW\n')
    os.remove(self.safetyPath('minor-rc'))
    code, output = self.runScript('safety_lock.py')
    self.assertEqual(code, 0, output)
    for name in SAFETY.values():
      with self.subTest(safety=name):
        self.assertEqual(self.readSafety(name), 'STOP')
        self.assertIn('Locked: %s.safety' % name, output)

  def test_usage(self) -> None:
    code, output = self.runScript('safety_lock.py', 'micro-dev')
    self.assertEqual(code, 1)
    self.assertIn('Usage: python bin/release_tooling/safety_lock.py', output)

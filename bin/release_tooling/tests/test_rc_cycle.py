"""
TestRcCycle tests every button while a release candidate cycle is open.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from . import ReleaseToolingTest


class TestRcCycle(ReleaseToolingTest):
  """
  Once the rc0 of the locked level is out, the rc of that level is free
  and publishes the next rcN, and the lts of that level needs its safety,
  publishes the release, unlocks the level and moves the counters as the
  lts buttons always have: MICRO up for micro; MINOR up and MICRO to 1 for
  minor; MAJOR up, MINOR to 0 and MICRO to 1 for major; RC and DEV to 0.
  Every dev and every button of another level is refused, since an rc
  freezes the scope. The counters read as after 1.1.0, with dev0, dev1
  and rc0 published.
  """

  def test_micro_locked(self) -> None:
    accepted = ('micro-rc', 'micro-lts')
    release = dict(micro=2, rc=0, dev=0, level='none')
    self.assertPresses(self.info(level='micro', dev=2, rc=1), {
      'micro-dev': ('refused', accepted),
      'micro-rc': ('free', '1.1.1-rc1', dict(rc=2)),
      'micro-lts': ('armed', '1.1.1', release),
      'minor-dev': ('refused', accepted),
      'minor-rc': ('refused', accepted),
      'minor-lts': ('refused', accepted),
      'major-dev': ('refused', accepted),
      'major-rc': ('refused', accepted),
      'major-lts': ('refused', accepted),
    })

  def test_minor_locked(self) -> None:
    accepted = ('minor-rc', 'minor-lts')
    release = dict(minor=2, micro=1, rc=0, dev=0, level='none')
    self.assertPresses(self.info(level='minor', dev=2, rc=1), {
      'micro-dev': ('refused', accepted),
      'micro-rc': ('refused', accepted),
      'micro-lts': ('refused', accepted),
      'minor-dev': ('refused', accepted),
      'minor-rc': ('free', '1.2.0-rc1', dict(rc=2)),
      'minor-lts': ('armed', '1.2.0', release),
      'major-dev': ('refused', accepted),
      'major-rc': ('refused', accepted),
      'major-lts': ('refused', accepted),
    })

  def test_major_locked(self) -> None:
    accepted = ('major-rc', 'major-lts')
    release = dict(major=2, minor=0, micro=1, rc=0, dev=0, level='none')
    self.assertPresses(self.info(level='major', dev=2, rc=1), {
      'micro-dev': ('refused', accepted),
      'micro-rc': ('refused', accepted),
      'micro-lts': ('refused', accepted),
      'minor-dev': ('refused', accepted),
      'minor-rc': ('refused', accepted),
      'minor-lts': ('refused', accepted),
      'major-dev': ('refused', accepted),
      'major-rc': ('free', '2.0.0-rc1', dict(rc=2)),
      'major-lts': ('armed', '2.0.0', release),
    })

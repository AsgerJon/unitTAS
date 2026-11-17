"""
TestDevCycle tests every button while a dev cycle is open.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from . import ReleaseToolingTest


class TestDevCycle(ReleaseToolingTest):
  """
  With a level locked and no rc published yet, a dev press of the locked
  level is free and publishes the next devN; a dev press of a higher
  level needs its safety, relocks to that level and publishes its dev0; a
  dev press of a lower level is refused. The rc of the locked level needs
  its safety, publishes rc0 and so closes the dev cycle; every other rc
  is refused, and so is every lts, since a release needs an rc first.
  The counters read as after 1.1.0, with dev0 and dev1 published.
  """

  def test_micro_locked(self) -> None:
    accepted = ('micro-dev', 'micro-rc', 'minor-dev', 'major-dev')
    self.assertPresses(self.info(level='micro', dev=2), {
      'micro-dev': ('free', '1.1.1-dev2', dict(dev=3)),
      'micro-rc': ('armed', '1.1.1-rc0', dict(rc=1)),
      'micro-lts': ('refused', accepted),
      'minor-dev': ('armed', '1.2.0-dev0', dict(level='minor', dev=1)),
      'minor-rc': ('refused', accepted),
      'minor-lts': ('refused', accepted),
      'major-dev': ('armed', '2.0.0-dev0', dict(level='major', dev=1)),
      'major-rc': ('refused', accepted),
      'major-lts': ('refused', accepted),
    })

  def test_minor_locked(self) -> None:
    accepted = ('minor-dev', 'minor-rc', 'major-dev')
    self.assertPresses(self.info(level='minor', dev=2), {
      'micro-dev': ('refused', accepted),
      'micro-rc': ('refused', accepted),
      'micro-lts': ('refused', accepted),
      'minor-dev': ('free', '1.2.0-dev2', dict(dev=3)),
      'minor-rc': ('armed', '1.2.0-rc0', dict(rc=1)),
      'minor-lts': ('refused', accepted),
      'major-dev': ('armed', '2.0.0-dev0', dict(level='major', dev=1)),
      'major-rc': ('refused', accepted),
      'major-lts': ('refused', accepted),
    })

  def test_major_locked(self) -> None:
    accepted = ('major-dev', 'major-rc')
    self.assertPresses(self.info(level='major', dev=2), {
      'micro-dev': ('refused', accepted),
      'micro-rc': ('refused', accepted),
      'micro-lts': ('refused', accepted),
      'minor-dev': ('refused', accepted),
      'minor-rc': ('refused', accepted),
      'minor-lts': ('refused', accepted),
      'major-dev': ('free', '2.0.0-dev2', dict(dev=3)),
      'major-rc': ('armed', '2.0.0-rc0', dict(rc=1)),
      'major-lts': ('refused', accepted),
    })

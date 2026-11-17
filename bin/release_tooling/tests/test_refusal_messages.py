"""
TestRefusalMessages tests the words of every kind of refusal.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import release_state

from . import ReleaseToolingTest

NO_CYCLE = """No cycle is open since the last release, 1.1.0
(LEVEL=none)."""
DEV_CYCLE = """A dev cycle is open for 1.2.0 (LEVEL=minor), last published
as 1.2.0-dev1."""
RC_CYCLE = """A release candidate cycle is open for 1.2.0 (LEVEL=minor),
last published as 1.2.0-rc0."""
NEEDS_RC = """A release needs at least one release candidate before it,
even if it is identical."""
ACCEPT_DEVS = """Accepted now: micro-dev (1.1.1-dev0, needs
micro-dev.safety), minor-dev (1.2.0-dev0, needs minor-dev.safety),
major-dev (2.0.0-dev0, needs major-dev.safety)."""
ACCEPT_DEV_CYCLE = """Accepted now: minor-dev (1.2.0-dev2, no safety),
minor-rc (1.2.0-rc0, needs minor-rc.safety), major-dev (2.0.0-dev0, needs
major-dev.safety)."""
ACCEPT_RC_CYCLE = """Accepted now: minor-rc (1.2.0-rc1, no safety),
minor-lts (1.2.0, needs minor-lts.safety)."""


def _flat(*texts: str) -> str:
  return str.join(' ', str.split(str.join(' ', texts)))


class TestRefusalMessages(ReleaseToolingTest):
  """
  A refused press must say in plain words which button was pressed, the
  state VERSION is in, why the press is refused there, and which buttons
  would be accepted, each with what it would publish and the safety it
  would need. One refusal of each kind is pinned word for word.
  """

  def assertMessage(self, info: dict, button: str, *parts: str) -> None:
    press = release_state.decide(info, button)
    self.assertEqual(press.message, _flat("'%s' is refused." % button,
                                          *parts))

  def test_rc_with_no_cycle(self) -> None:
    self.assertMessage(self.info(), 'minor-rc', NO_CYCLE, """A release
    candidate needs a dev cycle before it.""", ACCEPT_DEVS)

  def test_lts_with_no_cycle(self) -> None:
    self.assertMessage(self.info(), 'micro-lts', NO_CYCLE, NEEDS_RC,
                       ACCEPT_DEVS)

  def test_dev_stepping_down(self) -> None:
    info = self.info(level='minor', dev=2)
    self.assertMessage(info, 'micro-dev', DEV_CYCLE, """A dev release may
    stay at the locked level or climb to a higher one, never step
    down.""", ACCEPT_DEV_CYCLE)

  def test_rc_of_another_level(self) -> None:
    info = self.info(level='minor', dev=2)
    self.assertMessage(info, 'major-rc', DEV_CYCLE, """The release
    candidate of this cycle comes from 'minor-rc'.""", ACCEPT_DEV_CYCLE)

  def test_lts_in_a_dev_cycle(self) -> None:
    info = self.info(level='minor', dev=2)
    self.assertMessage(info, 'minor-lts', DEV_CYCLE, NEEDS_RC,
                       ACCEPT_DEV_CYCLE)

  def test_dev_in_an_rc_cycle(self) -> None:
    info = self.info(level='minor', dev=2, rc=1)
    for button in ('major-dev', 'minor-dev'):
      with self.subTest(button=button):
        self.assertMessage(info, button, RC_CYCLE, """A release candidate
        freezes the scope: release what it froze, then open the next
        line.""", ACCEPT_RC_CYCLE)

  def test_other_level_in_an_rc_cycle(self) -> None:
    info = self.info(level='minor', dev=2, rc=1)
    for button in ('micro-rc', 'major-rc', 'micro-lts', 'major-lts'):
      with self.subTest(button=button):
        self.assertMessage(info, button, RC_CYCLE, """This cycle continues
        through 'minor-rc' and ends through 'minor-lts'.""",
                           ACCEPT_RC_CYCLE)

  def test_allowed_presses(self) -> None:
    press = release_state.decide(self.info(), 'minor-dev')
    self.assertEqual(press.message, _flat("""'minor-dev' publishes
    1.2.0-dev0 and needs minor-dev.safety to read 'ALLOW'."""))
    press = release_state.decide(self.info(level='minor', dev=2), 'minor-dev')
    self.assertEqual(press.message, _flat("""'minor-dev' publishes
    1.2.0-dev2 and needs no safety."""))

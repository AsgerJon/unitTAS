"""
A suite whose first test crashes the game, for test_crash.py to run on a Run (not a test module: unittest's discovery
doesn't load it). The crash is the game's own way: Minecraft.crashed(report), which its next loop shows and exits on,
as when a mod's code throws out of a tick. Reflection makes the report and calls it; no test-only code is needed.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from unittas.testcase import GameTestCase

DESCRIPTION = 'unitTAS: a crash on purpose'
CAUSE = 'unitTAS: thrown on purpose'


def crash(game) -> None:
  """The client crashes at its next loop: a CrashReport made by reflection, handed to Minecraft.crashed."""
  cause = game.reflect([], source={'new': 'java.lang.Throwable', 'args': [CAUSE]}, side='client', as_='ref')
  report = game.reflect([], source={'new': 'net.minecraft.crash.CrashReport', 'args': [DESCRIPTION, {
    'ref': cause['ref']}]}, side='client', as_='ref')
  game.reflect([{'call': 'crashed', 'args': [{'ref': report['ref']}]}], source='minecraft', side='client')


class ACrashTests(GameTestCase):

  def test_a_crashes_the_game(self) -> None:
    crash(self.game)
    # a wait the crash ends: the game goes before it is done
    self.game.ticks(200)
    self.fail('the game is still ticking after its crash')

  def test_b_never_runs(self) -> None:
    self.fail('ran after the game had crashed')

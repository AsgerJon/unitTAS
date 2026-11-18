"""
A suite whose first test crashes the game, for test_crash.py to run on a Run (not a test module: unittest's discovery
doesn't load it). The crash is the game's own way, as when a mod's code throws out of a tick: 1.7.10's
Minecraft.crashed(report), which its next loop shows and exits on; from 1.13 on Minecraft.delayCrash(report), which its
next tick saves and exits on. Reflection makes the report and calls it, by the version's readable names (CRASHES); no
test-only code is needed.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from ports import V1_7_10, version
from unittas.testcase import GameTestCase

DESCRIPTION = 'unitTAS: a crash on purpose'
CAUSE = 'unitTAS: thrown on purpose'


#  each version's crash report's class and Minecraft's method that crashes the client with one
CRASHES = {V1_7_10: ('net.minecraft.crash.CrashReport', 'crashed')}
MODERN_CRASH = ('net.minecraft.CrashReport', 'delayCrash')


def crash(game) -> None:
  """The client crashes at its next loop: a CrashReport made by reflection, handed to the game's own crash."""
  report, crashes = CRASHES.get(version(), MODERN_CRASH)
  cause = game.reflect([], source={'new': 'java.lang.Throwable', 'args': [CAUSE]}, side='client', as_='ref')
  made = game.reflect([], source={'new': report, 'args': [DESCRIPTION, {'ref': cause['ref']}]}, side='client',
                      as_='ref')
  game.reflect([{'call': crashes, 'args': [{'ref': made['ref']}]}], source='minecraft', side='client')


class ACrashTests(GameTestCase):

  def test_a_crashes_the_game(self) -> None:
    crash(self.game)
    # a wait the crash ends: the game goes before it is done
    self.game.ticks(200)
    self.fail('the game is still ticking after its crash')

  def test_b_never_runs(self) -> None:
    self.fail('ran after the game had crashed')

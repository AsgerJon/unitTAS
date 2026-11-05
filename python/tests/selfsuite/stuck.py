"""
The 'self-stuck' suite's TimeLimitTests (src/self/java/.../self/TimeLimitTests.java), by the same names: run on
purpose only. Its first test runs past its time limit (3 s, by the clock): unwatched, it is stopped with no result,
never a verdict; watched, the watcher is asked first, and a 'wait' lets it reach its verdict. The second runs as ever.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from unittas.testcase import GameTestCase


class TimeLimitTests(GameTestCase):
  timeout_seconds = 3

  def testA_runsPastItsTime(self) -> None:
    # 200 client ticks, 10 s: past its 3 s
    self.game.ticks(200)

  def testB_theNextRunsAsEver(self) -> None:
    self.game.ticks(2)

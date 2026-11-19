"""
The look turned at a rate (mouse.rate, SPEC.md 19.7 step 12) on the
run's port: the client's player turns every frame by the frame's share
of a tick, as a hand turns a mouse. A rate r for n ticks turns about r
times n (the game time from the request to the last frame before the
answer: short of n by a frame's share at each end); the look turned in
more frames than ticks, each by its share of a tick, not a tick's; the
pitch stops at straight down, the rate still in force; player.look, 0
and 0, a screen opening and the reset stop it, and it stays stopped; a
screen open refuses a rate; the answer is the player's bearing (its
tick, where it is, its look and its motion). On the agent's versions
(1.16.1 on): the 1.7.10 probe has no mouse.rate.

  python -m unittas.selftest test_mouse.
  (through the watcher: "probe test_mouse on 26.3")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from ports import V1_16_1, V1_20_1, V1_21_1, V26_3, onlyOn, probeGame, start
from probegame import READY_SECONDS
from unittas.api import Game
from unittas.errors import NotReady
from unittas.perception import Perception
from unittas.reset import reset
from unittas.values import Look

#  how long a rate is watched, in ticks
TICKS = 40
#  how far short of r times n the turn may be, in ticks' worth: a
#  frame's share at each end, a frame at most a tick (20 frames a second)
SHORT = 2.0


@onlyOn(V26_3, V1_21_1, V1_20_1, V1_16_1,
        why="mouse.rate is the agent's (SPEC.md 19.7 step 12); 1.7.10's "
            "probe has none")
class MouseRateTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = probeGame('mouse')
    #  a fresh test world, as the other modules make theirs
    shutil.rmtree(os.path.join(cls.launched.gameDir, 'saves', 'unittas'),
                  ignore_errors=True)
    try:
      connection = cls.launched.start(READY_SECONDS)
      connection.events.waitFor(
        lambda event: event.get('event') == 'ready', READY_SECONDS)
      cls.game = Game(connection)
      cls.game.request('world.create', {}, timeout=240)
    except BaseException:
      cls.launched.stop()
      raise

  @classmethod
  def tearDownClass(cls) -> None:
    cls.launched.stop()

  def setUp(self) -> None:
    reset(self.game.connection, at=start())
    self.game.look(0.0, 0.0)

  def rate(self, yaw: float, pitch: float) -> int:
    """The rate set; the client tick it was set in."""
    answer = self.game.request('mouse.rate',
                               {'yaw': float(yaw), 'pitch': float(pitch)})
    return answer['tick']

  def still(self, ticks: int = 10) -> Perception:
    """What is perceived, and again after 'ticks': the same look."""
    seen = self.game.perceive()
    self.game.ticks(ticks)
    after = self.game.perceive()
    self.assertEqual(seen.look, after.look, 'the look turns on')
    return after

  def test_a_a_rate_turns_by_the_ticks_in_frames(self) -> None:
    yaw, pitch = 2.0, 0.5
    set_ = self.rate(yaw, pitch)
    self.game.ticks(TICKS)
    seen = self.game.perceive()
    ticks = seen.tick - set_
    self.assertGreaterEqual(ticks, TICKS)
    self.assertEqual((yaw, pitch, False),
                     (seen.mouseRate.yaw, seen.mouseRate.pitch,
                      seen.mouseRate.none))
    for name, rate, turned in (('yaw', yaw, seen.look.yaw),
                               ('pitch', pitch, seen.look.pitch)):
      with self.subTest(name):
        self.assertLessEqual(turned, rate * ticks + 1e-3)
        self.assertGreaterEqual(turned, rate * (ticks - SHORT))
    #  more frames than ticks: each a frame's share of a tick
    self.assertGreater(seen.mouseRate.frames, ticks)

  def test_b_the_pitch_stops_straight_down(self) -> None:
    self.game.look(0.0, 80.0)
    self.rate(0.0, 5.0)
    self.game.ticks(10)
    seen = self.game.perceive()
    self.assertEqual(Look(0.0, 90.0), seen.look)
    self.assertEqual(5.0, seen.mouseRate.pitch, 'the rate is still in force')

  def test_c_look_stops_it(self) -> None:
    self.rate(3.0, 0.0)
    self.game.ticks(5)
    self.game.look(10.0, 0.0)
    seen = self.still()
    self.assertTrue(seen.mouseRate.none)
    self.assertEqual(Look(10.0, 0.0), seen.look)

  def test_d_0_and_0_stops_it(self) -> None:
    self.rate(3.0, 0.0)
    self.game.ticks(5)
    stopped = self.game.mouseRate(0, 0)
    self.assertGreater(stopped.look.yaw, 0.0, 'it turned before it stopped')
    seen = self.still()
    self.assertTrue(seen.mouseRate.none)
    self.assertEqual(0, seen.mouseRate.frames)
    self.assertEqual(stopped.look, seen.look)

  def test_e_a_screen_stops_it_and_refuses_one(self) -> None:
    self.rate(3.0, 0.0)
    self.game.ticks(5)
    self.game.openScreen('inventory')
    try:
      seen = self.still()
      self.assertTrue(seen.mouseRate.none)
      with self.assertRaises(NotReady):
        self.game.mouseRate(1, 0)
      #  0 and 0 is no rate, screen or not
      self.game.mouseRate(0, 0)
    finally:
      self.game.closeScreen()
    #  stopped, it stays stopped
    after = self.still()
    self.assertEqual(seen.look, after.look)
    self.assertTrue(after.mouseRate.none)

  def test_f_the_answer_is_the_player_s_bearing(self) -> None:
    """Its tick, where it is, its look and its motion: the client's."""
    self.game.ticks(5)
    before = self.game.perceive()
    bearing = self.game.mouseRate(1.0, 0.0)
    self.game.mouseRate(0, 0)
    self.assertGreater(bearing.tick, before.tick)
    #  standing still on the ground: where it stood, as it moved
    self.assertEqual(before.pos, bearing.pos)
    self.assertEqual(before.motion, bearing.motion)
    self.assertEqual(before.look, bearing.look)

  def test_g_the_reset_stops_it(self) -> None:
    self.rate(3.0, 0.0)
    self.game.ticks(5)
    reset(self.game.connection, at=start())
    seen = self.still()
    self.assertTrue(seen.mouseRate.none)


if __name__ == '__main__':
  unittest.main()

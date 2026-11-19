"""
The look turned at a rate (mouse.rate, SPEC.md 19.7 step 12) on the
run's port: the client's player turns every frame by the frame's share
of a tick, as a hand turns a mouse, and at each tick's end up to it. So
a rate r for n ticks has turned r times n at a tick's end, whatever the
frame rate (the frames in between are the machine's: their count is
not tested, only that there were some); a rate asked every tick turns
the whole of each tick; the pitch stops at straight down, the rate
still in force; player.look, 0 and 0, a screen opening and the reset
stop it, and it stays stopped; a screen open refuses a rate; the answer
is the player's bearing (its tick, where it is, its look and its
motion). On the agent's versions (1.16.1 on): the 1.7.10 probe has no
mouse.rate.

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

  def test_a_a_rate_turns_r_times_the_ticks(self) -> None:
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
        self.assertAlmostEqual(rate * ticks, turned, delta=1e-3)
    #  turned in frames between the ticks too (how many is the machine's)
    self.assertGreater(seen.mouseRate.frames, 0)

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

  def test_g_asked_every_tick_it_turns_each_tick_whole(self) -> None:
    """
    A rate asked again turns the whole of the time between the two
    requests: the old rate up to the change, the new one from it
    (meantwell's finding on 26.3: two thirds turned when asked every
    tick, a frame's share lost at each request). Between two answers the
    look turns the rate in force times their ticks apart.
    """
    before = self.game.request('mouse.rate', {'yaw': 0.0, 'pitch': 0.0})
    rates = [6.0, 12.0, 15.0, 15.0, 15.0, 15.0, 12.0, 10.0, 4.0, 0.0]
    answers = [self.game.request('mouse.rate', {'yaw': rate, 'pitch': 0.0})
               for rate in rates]
    self.assertEqual(0.0, answers[0]['look']['yaw'] - before['look']['yaw'])
    for rate, was, now in zip(rates, answers, answers[1:]):
      with self.subTest(rate=rate, tick=now['tick']):
        ticks = now['tick'] - was['tick']
        turned = now['look']['yaw'] - was['look']['yaw']
        self.assertAlmostEqual(rate * ticks, turned, delta=1e-3)

  def test_h_the_reset_stops_it(self) -> None:
    self.rate(3.0, 0.0)
    self.game.ticks(5)
    reset(self.game.connection, at=start())
    seen = self.still()
    self.assertTrue(seen.mouseRate.none)


if __name__ == '__main__':
  unittest.main()

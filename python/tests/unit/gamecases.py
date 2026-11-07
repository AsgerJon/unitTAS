"""
GameTestCases for test_testcase.py to run: not a test module (unittest's discovery doesn't load it), so these classes
run only on the fake game a test gives them. test_testcase reaches them through this module, never by importing the
classes, which unittest's loader would then take for tests of its own.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import time
import unittest

from unittas.run import Run
from unittas.testcase import GameTestCase, MultiplayerTestCase


class ATests(GameTestCase):

  def setUp(self) -> None:
    #  a setUp of its own that calls nothing: the reset comes anyway
    self.mine = True

  def test_1_passes(self) -> None:
    self.assertEqual('Given', self.command('/say hi').lines[0])

  def test_2_fails(self) -> None:
    self.assertEqual(1, 2, 'on purpose')


class BTests(GameTestCase):

  def test_skipped(self) -> None:
    self.skipTest('not today')


class CTests(GameTestCase):
  shared_world = True

  @unittest.expectedFailure
  def test_parked(self) -> None:
    self.assertTrue(False)


class TerrainTests(GameTestCase):
  """A class that needs real terrain: a world of its own (a map, say), made for it."""
  world = {'type': 'default', 'seed': 1234}

  def test_in_its_own_world(self) -> None:
    self.assertIn('fresh for TerrainTests, made as it asks', Run.current.worldNote)


class AfterTerrainTests(GameTestCase):

  def test_back_on_the_flat_world(self) -> None:
    self.assertIn('the kept world put back', Run.current.worldNote)


class ChatTests(GameTestCase):

  def test_its_own_chat(self) -> None:
    self.command('/say hi')
    self.assertEqual(('Given',), tuple(line.plain for line in self.chat()))


class StallTests(GameTestCase):
  """Its first test meets a game that stopped ticking; the second must not run."""

  def test_a_meets_a_stall(self) -> None:
    self.command('/stall')

  def test_b_never_runs(self) -> None:
    self.fail('ran after the game had stopped ticking')


class SlowTests(GameTestCase):
  """Its first test runs past its time limit (1 s here): no result; the second runs as ever."""
  timeout_seconds = 1

  def test_a_loops(self) -> None:
    while True:
      self.game.ticks(1)
      time.sleep(0.01)

  def test_b_runs(self) -> None:
    pass


class CrashTests(GameTestCase):
  """Its first test meets the game crashing; the second must not run."""

  def test_a_meets_a_crash(self) -> None:
    self.command('/crash')

  def test_b_never_runs(self) -> None:
    self.fail('ran after the game had crashed')


class SaveCaseTests(GameTestCase):
  """For save mode: each test notes the save it found open (by the run: a class's state outlives a run)."""
  seen = {}

  def test_a_sees_its_save(self) -> None:
    save = self.save()
    SaveCaseTests.seen.setdefault(Run.current, []).append((save.folder, save.load, save.loadErrors))

  def test_b_passes(self) -> None:
    pass


class ModErrorTests(GameTestCase):
  """A mod's code that throws is a result: an ERROR, and the run goes on."""

  def test_a_mod_throws(self) -> None:
    self.command('/mod-throws')

  def test_b_runs_after(self) -> None:
    self.assertEqual('Given', self.command('/say hi').lines[0])


class MpTerrainTests(MultiplayerTestCase):
  """A multiplayer class can't ask for a world of its own yet: its server's world is the run's flat one."""
  world = {'type': 'default'}

  def test_never_runs(self) -> None:
    pass


class MpCaseTests(MultiplayerTestCase):
  """A multiplayer class: its test notes the games it was given (by the run: a class's state outlives a run)."""
  clients = ('alice', 'bob')
  seen = {}

  def test_a_three_games(self) -> None:
    self.assertIsNotNone(self.server)
    MpCaseTests.seen[Run.current] = {'server': self.server, 'alice': self.alice, 'bob': self.bob,
                                     'bobName': self.bob.playerName()}

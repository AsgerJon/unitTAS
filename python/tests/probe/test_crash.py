"""
Step 8b of phase 3 (SPEC.md section 9.3): a crash, said before the game goes. In the development client, crashed on
purpose the game's own way (crashsuite.crash):
- the probe's 'crash' event, with the crash report's file and its summary, then 'quit' with reason crash, and the
  game gone;
- in a Python run, the test it came in is NO RESULT naming the crash and its report, and the test after it isn't run;
- a quit from a world crashes nothing (the crash event found it did).
Each removes the crash report it caused from the game's crash-reports/.

  python -m unittas.selftest test_crash.      (through the watcher: "probe test_crash.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import re
import unittest

import crashsuite
from probegame import GONE_SECONDS, READY_SECONDS, ROOT, results
from unittas.api import Game
from unittas.dev import DevGame
from unittas.gamefiles import removeTree
from unittas.run import Run, runSuite

RESULT = re.compile(r'^(\S+) \.\.\. (.+?) \(\d+\.\d s\)$')


def isEvent(kind: str):
  return lambda event: event.get('event') == kind


class CrashTests(unittest.TestCase):

  def started(self, name: str) -> tuple:
    game = DevGame(ROOT, results(), name)
    self.addCleanup(game.stop)
    connection = game.start()
    connection.events.waitFor(isEvent('ready'), READY_SECONDS)
    return game, connection

  def removeReport(self, path: str) -> None:
    """The crash report this test caused, and only that file."""
    if path and os.path.isfile(path) and os.path.dirname(path).endswith('crash-reports'):
      os.remove(path)

  def test_a_the_crash_event_before_the_game_goes(self) -> None:
    game, connection = self.started('crash')
    mark = connection.events.mark()
    crashsuite.crash(Game(connection))
    crash = connection.events.waitFor(isEvent('crash'), 60, since=mark)
    self.addCleanup(self.removeReport, crash.get('report'))
    self.assertIn(crashsuite.DESCRIPTION, crash['summary'])
    self.assertIn(crashsuite.CAUSE, crash['summary'])
    self.assertTrue(os.path.isfile(crash['report']), crash)
    with open(crash['report'], encoding='utf-8', errors='replace') as file:
      self.assertIn(crashsuite.DESCRIPTION, file.read())
    gone = connection.events.waitFor(isEvent('quit'), 30, since=mark)
    self.assertEqual('crash', gone['reason'])
    self.assertTrue(game.ended(GONE_SECONDS), 'the game is still running %s s after its crash' % GONE_SECONDS)

  def test_b_a_crash_in_a_run_has_no_result(self) -> None:
    game, connection = self.started('crash-run')
    run = Run(Game(connection), game.gameDir, os.path.join(game.results, 'run'), stop=game.stop)
    try:
      run.begin()
      runSuite(run, unittest.TestLoader().loadTestsFromTestCase(crashsuite.ACrashTests), stream=io.StringIO())
    finally:
      report = run.finish()
    crash = [event for event in connection.events.since(0) if event.get('event') == 'crash']
    self.assertEqual(1, len(crash), 'one crash event')
    self.addCleanup(self.removeReport, crash[0].get('report'))
    with open(report, encoding='utf-8') as file:
      lines = file.read().split('\n')
    outcomes = [(found.group(1), found.group(2)) for found in map(RESULT.match, lines) if found]
    self.assertEqual([('ACrashTests.test_a_crashes_the_game', 'NO RESULT'), ('ACrashTests.test_b_never_runs',
                                                                             'NO RESULT')], outcomes)
    said = "the game crashed: %s" % crash[0]['summary']
    self.assertTrue(lines[1].startswith('NO TEST RESULT could be obtained for 2 tests: %s' % said), lines[1])
    self.assertIn('its crash report: %s' % crash[0]['report'], lines[1])
    test_b = lines[[i for i, line in enumerate(lines) if line.startswith('ACrashTests.test_b')][0] + 1]
    self.assertIn('not run: no test result could be obtained after %s' % said, test_b)
    self.assertEqual('FAILED (no results=2)', [line for line in lines if line][-1])

  def test_c_a_quit_from_a_world_crashes_nothing(self) -> None:
    # found by the crash event (2026-11-05): the probe's quit left the world and shut down with the game still counted
    # as focused, so its last frame turned a player that was gone (EntityRenderer.updateCameraAndRender): a
    # NullPointerException, a crash report, and an exit by the crash path, at nearly every quit from a world
    game, connection = self.started('crash-quit')
    reports = os.path.join(game.gameDir, 'crash-reports')
    before = set(os.listdir(reports)) if os.path.isdir(reports) else set()
    world = os.path.join(game.gameDir, 'saves', 'unittas')
    if os.path.lexists(world):
      # an earlier run's test world, that folder only, as a run removes it
      removeTree(world)
    connection.request('world.create', {'folder': 'unittas'}, timeout=240)
    mark = connection.events.mark()
    connection.request('quit', {'reason': 'test_c'}, timeout=10)
    gone = connection.events.waitFor(isEvent('quit'), 30, since=mark)
    self.assertEqual('asked', gone['reason'])
    self.assertTrue(game.ended(GONE_SECONDS), 'the game is still running %s s after quit' % GONE_SECONDS)
    after = set(os.listdir(reports)) if os.path.isdir(reports) else set()
    for name in after - before:
      self.addCleanup(self.removeReport, os.path.join(reports, name))
    crashes = [event for event in connection.events.since(mark) if event.get('event') == 'crash']
    self.assertEqual([], crashes, 'the quit crashed the game')
    self.assertEqual(set(), after - before, 'a crash report from the quit')


if __name__ == '__main__':
  unittest.main()

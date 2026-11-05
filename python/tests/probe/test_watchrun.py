"""
Step 8b of phase 3 (SPEC.md section 9.3): the watch on a Python run, in the development client, with the self-stuck
suite's twin (tests/selfsuite/stuck.py, TimeLimitTests: a test past its 3 s time limit).
- Unwatched: that test is stopped, NO RESULT, and the next one runs as ever.
- Watched: an alarm asks first. The test bench answers it as a watcher would (alarm.txt read, its pictures there,
  '1 wait 30' written to decision.txt), and the test reaches its verdict: ok, and the next one too.

  python -m unittas.selftest test_watchrun.      (through the watcher: "probe test_watchrun.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import re
import sys
import threading
import time
import unittest

from probegame import READY_SECONDS, ROOT, results
from unittas.api import Game
from unittas.dev import DevGame
from unittas.run import Run, runSuites
from unittas.watch import Watch

#  the self suites live beside the probe's tests, not among them
sys.path.insert(0, os.path.join(ROOT, 'python', 'tests'))
RESULT = re.compile(r'^(\S+) \.\.\. (.+?) \(\d+\.\d s\)$')


class WatchRunTests(unittest.TestCase):

  def run_(self, name: str, watched: bool, watcher=None) -> list:
    """The stuck suite on a watched or unwatched Run of a development client; the report's lines."""
    game = DevGame(ROOT, results(), name)
    connection = game.start()
    connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    run = Run(Game(connection), game.gameDir, os.path.join(game.results, 'run'), stop=game.stop)
    watch = Watch(run, watched=watched, pictures=5, decide=120)
    watch.start()
    if watcher is not None:
      threading.Thread(target=watcher, args=(run.results,), daemon=True).start()
    try:
      run.begin()
      runSuites(run, ['selfsuite.stuck'], stream=io.StringIO())
    finally:
      watch.stop()
      report = run.finish()
    with open(report, encoding='utf-8') as file:
      return file.read().split('\n')

  def outcomes(self, lines: list) -> list:
    return [(found.group(1), found.group(2)) for found in map(RESULT.match, lines) if found]

  def test_1_unwatched_past_its_time_is_no_result(self) -> None:
    lines = self.run_('watchrun-unwatched', False)
    self.assertEqual([('TimeLimitTests.testA_runsPastItsTime', 'NO RESULT'),
                      ('TimeLimitTests.testB_theNextRunsAsEver', 'ok')], self.outcomes(lines), '\n'.join(lines))
    self.assertEqual('NO TEST RESULT could be obtained for 1 test: ran past its time limit (3 s): no verdict', lines[1])
    self.assertEqual('FAILED (no results=1)', [line for line in lines if line][-1])

  def test_2_watched_an_alarm_and_a_wait(self) -> None:
    seen = {}

    def watcher(folder: str) -> None:
      """
      As a watching LLM, by what each alarm says: the time limit's is looked at (its two pictures there) and answered
      'wait 30'. Any other alarm (a test world that doesn't load: 1.7.10's integrated server can drop its own local
      connection, 2026-11-05) isn't this test's, and gets an abort saying so, so the run ends with that reason.
      """
      alarm = os.path.join(folder, 'alarm.txt')
      deadline = time.monotonic() + 600
      answered = set()
      while time.monotonic() < deadline and 'done' not in seen:
        try:
          with open(alarm, encoding='utf-8') as file:
            text = file.read()
        except FileNotFoundError:
          time.sleep(0.2)
          continue
        number = int(re.match(r'unitTAS alarm (\d+),', text).group(1))
        if number in answered:
          time.sleep(0.2)
          continue
        answered.add(number)
        what = re.search(r'^what: (.*)$', text, re.MULTILINE).group(1)
        if 'past its time limit' in what:
          seen['alarm'] = text
          seen['pictures'] = [os.path.isfile(os.path.join(folder, 'screenshots', 'alarm-%d-%s.png' % (number, which)))
                              for which in 'ab']
          answer = '%d wait 30' % number
        else:
          seen.setdefault('others', []).append(what)
          answer = "%d abort not this test's alarm: %s" % (number, what)
        with open(os.path.join(folder, 'decision.txt'), 'w', encoding='utf-8') as file:
          file.write(answer + '\n')

    try:
      lines = self.run_('watchrun-watched', True, watcher)
    finally:
      seen['done'] = True
    self.assertEqual([], seen.get('others', []), 'alarms other than the time limit\'s')
    self.assertIn('what: the test has run past its time limit (3 s)', seen.get('alarm', ''))
    self.assertEqual([True, True], seen.get('pictures'), 'the alarm\'s two pictures')
    self.assertEqual([('TimeLimitTests.testA_runsPastItsTime', 'ok'), ('TimeLimitTests.testB_theNextRunsAsEver', 'ok')],
                     self.outcomes(lines), '\n'.join(lines))
    self.assertEqual('OK', [line for line in lines if line][-1])
    folder = os.path.join(results(), 'watchrun-watched', 'run')
    with open(os.path.join(folder, 'alarms.txt'), encoding='utf-8') as file:
      self.assertIn('alarm 1 answered: wait 30 s', file.read())
    self.assertTrue(os.path.isfile(os.path.join(folder, 'screenshots', 'watch-live.png')), 'no live picture')
    with open(os.path.join(folder, 'watch.txt'), encoding='utf-8') as file:
      self.assertIn('client: ticking', file.read())


if __name__ == '__main__':
  unittest.main()

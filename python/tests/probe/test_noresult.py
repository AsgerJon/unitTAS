"""
No result, in the Java runner (SPEC.md 9.8): a test stopped by its own time limit has no verdict, since the limit is
wall-clock time and a slow machine could reach it in a test that would pass. Through java.run, unwatched (a watched
run asks its watcher instead of stopping the test): the self-stuck suite's TimeLimitTests. Its first test is
NO RESULT, the report says so before any test line, and the next test runs as ever.

  python -m unittas.selftest test_noresult.      (through the watcher: "probe test_noresult.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import re
import shutil
import unittest

from probegame import READY_SECONDS, ROOT, results
from unittas.dev import DevGame

RESULT = re.compile(r'^(\S+) \.\.\. (.+?) \(\d+\.\d s\)$')


class NoResultTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.game = DevGame(ROOT, results(), 'noresult')
    shutil.rmtree(os.path.join(cls.game.gameDir, 'saves', 'unittas'), ignore_errors=True)
    cls.connection = cls.game.start()
    cls.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop()

  def test_a_java_test_past_its_time_has_no_result(self) -> None:
    folder = os.path.join(self.game.results, 'java')
    mark = self.connection.events.mark()
    value = self.connection.request('java.run', {'suites': ['self-stuck'], 'filter': 'TimeLimitTests',
                                                 'results': folder, 'watched': False}, timeout=600)
    self.assertFalse(value['ok'])
    self.assertEqual(1, value['counts']['no_results'], value['counts'])
    with open(value['report'], encoding='utf-8') as file:
      lines = file.read().split('\n')
    self.assertTrue(lines[1].startswith('NO TEST RESULT could be obtained for 1 test: TimeLimitTests.testA'), lines[1])
    outcomes = [(found.group(1), found.group(2)) for found in map(RESULT.match, lines) if found]
    self.assertEqual([('TimeLimitTests.testA_runsPastItsTime', 'NO RESULT'),
                      ('TimeLimitTests.testB_theNextRunsAsEver', 'ok')], outcomes)
    self.assertEqual('FAILED (no results=1)', [line for line in lines if line][-1])
    events = [event for event in self.connection.events.since(mark) if event.get('event') == 'java.result']
    self.assertEqual(['no_result', 'ok'], [event['outcome'] for event in events])


if __name__ == '__main__':
  unittest.main()

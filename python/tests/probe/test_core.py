"""
Step 8 of phase 2 (SPEC.md section 8.3): the rest of the core. log.write; debug.threads, answering while the server
sleeps in its tick, and debug.trace of a world load; hooks.run, counted by unitTAS's own SelfPlugin; java.run, today's
Java runner driven over the socket: unitTAS's own suites self, self-red and nosuch, their report as
bin/self_red_check.py wants it, a java.result for each of its lines, the game's operations NotReady meanwhile, the
game back at the title screen after it, and a cancelled run. One launch, its tests in order.

  python -m unittas.selftest test_core.      (through the watcher: "probe test_core.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
import unittest

from probegame import GONE_SECONDS, READY_SECONDS, ROOT, results
from unittas.dev import DevGame
from unittas.errors import BadRequest, Cancelled, LinkTimeout, NotReady

SELF_PLUGIN = 'io.github.asgerjon.unittas.self.SelfPlugin'
#  a line of the Java runner's report.txt, as bin/self_red_check.py reads it
RESULT = re.compile(r'^(\S+) \.\.\. (.+?) \(\d+\.\d s\)$')
#  java.result's outcomes, and how the report words each
WORDS = {'ok': 'ok', 'fail': 'FAIL', 'error': 'ERROR', 'skipped': 'skipped', 'expected_failure': 'expected failure',
         'unexpected_success': 'unexpected success', 'problem': 'problem'}
#  the Java run of self, self-red and nosuch: bin/self_red_check.py's last line, as counts
RED_COUNTS = {'failures': 0, 'errors': 3, 'skipped': 2, 'expected_failures': 3, 'unexpected_successes': 1,
              'problems': 1}
#  a whole Java run of unitTAS's own suites, its fresh worlds included
JAVA_SECONDS = 900.0


def isJavaResult(event: dict) -> bool:
  return event.get('event') == 'java.result'


class CoreTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.game = DevGame(ROOT, results(), 'core')
    shutil.rmtree(os.path.join(cls.game.gameDir, 'saves', 'unittas'), ignore_errors=True)
    cls.connection = cls.game.start()
    cls.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop()

  def request(self, op, args=None, side=None, timeout=60.0):
    return self.connection.request(op, args, side=side, timeout=timeout)

  def logOnceItHas(self, text: str, seconds: float = 10.0) -> str:
    """The game's log, once it holds the text (the game's output reaches the file a little later)."""
    deadline = time.monotonic() + seconds
    while True:
      with open(os.path.join(self.game.results, 'gradle.log'), encoding='utf-8', errors='replace') as log:
        found = log.read()
      if text in found or time.monotonic() > deadline:
        return found
      time.sleep(0.2)

  def javaResults(self, name: str) -> str:
    return os.path.join(self.game.results, 'java-' + name)

  def firstJavaResult(self, run, mark: int, seconds: float = 300.0) -> dict:
    """The run's first java.result; the run's own error at once if it answered first."""
    deadline = time.monotonic() + seconds
    while True:
      if run.done:
        run.result(0)
        self.fail('java.run answered before any java.result came')
      try:
        return self.connection.events.waitFor(isJavaResult, 1.0, since=mark)
      except LinkTimeout:
        if time.monotonic() > deadline:
          raise

  def selfPlugin(self, field: str) -> int:
    return self.request('reflect.get', {'from': {'class': SELF_PLUGIN}, 'path': [field]}, side='server')

  # ---------------------------------------------------------------- log.write

  def test_01_log_write(self) -> None:
    self.assertEqual({}, self.request('log.write', {'message': '=== CoreTests.test_01_log_write ==='}))
    self.assertEqual({}, self.request('log.write', {'message': 'a warning from the tests', 'level': 'warn'}))
    log = self.logOnceItHas('a warning from the tests')
    self.assertRegex(log, r'(?m)/INFO\] \[unitTAS\]: === CoreTests\.test_01_log_write ===$')
    self.assertRegex(log, r'(?m)/WARN\] \[unitTAS\]: a warning from the tests$')

  def test_02_log_write_refuses(self) -> None:
    for args, field in (({}, 'message'), ({'message': 7}, 'message'), ({'message': 'x', 'level': 'loud'}, 'level')):
      with self.assertRaises(BadRequest) as refused:
        self.request('log.write', args)
      self.assertEqual(field, refused.exception.fields.get('field'), args)

  # ---------------------------------------------------------------- debugging

  def test_03_debug_threads(self) -> None:
    text = self.request('debug.threads')['text']
    self.assertIn('screen: net.minecraft.client.gui.GuiMainMenu', text)
    self.assertIn('"Client thread"', text)
    self.assertIn('"unitTAS link"', text)

  def test_04_debug_trace_of_a_world_load(self) -> None:
    self.request('world.create', {}, timeout=240)
    lines = self.request('debug.trace')['lines']
    self.assertTrue(lines, 'the world load was traced')
    self.assertIn('launching the integrated server', lines[0])
    self.assertIn('the test world is loaded', lines[-1])

  def test_05_debug_threads_while_the_server_sleeps(self) -> None:
    # the server sleeps 4 s in its next tick; debug.threads answers meanwhile, and shows it asleep there
    self.request('debug.lag', {'ms': 4000, 'ticks': 1}, side='server')
    time.sleep(0.5)
    asked = time.monotonic()
    text = self.request('debug.threads', timeout=10)['text']
    self.assertLess(time.monotonic() - asked, 2.0, 'debug.threads waited for the sleeping server')
    server = text[text.index('"Server thread"'):]
    server = server[:server.index('\n\n')]
    self.assertIn('TIMED_WAITING', server.split('\n')[0])
    self.assertIn('java.lang.Thread.sleep', server)
    self.request('ticks.wait', {'side': 'server', 'ticks': 1}, timeout=30)

  # ---------------------------------------------------------------- the mods' hooks

  def test_06_hooks_are_called(self) -> None:
    setUp, tornDown = self.selfPlugin('worldsSetUp'), self.selfPlugin('worldsTornDown')
    self.request('hooks.run', {'hook': 'setUpWorld'})
    self.request('hooks.run', {'hook': 'tearDownWorld'})
    self.request('hooks.run', {'hook': 'tearDownWorld'})
    self.assertEqual((setUp + 1, tornDown + 2), (self.selfPlugin('worldsSetUp'), self.selfPlugin('worldsTornDown')))

  # ---------------------------------------------------------------- java.run

  def test_07_java_run_needs_the_title_screen(self) -> None:
    with self.assertRaises(NotReady):
      self.request('java.run', {'suites': ['self'], 'results': self.javaResults('never')})
    self.request('world.close', timeout=240)

  def test_08_java_run_refuses(self) -> None:
    folder = self.javaResults('never')
    for args, field in (({'suites': ['self']}, 'results'),
                        ({'suites': ['self'], 'results': 'a/relative/folder'}, 'results'),
                        ({'suites': 'self', 'results': folder}, 'suites'),
                        ({'suites': ['self', 3], 'results': folder}, 'suites'),
                        ({'suites': ['self'], 'results': folder, 'watched': 'yes'}, 'watched'),
                        ({'suites': ['self'], 'results': folder, 'saves': ['../elsewhere']}, 'saves')):
      with self.assertRaises(BadRequest) as refused:
        self.request('java.run', args)
      self.assertEqual(field, refused.exception.fields.get('field'), args)
    self.assertFalse(os.path.exists(folder), 'a refused java.run made nothing')

  def test_09_java_run_of_unitTAS_s_own_suites(self) -> None:
    folder = self.javaResults('red')
    mark = self.connection.events.mark()
    run = self.connection.send('java.run', {'suites': ['self', 'self-red', 'nosuch'], 'results': folder})
    # while it goes: the game's operations wait for it, the probe's own answer
    self.firstJavaResult(run, mark)
    with self.assertRaises(NotReady):
      self.request('screen.get')
    with self.assertRaises(NotReady):
      self.request('java.run', {'suites': ['self'], 'results': self.javaResults('never')})
    self.request('status')
    self.request('log.write', {'message': 'during the Java run'})
    value = run.result(JAVA_SECONDS)
    self.assertFalse(value['ok'])
    self.assertEqual(os.path.join(folder, 'report.txt'), value['report'])
    counts = dict(value['counts'])
    ran = counts.pop('ran')
    self.assertEqual(RED_COUNTS, counts)
    # the report as the Java path's own check wants it, run as ./unittas.sh runs it
    checked = subprocess.run([sys.executable, '-I', os.path.join(ROOT, 'bin', 'self_red_check.py'), value['report']],
                             capture_output=True, text=True)
    self.assertEqual(0, checked.returncode, checked.stdout + checked.stderr)
    # a java.result for each of its lines, in its order
    with open(value['report'], encoding='utf-8') as report:
      text = report.read()
    lines = [(found.group(1), found.group(2)) for found in map(RESULT.match, text.split('\n-----')[0].split('\n'))
             if found]
    events = [event for event in self.connection.events.since(mark) if isJavaResult(event)]
    self.assertEqual(lines, [(event['test'], WORDS[event['outcome']]) for event in events])
    self.assertEqual(ran, sum(1 for _, outcome in lines if outcome != 'problem'))

  def test_10_after_the_java_run(self) -> None:
    self.assertEqual('menu', self.request('status')['state'])
    self.assertTrue(self.request('screen.get')['class'].endswith('GuiMainMenu'), 'the game answers again')

  def test_11_a_cancelled_java_run(self) -> None:
    folder = self.javaResults('cancelled')
    mark = self.connection.events.mark()
    run = self.connection.send('java.run', {'suites': ['self'], 'results': folder})
    self.firstJavaResult(run, mark)
    self.assertTrue(self.request('cancel', {'id': run.id})['cancelled'])
    with self.assertRaises(Cancelled):
      run.result(300)
    with open(os.path.join(folder, 'report.txt'), encoding='utf-8') as report:
      self.assertIn('unitTAS.aborted', report.read())
    self.assertEqual('menu', self.request('status')['state'])

  def test_12_quit(self) -> None:
    self.assertEqual({}, self.request('quit', {'reason': 'test_12'}))
    self.assertTrue(self.game.ended(GONE_SECONDS))


if __name__ == '__main__':
  unittest.main()

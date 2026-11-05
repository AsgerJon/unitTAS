"""
The watch (unittas.watch, SPEC.md 9.3 step 8b), without a game: test_run's fake game, and a fake clock whose sleep
moves time on at once and runs what was planned for each moment (a decision written, a test ended).
- Always: watch.txt from the heartbeat (the tick event), a live picture only while the client ticks.
- A test's time limit: unwatched, the test is stopped (no result); watched, an alarm asks first.
- An alarm: its text and files, each decision, one for another alarm dropped, a malformed one asked again, no answer
  at the decision time exactly, cleared by itself, the reminders.
- A world that doesn't load, in a watched run: the alarm, a wait, and a give-up.
- In a GameTestCase, by the real clock: a test past its timeout_seconds is NO RESULT, and the next runs.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import unittest

import gamecases
from unittas.errors import LinkTimeout, NoResult
from unittas.run import Run
from unittas.watch import LOAD_SECONDS, Watch
from test_run import FakeRun


class FakeClock:
  """Time that moves only when slept through; what is planned for a moment runs as the sleep passes it."""

  def __init__(self, now: float) -> None:
    self.now = now
    self.plans = []

  def time(self) -> float:
    return self.now

  def at(self, when: float, action) -> None:
    self.plans.append((when, action))
    self.plans.sort(key=lambda plan: plan[0])

  def sleep(self, seconds: float) -> None:
    end = self.now + seconds
    while self.plans and self.plans[0][0] <= end:
      when, action = self.plans.pop(0)
      self.now = max(self.now, when)
      action()
    self.now = end


class FakePending:
  """A request still waiting, for the world's guard: done once 'answer' is called."""

  def __init__(self, requestId: int = 99) -> None:
    self.id = requestId
    self.done = False
    self.value = None

  def answer(self, value) -> None:
    self.value = value
    self.done = True

  def result(self, timeout=None):
    if not self.done:
      raise LinkTimeout('no answer yet')
    return self.value


class WatchCase(FakeRun, unittest.TestCase):

  def setUp(self) -> None:
    FakeRun.setUp(self)
    self.clock = FakeClock(1000.0)
    self.shots = []

    def screenshot(args, side):
      with open(args['file'], 'wb') as file:
        file.write(b'a picture')
      self.shots.append(os.path.basename(args['file']))
      return {'file': args['file']}

    self.handlers['screenshot'] = screenshot
    self.handlers['debug.threads'] = lambda args, side: {'text': '"Client thread" waiting on the server'}
    self.handlers['cancel'] = lambda args, side: {'cancelled': True}
    self.handlers['ticks.wait'] = lambda args, side: {'waited_ms': 50, 'from': 1, 'tick': 2}
    Run.current = self.run
    self.addCleanup(setattr, Run, 'current', None)

  def watch(self, watched: bool) -> Watch:
    return Watch(self.run, watched=watched, pictures=10, decide=300, clock=self.clock.time, sleep=self.clock.sleep)

  def beat(self, watch: Watch, clientAgo: int = 100, client: int = 500) -> None:
    watch.heard({'event': 'tick', 'client': client, 'server': 400, 'client_ago_ms': clientAgo, 'server_ago_ms': 50,
                 'screen': None, 'state': 'world', 'paused': False})

  def path(self, name: str) -> str:
    return os.path.join(self.results, name)

  def read(self, name: str) -> str:
    with open(self.path(name), encoding='utf-8') as file:
      return file.read()

  def decide(self, when: float, line: str) -> None:
    def write() -> None:
      with open(self.path('decision.txt'), 'w', encoding='utf-8') as file:
        file.write(line + '\n')
    self.clock.at(when, write)

  def startTest(self, limit: int = 60, name: str = 'ATests.test_a') -> None:
    self.run.begin()
    self.run.enterClass('ATests')
    self.run.beforeTest(name, limit)


class AlwaysTests(WatchCase):

  def test_watch_txt_from_the_heartbeat(self) -> None:
    watch = self.watch(False)
    self.run.total = 5
    self.beat(watch)
    watch.testBegan(3, 'ATests.test_c', 60)
    self.clock.now += 4
    self.beat(watch)
    watch.round()
    text = self.read('watch.txt')
    self.assertIn('run: test 3/5 ATests.test_c, 4 s in (its limit 60 s)', text)
    self.assertIn('client: ticking', text)
    self.assertIn('server: ticking', text)
    self.assertIn('alarm: none open', text)
    self.clock.now += 8
    watch.round()
    text = self.read('watch.txt')
    self.assertIn('client: last ticked 8 s ago', text)
    self.assertIn('probe: silent for 8 s', text)

  def test_pictures_only_while_the_client_ticks(self) -> None:
    watch = self.watch(False)
    self.beat(watch)
    self.clock.now += 10
    self.beat(watch)
    watch.round()
    self.assertEqual(['watch-new.png'], self.shots)
    self.assertTrue(os.path.isfile(self.path('screenshots/watch-live.png')))
    self.clock.now += 10
    self.beat(watch, clientAgo=5000)
    watch.round()
    self.assertEqual(1, len(self.shots), 'a picture of a client that is not ticking')
    self.assertIn("the client isn't ticking", self.read('watch.txt'))
    self.clock.now += 10
    self.beat(watch)
    watch.round()
    self.assertEqual(2, len(self.shots))
    self.assertTrue(os.path.isfile(self.path('screenshots/watch-previous.png')))


class TimeLimitTests(WatchCase):

  def test_unwatched_the_test_is_stopped(self) -> None:
    watch = self.watch(False)
    self.beat(watch)
    self.startTest(60)
    self.clock.now += 59
    watch.round()
    self.assertIsNone(self.run.testStopped)
    self.clock.now += 1
    watch.round()
    why = 'ran past its time limit (60 s): no verdict'
    self.assertEqual(why, self.run.testStopped)
    with self.assertRaises(NoResult) as raised:
      self.run.game.command('/say still here')
    self.assertEqual(why, raised.exception.why)
    self.assertIsNone(self.run.stopped, 'the run goes on: the game is ticking')

  def test_watched_an_alarm_waits_then_fails_the_test(self) -> None:
    watch = self.watch(True)
    self.beat(watch)
    self.startTest(60)
    seen = []
    # the pictures at 1060 and 1063, the alarm written then
    self.clock.at(1064, lambda: seen.append(self.read('alarm.txt')))
    self.decide(1066, '1 wait 30')
    self.clock.now = 1060
    self.beat(watch)
    watch.round()
    self.assertIsNone(self.run.testStopped)
    alarm = seen[0]
    for said in ('unitTAS alarm 1, ', 'what: the test has run past its time limit (60 s)',
                 'run: test 1 ATests.test_a, 63 s in (its limit 60 s)', 'alarm-1-a.png', 'alarm-1-b.png',
                 '1 wait <seconds>', '1 fail <why>', '1 abort <why>', 'No answer by ',
                 self.path('decision.txt')):
      self.assertIn(said, alarm)
    self.assertEqual(['alarm-1-a.png', 'alarm-1-b.png'], [shot for shot in self.shots if shot.startswith('alarm-')])
    self.assertFalse(os.path.exists(self.path('alarm.txt')), 'the alarm closed')
    self.assertIn('alarm 1 answered: wait 30 s', self.read('alarms.txt'))
    self.clock.now = 1095
    watch.round()
    self.assertNotIn('alarm 2', self.read('alarms.txt'), 'asked again before its wait was up')
    self.decide(1100, 'fail it loops forever')
    self.clock.now = 1096
    self.beat(watch)
    watch.round()
    self.assertEqual('stopped by the watcher (alarm 2): it loops forever', self.run.testStopped)
    self.assertIn('ALARM 2: the test has run past its time limit (60 s)', self.read('progress.txt'))

  def test_no_answer_at_the_decision_time_exactly(self) -> None:
    watch = self.watch(True)
    self.beat(watch)
    self.startTest(60)
    self.clock.now = 1061
    self.beat(watch)
    watch.round()
    # the pictures at 1061 and 1064: the alarm opened then, and 300 s later it had no answer
    self.assertEqual(1364.0, self.clock.now)
    self.assertEqual('ran past its time limit (60 s), and alarm 1 had no answer: no verdict', self.run.testStopped)
    self.assertEqual(4, self.read('progress.txt').count('ALARM 1 still open'), 'a reminder each minute')
    self.assertIn('alarm 1: no answer in 300 s', self.read('alarms.txt'))

  def test_another_alarms_decision_and_a_malformed_one(self) -> None:
    watch = self.watch(True)
    self.beat(watch)
    self.startTest(60)
    seen = []
    self.decide(1065, '7 wait 10')
    self.decide(1070, 'maybe later')
    self.clock.at(1075, lambda: seen.append(self.read('alarm.txt')))
    self.decide(1080, 'abort the world is gone')
    self.clock.now = 1061
    self.beat(watch)
    watch.round()
    log = self.read('alarms.txt')
    self.assertIn('a decision for alarm 7 came while alarm 1 is open: dropped', log)
    self.assertIn("decision.txt said 'maybe later', which is none of wait, fail, abort", log)
    self.assertIn("decision.txt said 'maybe later': that's none of the three; write it again.", seen[0])
    why = 'the watcher aborted the run (alarm 1): the world is gone'
    self.assertEqual(why, self.run.stopped)
    self.assertEqual(why, self.run.testStopped)

  def test_cleared_by_itself(self) -> None:
    watch = self.watch(True)
    self.beat(watch)
    self.startTest(60)
    self.clock.at(1070, watch.testEnded)
    self.clock.now = 1061
    watch.round()
    self.assertIsNone(self.run.testStopped)
    self.assertIn('alarm 1 cleared by itself', self.read('alarms.txt'))
    self.assertFalse(os.path.exists(self.path('alarm.txt')))


class LoadingTests(WatchCase):

  def test_a_watched_run_lets_the_watch_judge_the_world(self) -> None:
    self.watch(True)
    self.run.begin()
    for op in ('world.create', 'world.open'):
      args = [request['args'] for request in self.asked if request['op'] == op][0]
      self.assertEqual(3600, args.get('max_seconds'), op)

  def test_the_world_waited_for_then_given_up(self) -> None:
    watch = self.watch(True)
    pending = FakePending()
    self.decide(1000 + LOAD_SECONDS + 10, '1 wait 30')
    self.clock.at(1000 + LOAD_SECONDS + 35, lambda: pending.answer({'folder': 'unittas'}))
    self.assertEqual({'folder': 'unittas'}, watch.guardLoad(pending, 'the test world'))
    self.assertIn('alarm 1 answered: wait 30 s', self.read('alarms.txt'))
    self.assertIn('waiting on the server', self.read('alarm-1-threads.txt'), "the threads, as the client doesn't tick")
    stuck = FakePending(100)
    self.decide(self.clock.now + LOAD_SECONDS + 5, 'fail it is stuck')
    with self.assertRaises(NoResult) as raised:
      watch.guardLoad(stuck, 'the test world')
    self.assertEqual('the watcher gave up on the test world (alarm 2): it is stuck', raised.exception.why)
    self.assertIn({'id': 100}, [request.get('args') for request in self.asked if request['op'] == 'cancel'])


class GameTestCaseTimeLimitTests(WatchCase):
  """By the real clock: a GameTestCase past its timeout_seconds."""

  def test_past_its_time_no_result_and_the_next_runs(self) -> None:
    self.run.begin()
    watch = Watch(self.run, watched=False, pictures=0)
    watch.start()
    try:
      suite = unittest.TestLoader().loadTestsFromTestCase(gamecases.SlowTests)
      result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    finally:
      watch.stop()
    self.assertEqual(1, len(result.errors))
    self.assertIn('NO TEST RESULT', result.errors[0][1])
    with open(self.run.finish(), encoding='utf-8') as file:
      text = file.read()
    self.assertIn('SlowTests.test_a_loops ... NO RESULT', text)
    self.assertIn('    ran past its time limit (1 s): no verdict', text)
    self.assertIn('SlowTests.test_b_runs ... ok', text)


if __name__ == '__main__':
  unittest.main()

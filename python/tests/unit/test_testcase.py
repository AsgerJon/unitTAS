"""
GameTestCase (unittas.testcase), without a game: plain unittest classes run by unittest's own runner against a fake
probe. Each class gets its world (fresh, or shared with shared_world), each test a reset before it whatever its own
setUp does, a failure or an error a picture before the next reset; the Run writes their lines into the report.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import unittest

import gamecases
from fakeprobe import FakeError
from unittas.run import Run
from test_run import FakeRun


class GameTestCaseTests(FakeRun, unittest.TestCase):
  """The Run of test_run's fake game, with GameTestCases run on it."""

  def setUp(self) -> None:
    FakeRun.setUp(self)
    fake = self.fake

    def say(args, side):
      fake.event('chat', plain='Given', formatted='Given', json='{}')
      return {'result': 1, 'lines': ['Given'], 'errors': []}

    self.handlers['command.run'] = say
    Run.current = self.run
    self.addCleanup(setattr, Run, 'current', None)

  def runClasses(self, *classes) -> unittest.TestResult:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite(loader.loadTestsFromTestCase(each) for each in classes)
    return unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)

  def report(self) -> list:
    with open(self.run.finish(), encoding='utf-8') as file:
      text = file.read()
    return [line for line in text.split('\n')[2:text.split('\n').index('-' * 70)]]

  def test_classes_tests_and_their_report(self) -> None:
    self.run.begin()
    result = self.runClasses(gamecases.ATests, gamecases.BTests, gamecases.CTests)
    self.assertEqual((1, 0, 1, 1), (len(result.failures), len(result.errors), len(result.skipped),
                                    len(result.expectedFailures)))
    lines = self.report()
    self.assertEqual('world 1: the run\'s first, for ATests', lines[0])
    self.assertRegex(lines[1], r'^ATests\.test_1_passes \.\.\. ok \(\d+\.\d s\)$')
    self.assertRegex(lines[2], r'^ATests\.test_2_fails \.\.\. FAIL \(\d+\.\d s\)$')
    self.assertIn('AssertionError: 1 != 2 : on purpose', lines[3])
    where = [line for line in lines if line.strip().startswith('at ')]
    self.assertTrue(where and 'gamecases.py' in where[0] and 'test_2_fails' in where[0], where)
    self.assertIn('    screenshot: screenshots/ATests.test_2_fails.png', lines)
    self.assertTrue(any(line.startswith('world 2: fresh for BTests') for line in lines), lines)
    self.assertIn('    not today', lines)
    self.assertIn('world 2, shared: CTests runs in it as BTests left it', lines)
    self.assertTrue(any(line.startswith('CTests.test_parked ... expected failure') for line in lines), lines)
    self.assertEqual(['hooks beforeRun', 'world.create', 'world.prepare', 'world.close', 'world.open',
                      'hooks setUpWorld', 'reset', 'reset', 'refs.clear', 'reset', 'refs.clear',
                      'hooks tearDownWorld', 'world.close', 'world.open', 'hooks setUpWorld', 'reset', 'reset',
                      'refs.clear', 'reset', 'reset', 'refs.clear', 'hooks tearDownWorld', 'hooks afterRun', 'quit'],
                     self.lifecycle())
    shots = [request['args']['file'] for request in self.asked if request['op'] == 'screenshot']
    self.assertEqual([os.path.join(self.results, 'screenshots', 'ATests.test_2_fails.png')], shots)

  def test_a_test_reads_its_own_chat(self) -> None:
    self.run.begin()
    self.fake.event('chat', plain='before the test', formatted='x', json='{}')
    result = self.runClasses(gamecases.ChatTests)
    self.assertTrue(result.wasSuccessful(), result.failures + result.errors)

  def test_a_reset_that_fails_is_the_test_s_error(self) -> None:
    self.run.begin()

    def broken(args, side):
      raise FakeError('GameError', 'a mod\'s resetPlayer threw', plugin='com.example.Plugin')

    self.handlers['batch'] = broken
    result = self.runClasses(gamecases.BTests)
    self.assertEqual(1, len(result.errors), result.errors)
    self.assertIn('resetPlayer', result.errors[0][1])

  def test_a_stalled_game_is_no_result_and_the_run_stops(self) -> None:
    self.run.begin()
    said = self.handlers['command.run']

    def stalled(args, side):
      if args['command'] == '/stall':
        raise FakeError('Stalled', 'the client didn\'t tick for 15 s', side='client', since_tick_ms=15000)
      return said(args, side)

    self.handlers['command.run'] = stalled

    def stillStuck(args, side):
      raise FakeError('Stalled', 'the client didn\'t tick for 15 s', side='client', since_tick_ms=15000)

    self.handlers['ticks.wait'] = stillStuck
    result = self.runClasses(gamecases.StallTests, gamecases.ATests)
    self.assertEqual([], result.failures, 'no test was failed: none could be run to a verdict')
    self.assertEqual(4, len(result.errors), result.errors)
    for _, text in result.errors:
      self.assertIn('NO TEST RESULT', text)
    lines = self.report()
    self.assertIn('the game stopped ticking', [line for line in lines if 'test_a_meets_a_stall' in line or
                                               line.startswith('    ')][1])
    outcomes = {line.split(' ... ')[0]: line.split(' ... ')[1].split(' (')[0] for line in lines if ' ... ' in line}
    self.assertEqual({'StallTests.test_a_meets_a_stall': 'NO RESULT', 'StallTests.test_b_never_runs': 'NO RESULT',
                      'ATests.test_1_passes': 'NO RESULT', 'ATests.test_2_fails': 'NO RESULT'}, outcomes)
    with open(os.path.join(self.results, 'report.txt'), encoding='utf-8') as file:
      self.assertTrue(file.read().split('\n')[1].startswith('NO TEST RESULT could be obtained for 4 tests'))

  def test_a_game_that_ticks_again_goes_on(self) -> None:
    self.run.begin()
    said = self.handlers['command.run']

    def stalled(args, side):
      if args['command'] == '/stall':
        raise FakeError('Stalled', 'the client didn\'t tick for 15 s', side='client', since_tick_ms=15000)
      return said(args, side)

    self.handlers['command.run'] = stalled
    self.handlers['ticks.wait'] = lambda args, side: {'waited_ms': 50, 'from': 10, 'tick': 11}
    self.runClasses(gamecases.StallTests, gamecases.ChatTests)
    outcomes = {line.split(' ... ')[0]: line.split(' ... ')[1].split(' (')[0] for line in self.report() if ' ... ' in line}
    self.assertEqual({'StallTests.test_a_meets_a_stall': 'NO RESULT', 'StallTests.test_b_never_runs': 'FAIL',
                      'ChatTests.test_its_own_chat': 'ok'}, outcomes,
                     'after the stall the client ticked again: the run went on, and its results are real')
    with open(os.path.join(self.results, 'report.txt'), encoding='utf-8') as file:
      self.assertTrue(file.read().split('\n')[1].startswith('NO TEST RESULT could be obtained for 1 test'))

  def test_a_mod_s_error_is_a_result(self) -> None:
    self.run.begin()
    said = self.handlers['command.run']

    def throws(args, side):
      if args['command'] == '/mod-throws':
        raise FakeError('GameError', 'com.example.Mod threw: java.lang.IllegalStateException')
      return said(args, side)

    self.handlers['command.run'] = throws
    result = self.runClasses(gamecases.ModErrorTests)
    self.assertEqual(1, len(result.errors))
    self.assertNotIn('NO TEST RESULT', result.errors[0][1])
    outcomes = [line.split(' ... ')[1].split(' (')[0] for line in self.report() if ' ... ' in line]
    self.assertEqual(['ERROR', 'ok'], outcomes)

  def test_a_crash_is_no_result_naming_it(self) -> None:
    fake = self.fake

    def crash(args, side):
      # the game's crash: said first (the crash event), then the quit, then the connection gone
      fake.event('crash', report='/game/crash-reports/crash-x-client.txt', summary='Boom: java.lang.Throwable: x')
      fake.event('quit', reason='crash')
      fake.close()
      return {}

    self.handlers['command.run'] = crash
    self.runClasses(gamecases.CrashTests)
    with open(self.run.finish(), encoding='utf-8') as file:
      lines = file.read().split('\n')
    said = 'the game crashed: Boom: java.lang.Throwable: x (its crash report: /game/crash-reports/crash-x-client.txt)'
    self.assertEqual('NO TEST RESULT could be obtained for 2 tests: ' + said, lines[1])
    outcomes = [line.split(' ... ')[1].split(' (')[0] for line in lines if ' ... ' in line]
    self.assertEqual(['NO RESULT', 'NO RESULT'], outcomes)
    self.assertIn('    not run: no test result could be obtained after ' + said, lines)

  def test_without_a_run(self) -> None:
    Run.current = None
    result = self.runClasses(gamecases.BTests)
    self.assertEqual(1, len(result.errors))
    self.assertIn('no unitTAS run', result.errors[0][1])


if __name__ == '__main__':
  unittest.main()

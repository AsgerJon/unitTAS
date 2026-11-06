"""
The run's lifecycle (unittas.run.Run), without a game: a fake probe answers, and a folder stands for the game's. In
PROTOCOL.md section 13's order: beforeRun; the world made, prepared, closed, kept aside as made, opened; each class
its world (the kept one put back unless shared_world) with setUpWorld and a reset before setUpClass; each test a reset
before it and refs.clear after; at the end tearDownWorld, afterRun and quit. The report in the Java report's shape.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import re
import shutil
import tempfile
import unittest

from fakeprobe import FakeError, FakeProbe, inThread
from unittas.api import Game
from unittas.link import Listener
from unittas.run import Run
from unittas.wire import Role
from test_values import PLAYER


class FakeRun:
  """A Run on a fake game for a test case: 'run', 'fake', 'asked' (the requests), 'handlers' (changeable)."""

  def setUp(self) -> None:
    self.scratch = tempfile.mkdtemp(prefix='unittas-run-')
    self.addCleanup(shutil.rmtree, self.scratch, True)
    self.gameDir = os.path.join(self.scratch, 'game')
    self.results = os.path.join(self.scratch, 'results')
    os.makedirs(self.gameDir)
    self.listener = Listener()
    self.addCleanup(self.listener.close)
    expected = self.listener.prepare(self.gameDir, 'alice', Role.CLIENT)
    self.fake = FakeProbe(expected.startFile)
    thread, box = inThread(self.fake.connect)
    connection = self.listener.accept(timeout=10)
    thread.join(10)
    self.addCleanup(connection.close)
    self.addCleanup(self.fake.close)
    world = os.path.join(self.gameDir, 'saves', 'unittas')

    def create(args, side):
      if os.path.exists(world):
        raise FakeError('Exists', 'saves/unittas is there already: world.create makes a new world', what='unittas')
      os.makedirs(os.path.join(world, 'region'))
      with open(os.path.join(world, 'level.dat'), 'w') as file:
        file.write('as made')
      return {'folder': 'unittas', 'load_ms': 10, 'spawn': [0, 4, 0]}

    batchAnswer = [{'ok': True, 'value': {'respawned': False}}, {'ok': True, 'value': {}},
                   {'ok': True, 'value': {'plugins': []}}]
    self.handlers = {
      'hooks.run': lambda args, side: {'plugins': []},
      'world.create': create,
      'world.prepare': lambda args, side: {},
      'world.close': lambda args, side: {'close_ms': 5},
      'world.open': lambda args, side: {'folder': 'unittas', 'name': 'unitTAS', 'load_ms': 5},
      'client.reset': lambda args, side: {},
      'player.get': lambda args, side: dict(PLAYER, pos=[0.5, 4.0, 0.5]),
      'batch': lambda args, side: batchAnswer,
      'wait.until': lambda args, side: {'held': True, 'tick': 5, 'checks': 1, 'value': dict(PLAYER)},
      'refs.clear': lambda args, side: {},
      'screenshot': lambda args, side: {'file': args['file']},
      'quit': lambda args, side: {},
    }
    self.asked = self.fake.serve(self.handlers)
    self.world = world
    self.run = Run(Game(connection), self.gameDir, self.results)

  def lifecycle(self) -> list:
    """The requests that make the lifecycle, a reset counted once (its batch)."""
    out = []
    for request in self.asked:
      op = request['op']
      if op == 'hooks.run':
        out.append('hooks ' + request['args']['hook'])
      elif op == 'batch':
        out.append('reset')
      elif op.startswith('world.') or op in ('refs.clear', 'quit'):
        out.append(op)
    return out


class RunTests(FakeRun, unittest.TestCase):

  def test_the_order_for_a_first_a_fresh_and_a_shared_class(self) -> None:
    run = self.run
    run.begin()
    run.enterClass('ATests', shared=False)
    for name in ('ATests.test_1', 'ATests.test_2'):
      mark = run.beforeTest()
      run.afterTest(name, 'ok', 0.1, '', mark)
    # what class A left in its world, as a game would leave it
    with open(os.path.join(self.world, 'region', 'r.0.0.mca'), 'w') as file:
      file.write('A was here')
    run.enterClass('BTests', shared=False)
    self.assertFalse(os.path.exists(os.path.join(self.world, 'region', 'r.0.0.mca')), 'the kept world put back exactly')
    with open(os.path.join(self.world, 'level.dat')) as file:
      self.assertEqual('as made', file.read())
    run.afterTest('BTests.test_1', 'ok', 0.1, '', run.beforeTest())
    run.enterClass('CTests', shared=True)
    run.afterTest('CTests.test_1', 'ok', 0.1, '', run.beforeTest())
    run.finish()
    self.assertEqual([
      'hooks beforeRun', 'world.create', 'world.prepare', 'world.close', 'world.open',
      'hooks setUpWorld', 'reset', 'reset', 'refs.clear', 'reset', 'refs.clear',
      'hooks tearDownWorld', 'world.close', 'world.open', 'hooks setUpWorld', 'reset', 'reset', 'refs.clear',
      'reset', 'reset', 'refs.clear',
      'hooks tearDownWorld', 'hooks afterRun', 'quit',
    ], self.lifecycle())

  def test_the_report(self) -> None:
    run = self.run
    run.begin()
    run.enterClass('ATests', shared=False)
    run.afterTest('ATests.test_1', 'ok', 0.4, '', run.beforeTest())
    mark = run.beforeTest()
    self.fake.event('chat', plain='Given [Red Wool] * 1', formatted='Given', json='{}')
    picture = run.picture('ATests.test_2')
    run.afterTest('ATests.test_2', 'FAIL', 1.25, 'AssertionError: 1 != 2', mark, screenshot=picture)
    run.enterClass('BTests', shared=False)
    run.afterTest('BTests.test_1', 'skipped', 0.0, 'not today', run.beforeTest())
    run.enterClass('CTests', shared=True)
    run.afterTest('CTests.test_1', 'expected failure', 0.2, 'AssertionError: parked', run.beforeTest())
    report = run.finish()
    self.assertEqual(os.path.join(self.results, 'report.txt'), report)
    with open(report, encoding='utf-8') as file:
      lines = file.read().split('\n')
    self.assertTrue(lines[0].startswith('unitTAS report, '), lines[0])
    body = lines[2:lines.index('-' * 70)]
    self.assertEqual('world 1: the run\'s first, for ATests', body[0])
    self.assertEqual('ATests.test_1 ... ok (0.4 s)', body[1])
    self.assertEqual('ATests.test_2 ... FAIL (1.2 s)', body[2])
    self.assertEqual('    AssertionError: 1 != 2', body[3])
    self.assertEqual('    screenshot: screenshots/ATests.test_2.png', body[4])
    self.assertEqual(['    chat during the test:', '      | Given [Red Wool] * 1'], body[5:7])
    self.assertRegex(body[7], r'^world 2: fresh for BTests \(the kept world put back, opened in \d+\.\d s\)$')
    self.assertEqual(['BTests.test_1 ... skipped (0.0 s)', '    not today'], body[8:10])
    self.assertEqual('world 2, shared: CTests runs in it as BTests left it', body[10])
    self.assertEqual(['CTests.test_1 ... expected failure (0.2 s)', '    AssertionError: parked'], body[11:13])
    tail = [line for line in lines[lines.index('-' * 70) + 1:] if line]
    self.assertTrue(re.match(r'^Ran 4 tests in \d+\.\d s$', tail[0]), tail)
    self.assertEqual('FAILED (failures=1, skipped=1, expected failures=1)', tail[1])
    shot = [request for request in self.asked if request['op'] == 'screenshot'][0]
    self.assertEqual(os.path.join(self.results, 'screenshots', 'ATests.test_2.png'), shot['args']['file'])

  def test_an_old_test_world_goes_first_and_the_kept_copy_last(self) -> None:
    os.makedirs(os.path.join(self.world, 'region'))
    with open(os.path.join(self.world, 'level.dat'), 'w') as file:
      file.write('an earlier run\'s')
    other = os.path.join(self.gameDir, 'saves', 'someone-elses')
    os.makedirs(other)
    self.run.begin()
    with open(os.path.join(self.world, 'level.dat')) as file:
      self.assertEqual('as made', file.read())
    self.assertTrue(os.path.isdir(self.run.keptFolder()))
    self.run.finish()
    self.assertFalse(os.path.exists(self.run.keptFolder()), 'the kept copy is the run\'s, and goes with it')
    self.assertTrue(os.path.isdir(other), 'only the test world\'s folder')

  def test_no_result_is_said_first_and_counted(self) -> None:
    run = self.run
    run.begin()
    run.enterClass('ATests', shared=False)
    run.afterTest('ATests.test_1', 'ok', 0.1, '', run.beforeTest())
    run.noResult('ATests.test_2', 'the game stopped ticking: the client didn\'t tick for 15 s', 15.2)
    run.noResult('ATests.test_3', 'not run: no test result could be obtained after ATests.test_2', 0.0)
    with open(run.finish(), encoding='utf-8') as file:
      lines = file.read().split('\n')
    self.assertEqual('NO TEST RESULT could be obtained for 2 tests: the game stopped ticking: the client didn\'t tick '
                     'for 15 s', lines[1])
    self.assertIn('ATests.test_2 ... NO RESULT (15.2 s)', lines)
    self.assertIn('ATests.test_3 ... NO RESULT (0.0 s)', lines)
    self.assertEqual('FAILED (no results=2)', [line for line in lines if line][-1])

  def test_all_ok(self) -> None:
    run = self.run
    run.begin()
    run.enterClass('ATests', shared=False)
    run.afterTest('ATests.test_1', 'ok', 0.1, '', run.beforeTest())
    with open(run.finish(), encoding='utf-8') as file:
      self.assertEqual('OK', [line for line in file.read().split('\n') if line][-1])


class OpeningGuardTests(FakeRun, unittest.TestCase):
  """The opening guard's Python side: each world opened with the run's pictures folder; its warnings said."""

  def test_the_pictures_folder_and_a_dropped_login_said(self) -> None:
    from fakeprobe import Warned
    opened = self.handlers['world.open']

    def dropped(args, side):
      return Warned(opened(args, side), 'the integrated server dropped the client\'s own connection before it joined'
                                        ' (1.7.10\'s login race): left and opened again')

    self.handlers['world.open'] = dropped
    self.run.begin()
    for op in ('world.create', 'world.open'):
      args = [request['args'] for request in self.asked if request['op'] == op][0]
      self.assertEqual(os.path.join(self.results, 'screenshots'), args['pictures'], op)
    with open(os.path.join(self.results, 'progress.txt'), encoding='utf-8') as file:
      self.assertIn("the test world: the integrated server dropped the client's own connection", file.read())

  def test_a_world_that_does_not_open_is_no_result_for_its_class(self) -> None:
    import io
    import gamecases
    from unittas.run import runSuite

    self.run.begin()
    # the run's first class has the run's first world: the classes after it are the ones whose world is opened again
    self.run.enterClass('FirstTests')
    opens = []

    def refused(args, side):
      opens.append(args)
      raise FakeError('Disconnected', 'dropped, and again after it was opened once more', reason='dropped')

    self.handlers['world.open'] = refused
    runSuite(self.run, unittest.TestLoader().loadTestsFromNames(['gamecases.ATests', 'gamecases.BTests']),
             stream=io.StringIO())
    with open(self.run.finish(), encoding='utf-8') as file:
      lines = file.read().split('\n')
    outcomes = [line.split(' ... ')[1].split(' (')[0] for line in lines if ' ... ' in line]
    self.assertEqual(['NO RESULT', 'NO RESULT', 'NO RESULT'], outcomes, '\n'.join(lines))
    self.assertIn("the test world didn't open", '\n'.join(lines))


if __name__ == '__main__':
  unittest.main()

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
      # as a probe has it: the save made in saves/<folder>, refused where one is there
      name = args.get('folder', 'unittas')
      folder = os.path.join(self.gameDir, 'saves', name)
      if os.path.exists(folder):
        raise FakeError('Exists', 'saves/%s is there already: world.create makes a new world' % name, what=name)
      os.makedirs(os.path.join(folder, 'region'))
      with open(os.path.join(folder, 'level.dat'), 'w') as file:
        file.write('as made')
      return {'folder': name, 'load_ms': 10, 'spawn': [0, 4, 0]}

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


class ClassWorldTests(FakeRun, unittest.TestCase):
  """
  A class that asks for a world of its own (world = {...}, world.create's own arguments): made fresh for it in a save
  folder of its own (unittas-class), so the run's kept flat world is never touched; the reset starts where the game put
  the player when it was made, not on the flat world's grass. The next class without one gets the flat world back.
  """

  def setUp(self) -> None:
    FakeRun.setUp(self)
    self.spawned = [12.5, 70.0, -3.5]
    flatPlayer = self.handlers['player.get']
    created = {'class': False}
    create = self.handlers['world.create']

    def creating(args, side):
      created['class'] = args['folder'] == 'unittas-class'
      return create(args, side)

    def player(args, side):
      return dict(PLAYER, pos=self.spawned) if created['class'] else flatPlayer(args, side)

    def opening(args, side):
      created['class'] = False
      return {'folder': args['folder'], 'name': 'unitTAS', 'load_ms': 5}

    self.handlers['world.create'] = creating
    self.handlers['player.get'] = player
    self.handlers['world.open'] = opening

  def resetsAt(self) -> list:
    """Where each reset put the player, in order: player.reset's 'at' in each batch."""
    out = []
    for request in self.asked:
      if request['op'] == 'batch':
        for op in request['args']['ops']:
          if op['op'] == 'player.reset':
            out.append(tuple(op['args']['at']))
    return out

  def test_made_fresh_for_the_class_with_its_arguments(self) -> None:
    self.run.begin()
    self.run.enterClass('CaveTests', world={'type': 'default', 'seed': 1234})
    creates = [request['args'] for request in self.asked if request['op'] == 'world.create']
    self.assertEqual({'folder': 'unittas-class', 'type': 'default', 'seed': 1234},
                     {key: creates[-1][key] for key in ('folder', 'type', 'seed')})
    self.assertFalse({'type', 'seed', 'generator'} & set(creates[0]), "the run's own world is the probe's flat, as ever")
    self.assertEqual('unittas', creates[0]['folder'])
    self.assertIn('world 2: fresh for CaveTests, made as it asks (type default, seed 1234', self.run.worldNote)
    hooks = [request['args']['hook'] for request in self.asked if request['op'] == 'hooks.run']
    self.assertEqual('setUpWorld', hooks[-1], 'its setUpWorld, as any fresh world has')
    ops = [request['op'] for request in self.asked]
    afterCreate = ops[len(ops) - 1 - ops[::-1].index('world.create'):]
    self.assertIn('world.prepare', afterCreate, "prepared as the run's own world is")

  def test_the_reset_starts_where_the_game_put_the_player(self) -> None:
    self.run.begin()
    self.run.enterClass('CaveTests', world={'type': 'default'})
    self.run.beforeTest()
    self.assertEqual([tuple(self.spawned)] * 2, self.resetsAt()[-2:], "the class's own start, at entry and per test")

  def test_the_next_class_without_one_gets_the_flat_world_back(self) -> None:
    self.run.begin()
    self.run.enterClass('CaveTests', world={'type': 'default'})
    self.run.enterClass('FlatTests')
    opens = [request['args']['folder'] for request in self.asked if request['op'] == 'world.open']
    self.assertEqual('unittas', opens[-1], 'the kept flat world put back and opened')
    self.assertEqual((0.5, 4.0, 0.5), self.resetsAt()[-1], "the flat world's start again")
    self.assertTrue(os.path.isdir(os.path.join(self.gameDir, 'saves', 'unittas')))

  def test_shared_with_the_same_world_runs_on_in_it(self) -> None:
    self.run.begin()
    self.run.enterClass('CaveTests', world={'type': 'default', 'seed': 5})
    made = [request for request in self.asked if request['op'] == 'world.create']
    self.run.enterClass('MoreCaveTests', shared=True, world={'type': 'default', 'seed': 5})
    self.assertEqual(len(made), len([request for request in self.asked if request['op'] == 'world.create']))
    self.assertIn('shared: MoreCaveTests runs in it as CaveTests left it', self.run.worldNote)
    self.run.enterClass('OtherCaveTests', shared=True, world={'type': 'default', 'seed': 6})
    self.assertIn('fresh for OtherCaveTests', self.run.worldNote, 'shared only with the same world')

  def test_an_earlier_class_world_goes_first(self) -> None:
    os.makedirs(os.path.join(self.gameDir, 'saves', 'unittas-class', 'region'))
    with open(os.path.join(self.gameDir, 'saves', 'unittas-class', 'old.txt'), 'w') as file:
      file.write('an earlier run')
    self.run.begin()
    self.run.enterClass('CaveTests', world={'type': 'default'})
    self.assertFalse(os.path.exists(os.path.join(self.gameDir, 'saves', 'unittas-class', 'old.txt')))

  def test_a_world_it_can_t_ask_for_is_refused(self) -> None:
    self.run.begin()
    for bad in ({'folder': 'mine'}, {'colour': 'blue'}, ['default'], {'seed': 'many'}):
      with self.subTest(bad=bad):
        with self.assertRaises(TypeError):
          self.run.enterClass('BadTests', world=bad)


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

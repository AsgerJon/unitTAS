"""
The 'unittas' command (unittas.cli, SPEC.md 9.3 step 8a), without a game: a fake launched game over the fake probe
stands for the spec's.
- run: the spec found (--instance, UNITTAS_INSTANCE, unittas.toml); the tests by unittest's names or discovered; loaded
  before the game starts; the report written and shown, and the exit code by it; a game that can't start makes every
  test NO RESULT; Ctrl+C ends the run properly.
- launch: the game until it goes, the test world with --world; a headless display refused.
- compare: bin/compare_reports.py's, moved in.
- Plain unittest: the first GameTestCase starts a run from the spec, ended at exit.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import shutil
import signal
import sys
import tempfile
import textwrap
import threading
import time
import unittest

from fakegame import Factory
from unittas import cli, session
from unittas.errors import LinkTimeout, NoResult
from unittas.run import Run

SPEC = 'minecraft = "1.7.10"\nloader = { forge = "10.13.4.1614" }\nclient = "real"\n'
SUITES = {
  'clisuite_ok': '''
    from unittas.testcase import GameTestCase

    class AOkTests(GameTestCase):
      def test_a(self):
        pass

      def test_b(self):
        pass
    ''',
  'clisuite_fail': '''
    from unittas.testcase import GameTestCase

    class AFailTests(GameTestCase):
      def test_fails(self):
        self.fail('on purpose')
    ''',
  'clisuite_stop': '''
    from unittas.testcase import GameTestCase

    class AStopTests(GameTestCase):
      def test_a_runs(self):
        pass

      def test_b_is_stopped(self):
        raise KeyboardInterrupt()

      def test_c_never_runs(self):
        pass
    ''',
}
SUITES['clisuite_unbegun'] = '''
    from unittas.testcase import GameTestCase

    class AFixtureTests(GameTestCase):
      @classmethod
      def setUpClass(cls):
        super().setUpClass()
        cls.game.setBlock((40, 4, 40), 'minecraft:gold_block')

      def test_a(self):
        pass

      def test_b(self):
        pass

    class BSetUpFailsTests(GameTestCase):
      @classmethod
      def setUpClass(cls):
        super().setUpClass()
        raise RuntimeError('setUpClass fails on purpose')

      def test_never_runs(self):
        pass

    class COkTests(GameTestCase):
      def test_c(self):
        pass
    '''
DISCOVERED = '''
  from unittas.testcase import GameTestCase

  class DiscoveredTests(GameTestCase):
    def test_found(self):
      pass
  '''


class CliCase(unittest.TestCase):
  """A scratch folder with a spec and the suites in it, on the path; a fake game for each run."""

  @classmethod
  def setUpClass(cls) -> None:
    cls.suites = tempfile.mkdtemp(prefix='unittas-cli-suites-')
    for name, body in SUITES.items():
      with open(os.path.join(cls.suites, name + '.py'), 'w', encoding='utf-8') as file:
        file.write(textwrap.dedent(body))
    sys.path.insert(0, cls.suites)

  @classmethod
  def tearDownClass(cls) -> None:
    while cls.suites in sys.path:
      sys.path.remove(cls.suites)
    shutil.rmtree(cls.suites, True)

  def setUp(self) -> None:
    self.scratch = tempfile.mkdtemp(prefix='unittas-cli-')
    self.addCleanup(shutil.rmtree, self.scratch, True)
    self.spec = self.writeSpec('unittas.toml', SPEC)
    self.results = os.path.join(self.scratch, 'results')
    self.factory = Factory(os.path.join(self.scratch, 'game'))
    for name in SUITES:
      sys.modules.pop(name, None)
    self.addCleanup(lambda: [sys.modules.pop(name, None) for name in list(SUITES) + ['test_discovered']])
    self.addCleanup(setattr, Run, 'current', None)

  def writeSpec(self, name: str, body: str) -> str:
    path = os.path.join(self.scratch, name)
    with open(path, 'w', encoding='utf-8') as file:
      file.write(body)
    return path

  def main(self, *argv: str, environ: dict = None, cwd: str = None, factory: Factory = None) -> tuple:
    """The command's exit code and what it printed."""
    out = io.StringIO()
    code = cli.main(list(argv), out=out, environ=environ or {}, cwd=cwd or self.suites,
                    gameFor=factory or self.factory)
    return code, out.getvalue()

  def report(self, folder: str = None) -> list:
    with open(os.path.join(folder or self.results, 'report.txt'), encoding='utf-8') as file:
      return file.read().split('\n')


class UsageTests(CliCase):

  def test_no_command_and_unknown_ones_are_usage_mistakes(self) -> None:
    for argv in ((), ('nonsense',), ('run', '--instance'), ('compare', 'only-one'), ('launch', 'extra')):
      code, said = self.main(*argv)
      self.assertEqual(2, code, argv)
      self.assertIn('unittas run', said, argv)

  def test_the_spec_from_its_three_places_in_order(self) -> None:
    other = self.writeSpec('other.toml', SPEC)
    third = self.writeSpec('third.toml', SPEC)
    environ = {'UNITTAS_INSTANCE': third}
    self.assertEqual(other, session.findSpec(other, environ, self.scratch))
    self.assertEqual(third, session.findSpec(None, environ, self.scratch))
    self.assertEqual(self.spec, session.findSpec(None, {}, self.scratch))

  def test_no_spec_names_all_three_places(self) -> None:
    empty = os.path.join(self.scratch, 'empty')
    os.makedirs(empty)
    with self.assertRaises(session.UsageError) as raised:
      session.findSpec(None, {}, empty)
    for place in ('--instance', 'UNITTAS_INSTANCE', 'unittas.toml'):
      self.assertIn(place, str(raised.exception))
    with self.assertRaises(session.UsageError) as raised:
      session.findSpec(os.path.join(empty, 'gone.toml'), {}, empty)
    self.assertIn('gone.toml', str(raised.exception))
    code, said = self.main('run', 'clisuite_ok', cwd=empty)
    self.assertEqual(2, code)
    self.assertIn('UNITTAS_INSTANCE', said)

  def test_a_spec_mistake_is_a_usage_mistake(self) -> None:
    broken = self.writeSpec('broken.toml', SPEC.replace('"real"', '"wishful"'))
    code, said = self.main('run', 'clisuite_ok', '--instance', broken)
    self.assertEqual(2, code)
    self.assertIn('broken.toml', said)
    self.assertEqual([], self.factory.calls, 'a spec that is wrong costs no launch')

  def test_the_results_folder_beside_the_spec_and_latest(self) -> None:
    from unittas.spec import InstanceSpec
    spec = InstanceSpec.read(self.spec)
    folder = session.resultsFolder(spec, None, {'UNITTAS_STAMP': '2026-11-05_20-00-00'})
    self.assertEqual(os.path.join(self.scratch, 'unittas-results', '2026-11-05_20-00-00'), folder)
    self.assertTrue(os.path.isdir(folder))
    self.assertEqual('2026-11-05_20-00-00', os.readlink(os.path.join(self.scratch, 'unittas-results', 'latest')))
    self.assertEqual(os.path.abspath('given'), session.resultsFolder(spec, 'given', {}))


class RunTests(CliCase):

  def test_a_run_that_passes(self) -> None:
    code, said = self.main('run', 'clisuite_ok', '--instance', self.spec, '--results', self.results)
    self.assertEqual(0, code, said)
    lines = self.report()
    self.assertIn('AOkTests.test_a ... ok', '\n'.join(lines))
    self.assertEqual('OK', [line for line in lines if line][-1])
    self.assertIn('AOkTests.test_b ... ok', said, 'each test\'s line shown as it ends')
    # numbered as the Java runner's progress has them: 'test N/M Class.method ... outcome'
    self.assertIn('] test 1/2 AOkTests.test_a ... ok\n', said)
    self.assertIn('] test 2/2 AOkTests.test_b ... ok\n', said)
    with open(os.path.join(self.results, 'progress.txt'), encoding='utf-8') as file:
      progress = file.read().split('\n')
    self.assertIn('test 2/2 AOkTests.test_b ... ok', progress)
    self.assertIn(os.path.join(self.results, 'report.txt'), said)
    self.assertTrue(said.rstrip().endswith('OK'), said)
    self.assertEqual(1, self.factory.game.stops)
    self.assertEqual('quit', self.factory.game.ops()[-1])
    # the opening guard: a picture of the game as it came up, at its title screen
    shots = [request['args']['file'] for request in self.factory.game.asked if request['op'] == 'screenshot']
    self.assertEqual(os.path.join(self.results, 'screenshots', 'opened.png'), shots[0])

  def test_a_run_that_fails_exits_1(self) -> None:
    code, said = self.main('run', 'clisuite_fail', '--instance', self.spec, '--results', self.results)
    self.assertEqual(1, code, said)
    self.assertEqual('FAILED (failures=1)', [line for line in self.report() if line][-1])

  def test_names_by_class_and_test_and_a_wrong_one(self) -> None:
    code, said = self.main('run', 'clisuite_ok.AOkTests.test_b', 'clisuite_ok.NoSuchTests', '--instance', self.spec,
                           '--results', self.results)
    self.assertEqual(1, code, said)
    text = '\n'.join(self.report())
    self.assertIn('AOkTests.test_b ... ok', text)
    self.assertNotIn('AOkTests.test_a', text)
    self.assertIn("no test called 'clisuite_ok.NoSuchTests'", text)
    # a problem is said as itself, unnumbered, as the Java runner's progress has it
    self.assertIn("] no test called 'clisuite_ok.NoSuchTests'\n", said)
    self.assertIn('] test 1/1 AOkTests.test_b ... ok\n', said)

  def test_tests_are_loaded_before_the_game_starts(self) -> None:
    code, said = self.main('run', 'clisuite_nosuch', '--instance', self.spec, '--results', self.results)
    self.assertEqual(1, code, said)
    self.assertEqual([], self.factory.calls, 'nothing to run: no game launched for it')
    text = '\n'.join(self.report())
    self.assertIn('unitTAS.suites ... problem', text)
    self.assertIn("no suite called 'clisuite_nosuch'", text)

  def test_discovered_from_the_current_folder(self) -> None:
    folder = os.path.join(self.scratch, 'tests')
    os.makedirs(folder)
    with open(os.path.join(folder, 'test_discovered.py'), 'w', encoding='utf-8') as file:
      file.write(textwrap.dedent(DISCOVERED))
    code, said = self.main('run', '--instance', self.spec, '--results', self.results, cwd=folder)
    self.assertEqual(0, code, said)
    self.assertIn('DiscoveredTests.test_found ... ok', '\n'.join(self.report()))

  def test_a_game_that_cannot_start_leaves_every_test_without_a_result(self) -> None:
    factory = Factory(os.path.join(self.scratch, 'game'), failing=LinkTimeout('alice: no hello within 1 s'))
    code, said = self.main('run', 'clisuite_ok', '--instance', self.spec, '--results', self.results, factory=factory)
    self.assertEqual(1, code, said)
    lines = self.report()
    self.assertEqual("NO TEST RESULT could be obtained for 2 tests: not run: the game didn't start: alice: no hello "
                     "within 1 s", lines[1])
    text = '\n'.join(lines)
    self.assertIn('unitTAS.game ... problem', text)
    self.assertIn('AOkTests.test_a ... NO RESULT', text)
    self.assertIn('AOkTests.test_b ... NO RESULT', text)
    self.assertIn('NO TEST RESULT', said)
    self.assertEqual('FAILED (no results=2, problems=1)', [line for line in lines if line][-1])

  def test_a_run_that_cannot_begin_is_no_result_once_for_each_test(self) -> None:
    """
    The test world never loads (1.7.10's login race, 2026-11-05): every test is NO RESULT, once. A class's own
    setUpClass doesn't run against a game with no world (that was an ERROR, a verdict), and the count never passes
    the total.
    """
    from fakeprobe import FakeError
    from fakegame import FakeLaunched

    class Unbegun(Factory):
      def __call__(self, spec, results, name='game', **_):
        game = Factory.__call__(self, spec, results, name)

        def stuck(args, side):
          raise FakeError('TimedOut', "unittas didn't open within 180 s", seconds=180)

        game.handlers['world.create'] = stuck
        return game

    factory = Unbegun(os.path.join(self.scratch, 'game'))
    code, said = self.main('run', 'clisuite_unbegun', '--instance', self.spec, '--results', self.results,
                           factory=factory)
    self.assertEqual(1, code, said)
    lines = self.report()
    outcomes = [line.split(' ... ')[:2] for line in lines if ' ... ' in line]
    names = [name for name, _ in outcomes]
    self.assertEqual(['unitTAS.run', 'AFixtureTests.test_a', 'AFixtureTests.test_b', 'BSetUpFailsTests.test_never_runs',
                      'COkTests.test_c'], names, '\n'.join(lines))
    self.assertEqual(['problem', 'NO RESULT', 'NO RESULT', 'NO RESULT', 'NO RESULT'],
                     [outcome.split(' (')[0] for _, outcome in outcomes])
    self.assertEqual('FAILED (no results=4, problems=1)', [line for line in lines if line][-1])
    numbered = [line for line in said.split('\n') if '] test ' in line]
    self.assertEqual(['test %d/4' % n for n in range(1, 5)], [line.split('] ')[1].split(' ')[0] + ' ' +
                                                              line.split('] ')[1].split(' ')[1] for line in numbered])

  def test_ctrl_c_ends_the_run_properly(self) -> None:
    code, said = self.main('run', 'clisuite_stop', '--instance', self.spec, '--results', self.results)
    self.assertEqual(130, code, said)
    text = '\n'.join(self.report())
    self.assertIn('AStopTests.test_a_runs ... ok', text)
    self.assertIn('AStopTests.test_b_is_stopped ... NO RESULT', text)
    self.assertIn('AStopTests.test_c_never_runs ... NO RESULT', text)
    self.assertIn('not run: no test result could be obtained after the run was stopped by Ctrl+C', text)
    self.assertIn('test 3/3 AStopTests.test_c_never_runs ... NO RESULT', said)
    self.assertIn('quit', self.factory.game.ops())
    self.assertEqual(1, self.factory.game.stops)

  def test_watched_by_the_flag_or_the_environment(self) -> None:
    """A run always has its watch (watch.txt, progress.txt); watched, the world's load is the watch's to judge."""
    for argv, environ in ((('--watched',), {}), ((), {'UNITTAS_WATCHED': '1'}), ((), {})):
      sys.modules.pop('clisuite_ok', None)
      results = os.path.join(self.scratch, 'results-%d' % len(self.factory.calls))
      code, said = self.main('run', 'clisuite_ok', '--instance', self.spec, '--results', results, *argv,
                             environ=environ)
      self.assertEqual(0, code, said)
      create = [request['args'] for request in self.factory.game.asked if request['op'] == 'world.create'][0]
      watched = bool(argv or environ)
      self.assertEqual(3600 if watched else None, create.get('max_seconds'), (argv, environ))
      self.assertTrue(os.path.isfile(os.path.join(results, 'watch.txt')), 'no watch.txt')
      with open(os.path.join(results, 'progress.txt'), encoding='utf-8') as file:
        progress = file.read()
      self.assertIn('AOkTests.test_a ... ok', progress)
      self.assertEqual(watched, 'watched: alarms in' in progress.split('\n')[0], progress)

  def test_the_default_results_folder(self) -> None:
    code, said = self.main('run', 'clisuite_ok', '--instance', self.spec,
                           environ={'UNITTAS_STAMP': '2026-11-05_20-00-01'})
    self.assertEqual(0, code, said)
    self.assertIn('AOkTests.test_a ... ok',
                  '\n'.join(self.report(os.path.join(self.scratch, 'unittas-results', '2026-11-05_20-00-01'))))


class LaunchTests(CliCase):

  def hangUpSoon(self) -> None:
    """The fake game goes by itself a moment after it has started, as a closed window does."""

    def later() -> None:
      for _ in range(100):
        game = self.factory.game
        if game is not None and game.fake is not None and game.asked is not None and (
            not self.wantWorld or 'world.prepare' in game.ops()):
          time.sleep(0.2)
          game.fake.event('quit', reason='window closed')
          game.fake.close()
          return
        time.sleep(0.1)

    threading.Thread(target=later, daemon=True).start()

  def test_the_game_until_it_goes(self) -> None:
    self.wantWorld = False
    self.hangUpSoon()
    code, said = self.main('launch', '--instance', self.spec, '--results', self.results)
    self.assertEqual(0, code, said)
    self.assertIn('for looking at', said)
    self.assertNotIn('world.create', self.factory.game.ops())
    self.assertEqual(1, self.factory.game.stops)

  def test_with_the_test_world(self) -> None:
    self.wantWorld = True
    self.hangUpSoon()
    code, said = self.main('launch', '--world', '--instance', self.spec, '--results', self.results)
    self.assertEqual(0, code, said)
    ops = self.factory.game.ops()
    self.assertLess(ops.index('world.create'), ops.index('world.prepare'))

  def test_sigterm_ends_it_as_ctrl_c_does(self) -> None:
    """A launch killed (SIGTERM) still quits its game and puts its files back, as Ctrl+C has it."""
    caught = []

    def safety(signum, frame):  # only if the command didn't take SIGTERM itself: the fake goes, and the test fails
      caught.append(signum)
      self.factory.game.fake.close()

    previous = signal.signal(signal.SIGTERM, safety)
    self.addCleanup(signal.signal, signal.SIGTERM, previous)

    def later() -> None:
      for _ in range(100):
        game = self.factory.game
        if game is not None and game.fake is not None and 'quit' not in game.ops():
          time.sleep(0.3)
          os.kill(os.getpid(), signal.SIGTERM)
          return
        time.sleep(0.1)

    threading.Thread(target=later, daemon=True).start()
    code, said = self.main('launch', '--instance', self.spec, '--results', self.results)
    self.assertEqual(0, code, said)
    self.assertEqual([], caught, 'the command left SIGTERM to the process')
    self.assertIn('the game is asked to quit', said)
    self.assertIs(safety, signal.getsignal(signal.SIGTERM), 'the handler before the command, back after it')
    self.assertEqual(1, self.factory.game.stops)

  def test_a_headless_display_is_refused(self) -> None:
    headless = self.writeSpec('headless.toml', SPEC + 'window = { display = "headless" }\n')
    code, said = self.main('launch', '--instance', headless, '--results', self.results)
    self.assertEqual(2, code)
    self.assertIn('headless', said)
    self.assertEqual([], self.factory.calls)


class CompareTests(CliCase):

  def test_the_same_and_a_difference(self) -> None:
    before = os.path.join(self.scratch, 'before.txt')
    after = os.path.join(self.scratch, 'after.txt')
    with open(before, 'w', encoding='utf-8') as file:
      file.write('unitTAS report\n\nATests.test_a ... ok (0.1 s)\nATests.test_b ... ok (0.2 s)\n' + '-' * 70 + '\n')
    with open(after, 'w', encoding='utf-8') as file:
      file.write('unitTAS report\n\nATests.test_a ... ok (0.3 s)\nATests.test_b ... FAIL (0.2 s)\n' + '-' * 70 + '\n')
    code, said = self.main('compare', before, before)
    self.assertEqual(0, code, said)
    self.assertIn('the same: 2 tests', said)
    code, said = self.main('compare', before, after)
    self.assertEqual(1, code, said)
    self.assertIn('ATests.test_b: ok -> FAIL', said)

  def test_no_result_on_both_sides_is_no_sameness(self) -> None:
    """Two runs with no verdict for a test haven't shown it the same (SPEC.md 9.8): a difference, said as such."""
    report = os.path.join(self.scratch, 'stuck.txt')
    with open(report, 'w', encoding='utf-8') as file:
      file.write('unitTAS report\nNO TEST RESULT could be obtained for 1 test: stuck\n\nATests.test_a ... ok (0.1 s)\n'
                 'ATests.test_b ... NO RESULT (15.0 s)\n    stuck\n' + '-' * 70 + '\n')
    code, said = self.main('compare', report, report)
    self.assertEqual(1, code, said)
    self.assertIn('no result before: ATests.test_b', said)
    self.assertIn('no result after: ATests.test_b', said)


class PlainUnittestTests(CliCase):
  """Under plain unittest, the first GameTestCase starts a run from the spec; it ends at exit."""

  def setUp(self) -> None:
    CliCase.setUp(self)
    self.addCleanup(session.forgetAutoRun)

  def test_started_from_the_spec_and_ended(self) -> None:
    run = session.autoRun(environ={'UNITTAS_INSTANCE': self.spec, 'UNITTAS_STAMP': 'plain'}, cwd=self.scratch,
                          gameFor=self.factory)
    self.assertIs(run, Run.current)
    self.assertIs(run, session.autoRun(environ={}, cwd=self.scratch, gameFor=self.factory), 'one run per process')
    self.assertEqual(1, len(self.factory.calls))
    self.assertIn('world.create', self.factory.game.ops())
    report = session.endAutoRun()
    self.assertEqual(os.path.join(self.scratch, 'unittas-results', 'plain', 'report.txt'), report)
    self.assertEqual(1, self.factory.game.stops)
    self.assertIsNone(Run.current)

  def test_a_game_test_case_under_plain_unittest(self) -> None:
    import clisuite_ok
    previous = session.gameFor
    session.gameFor = self.factory
    self.addCleanup(setattr, session, 'gameFor', previous)
    environ = dict(os.environ)
    os.environ['UNITTAS_INSTANCE'] = self.spec
    os.environ['UNITTAS_STAMP'] = 'plain-unittest'
    self.addCleanup(lambda: (os.environ.clear(), os.environ.update(environ)))
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(
      unittest.TestLoader().loadTestsFromModule(clisuite_ok))
    self.assertTrue(result.wasSuccessful(), result.errors)
    self.assertEqual(2, result.testsRun)
    with open(session.endAutoRun(), encoding='utf-8') as file:
      self.assertIn('AOkTests.test_b ... ok', file.read())

  def test_no_spec_says_how_to_give_one(self) -> None:
    empty = os.path.join(self.scratch, 'empty')
    os.makedirs(empty)
    with self.assertRaises(RuntimeError) as raised:
      session.autoRun(environ={}, cwd=empty, gameFor=self.factory)
    for said in ('unittas run', 'UNITTAS_INSTANCE', 'unittas.toml'):
      self.assertIn(said, str(raised.exception))

  def test_a_game_that_cannot_start_is_tried_once(self) -> None:
    factory = Factory(os.path.join(self.scratch, 'game'), failing=LinkTimeout('alice: no hello within 1 s'))
    environ = {'UNITTAS_INSTANCE': self.spec, 'UNITTAS_STAMP': 'unstarted'}
    for _ in range(2):
      with self.assertRaises(NoResult) as raised:
        session.autoRun(environ=environ, cwd=self.scratch, gameFor=factory)
      self.assertIn("the game didn't start", str(raised.exception))
    self.assertEqual(1, len(factory.calls))


if __name__ == '__main__':
  unittest.main()

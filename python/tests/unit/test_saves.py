"""
Old saves through the orchestrator (SPEC.md 9.3 step 9), without a game.
- 9a, Java suites (unittas run --java): the saves put in as fresh copies (what was there of the same name kept in the
  results), java.run asked with their names and the pristine folder, the Java runner's numbered lines shown as they
  come, the saves as the game left them kept after.
- 9b, save mode for Python tests (unittas run TESTS --saves): each save opened twice, as found and as this game saved
  it, in the Java runner's order; the suite in each with no resets and no world hooks; each line named
  'Class.test [save, load N]'; a test's self.save(), with the log's errors between the asking and the settled world.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest

import gamecases
from unittas import session
from unittas.run import Run, runSaves
from test_cli import CliCase
from test_run import FakeRun


def makeSaves(folder: str, names: tuple) -> None:
  """A save set as the pristine folder has one: a folder with a level.dat for each, a building list beside it."""
  for name in names:
    os.makedirs(os.path.join(folder, name, 'region'))
    with open(os.path.join(folder, name, 'level.dat'), 'w') as file:
      file.write('pristine %s' % name)
    with open(os.path.join(folder, name + '.buildings'), 'w') as file:
      file.write('marker 0 8 4 8 8 4 8 view 8.5 4.0 10.5 180.0 10.0\n')


class SavesInAndOutTests(unittest.TestCase):

  def setUp(self) -> None:
    self.scratch = tempfile.mkdtemp(prefix='unittas-saves-')
    self.addCleanup(shutil.rmtree, self.scratch, True)

  def test_fresh_copies_in_and_kept_after(self) -> None:
    pristine = os.path.join(self.scratch, 'pristine')
    makeSaves(pristine, ('b-save', 'a-save'))
    os.makedirs(os.path.join(pristine, 'not-a-save'))
    game = os.path.join(self.scratch, 'game')
    os.makedirs(os.path.join(game, 'saves', 'a-save'))
    with open(os.path.join(game, 'saves', 'a-save', 'level.dat'), 'w') as file:
      file.write('an earlier run left this')
    results = os.path.join(self.scratch, 'results')
    names = session.savesIn(pristine, game, results)
    self.assertEqual(['a-save', 'b-save'], names)
    with open(os.path.join(game, 'saves', 'a-save', 'level.dat')) as file:
      self.assertEqual('pristine a-save', file.read())
    with open(os.path.join(results, 'saves-before-this-run', 'a-save', 'level.dat')) as file:
      self.assertEqual('an earlier run left this', file.read(), 'what was there is kept, never deleted')
    session.savesOut(names, game, results)
    self.assertEqual([], os.listdir(os.path.join(game, 'saves')))
    self.assertEqual(['a-save', 'b-save'], sorted(os.listdir(os.path.join(results, 'saves-after'))))

  def test_no_saves_is_a_usage_mistake(self) -> None:
    empty = os.path.join(self.scratch, 'empty')
    os.makedirs(empty)
    with self.assertRaises(session.UsageError) as raised:
      session.savesIn(empty, os.path.join(self.scratch, 'game'), os.path.join(self.scratch, 'results'))
    self.assertIn('no saves', str(raised.exception))


class JavaSuitesTests(CliCase):
  """9a: unittas run --java."""

  def test_java_suites_in_save_mode(self) -> None:
    pristine = os.path.join(self.scratch, 'pristine')
    makeSaves(pristine, ('a-save', 'b-save'))
    code, said = self.main('run', '--java', 'oldsaves', '--saves', pristine, '--instance', self.spec, '--results',
                           self.results)
    self.assertEqual(0, code, said)
    asked = [request['args'] for request in self.factory.game.asked if request['op'] == 'java.run'][0]
    self.assertEqual(['oldsaves'], asked['suites'])
    self.assertEqual(['a-save', 'b-save'], asked['saves'])
    self.assertEqual(os.path.abspath(pristine), asked['oldsaves'])
    self.assertEqual(self.results, asked['results'])
    for line in ('test 1/4 SaveTests.test_x [a-save, load 1] ... ok', 'test 4/4 SaveTests.test_x [b-save, load 2] ... ok'):
      self.assertIn('] %s\n' % line, said, "the Java runner's lines, as they come")
    self.assertTrue(said.rstrip().endswith('OK'), said)
    self.assertEqual(['a-save', 'b-save'], sorted(os.listdir(os.path.join(self.results, 'saves-after'))))
    self.assertNotIn('world.create', self.factory.game.ops(), "Java's runner makes its own worlds")
    self.assertEqual('quit', self.factory.game.ops()[-1])

  def test_java_suites_in_the_test_world(self) -> None:
    code, said = self.main('run', '--java', 'self,self-red', '--instance', self.spec, '--results', self.results)
    self.assertEqual(0, code, said)
    asked = [request['args'] for request in self.factory.game.asked if request['op'] == 'java.run'][0]
    self.assertEqual(['self', 'self-red'], asked['suites'])
    self.assertEqual([], asked.get('saves', []))
    self.assertNotIn('oldsaves', asked)

  def test_tests_and_java_suites_are_one_or_the_other(self) -> None:
    code, said = self.main('run', 'clisuite_ok', '--java', 'self', '--instance', self.spec)
    self.assertEqual(2, code)
    self.assertIn('--java', said)


class PythonSaveModeTests(FakeRun, unittest.TestCase):
  """9b: the Python Run's own save loop."""

  def setUp(self) -> None:
    FakeRun.setUp(self)
    self.pristine = os.path.join(self.scratch, 'pristine')
    makeSaves(self.pristine, ('a-save', 'b-save'))
    fake = self.fake

    def opened(args, side):
      if args['folder'] == 'b-save':
        fake.event('log', level='ERROR', logger='Minecraft-Server', thread='Server thread',
                   message='Couldn\'t load chunk', thrown='java.io.EOFException: truncated')
      return {'folder': args['folder'], 'name': args['folder'], 'load_ms': 5}

    self.handlers['world.open'] = opened
    self.handlers['ticks.wait'] = lambda args, side: {'waited_ms': 50, 'from': 1, 'tick': 1 + args.get('n', 1)}
    self.addCleanup(setattr, Run, 'current', None)

  def test_each_save_twice_in_the_java_runners_order(self) -> None:
    runSaves(self.run, ['gamecases.SaveCaseTests'], ['a-save', 'b-save'], self.pristine, stream=io.StringIO())
    with open(self.run.finish(), encoding='utf-8') as file:
      lines = file.read().split('\n')
    tests = [line.split(' ... ')[0] for line in lines if ' ... ' in line]
    self.assertEqual(['SaveCaseTests.test_a_sees_its_save [a-save, load 1]', 'SaveCaseTests.test_b_passes [a-save, load 1]',
                      'SaveCaseTests.test_a_sees_its_save [b-save, load 1]', 'SaveCaseTests.test_b_passes [b-save, load 1]',
                      'SaveCaseTests.test_a_sees_its_save [a-save, load 2]', 'SaveCaseTests.test_b_passes [a-save, load 2]',
                      'SaveCaseTests.test_a_sees_its_save [b-save, load 2]', 'SaveCaseTests.test_b_passes [b-save, load 2]'],
                     tests)
    self.assertEqual('OK', [line for line in lines if line][-1])
    ops = []
    for request in self.asked:
      if request['op'] in ('world.open', 'world.close', 'world.create', 'batch', 'hooks.run'):
        folder = (request.get('args') or {}).get('folder')
        ops.append(request['op'] + (' ' + folder if folder else ''))
    self.assertEqual(['hooks.run', 'world.open a-save', 'world.close', 'world.open b-save', 'world.close',
                      'world.open a-save', 'world.close', 'world.open b-save', 'world.close', 'hooks.run'], ops,
                     'no world made, no reset')
    hooks = [request['args']['hook'] for request in self.asked if request['op'] == 'hooks.run']
    self.assertEqual(['beforeRun', 'afterRun'], hooks, 'no world hooks in save mode: they would change the save')
    settles = [request['args']['n'] for request in self.asked if request['op'] == 'ticks.wait']
    self.assertEqual([60, 60, 60, 60], settles, 'each save settles 60 client ticks before its tests')

  def test_a_test_sees_its_save(self) -> None:
    runSaves(self.run, ['gamecases.SaveCaseTests'], ['a-save', 'b-save'], self.pristine, stream=io.StringIO())
    seen = gamecases.SaveCaseTests.seen[self.run]
    self.assertEqual([('a-save', 1), ('b-save', 1), ('a-save', 2), ('b-save', 2)], [(f, n) for f, n, _ in seen])
    self.assertEqual((), seen[0][2])
    self.assertEqual(("[Minecraft-Server] Couldn't load chunk (java.io.EOFException: truncated)",), seen[1][2],
                     "the log's errors between the asking and the settled world, as TasSave words them")
    with open(os.path.join(self.results, 'progress.txt'), encoding='utf-8') as file:
      progress = file.read()
    for said in ('opening a-save as it was found', 'opening a-save again, as this game saved it',
                 'test 8/8 SaveCaseTests.test_b_passes [b-save, load 2] ... ok'):
      self.assertIn(said, progress)

  def test_the_save_open_and_its_pristine_copy(self) -> None:
    self.run.saveMode = True
    self.run.openSave('a-save', 1, self.pristine)
    self.assertEqual(os.path.join(self.pristine, 'a-save'), self.run.save.pristine)
    self.assertEqual(os.path.join(self.pristine, 'a-save.buildings'), self.run.save.buildings)
    self.assertGreaterEqual(self.run.save.loadSeconds, 0.0)


if __name__ == '__main__':
  unittest.main()

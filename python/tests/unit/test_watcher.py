"""
'unittas watch' (unittas.watcher, SPEC.md 9.3 step 8b), without a game: a queue folder, and a runner that records
what it was asked to run. The same files as unittas-watch.sh: a request taken, its run folder in 'run', its exit code
in 'done'; each notify line handed to ./request_task.sh. A request is 'unittas run's arguments, watched; in unitTAS's
own repository, '<suites> [filter]' and 'probe [filter]' as unittas-watch.sh runs them.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import shutil
import stat
import sys
import tempfile
import unittest

from unittas.watcher import QueueWatcher


class Runner:
  """Records each run asked for (its words, folder and environment) and exits with 'code'."""

  def __init__(self, code: int = 3) -> None:
    self.code = code
    self.runs = []

  def __call__(self, argv: list, cwd: str, env: dict) -> int:
    self.runs.append((argv, cwd, env))
    return self.code


class WatcherTests(unittest.TestCase):

  def setUp(self) -> None:
    self.root = tempfile.mkdtemp(prefix='unittas-watcher-')
    self.addCleanup(shutil.rmtree, self.root, True)
    self.queue = os.path.join(self.root, 'unittas-queue')
    self.runner = Runner()
    self.out = io.StringIO()

  def watcher(self) -> QueueWatcher:
    return QueueWatcher(self.root, runner=self.runner, out=self.out, environ={'HOME': '/home/someone'},
                        stamp=lambda: '2026-11-05_21-00-00')

  def ask(self, line: str) -> None:
    os.makedirs(self.queue, exist_ok=True)
    with open(os.path.join(self.queue, 'request'), 'w', encoding='utf-8') as file:
      file.write(line + '\n')

  def read(self, name: str) -> str:
    with open(os.path.join(self.queue, name), encoding='utf-8') as file:
      return file.read()

  def test_nothing_asked_nothing_run(self) -> None:
    self.assertFalse(self.watcher().once())
    self.assertEqual([], self.runner.runs)

  def test_a_request_is_unittas_run_watched(self) -> None:
    self.ask('tests.test_doors tests.test_give.GiveTests')
    self.assertTrue(self.watcher().once())
    results = os.path.join(self.root, 'unittas-results', '2026-11-05_21-00-00')
    argv, cwd, env = self.runner.runs[0]
    self.assertEqual([sys.executable, '-m', 'unittas', 'run', 'tests.test_doors', 'tests.test_give.GiveTests',
                      '--watched', '--results', results], argv)
    self.assertEqual(self.root, cwd)
    self.assertEqual('2026-11-05_21-00-00', env['UNITTAS_STAMP'])
    self.assertEqual(results + '\n', self.read('run'))
    self.assertEqual('3\n', self.read('done'))
    self.assertFalse(os.path.exists(os.path.join(self.queue, 'request')), 'the request taken')
    self.assertIn('asked for: tests.test_doors tests.test_give.GiveTests', self.out.getvalue())
    self.assertIn('finished (exit 3)', self.out.getvalue())

  def test_in_unittas_own_repository_as_the_script_has_it(self) -> None:
    with open(os.path.join(self.root, 'unittas.sh'), 'w', encoding='utf-8') as file:
      file.write('#!/usr/bin/env bash\n')
    os.makedirs(os.path.join(self.root, 'python', 'tests', 'probe'))
    watcher = self.watcher()
    self.ask('probe test_core.')
    watcher.once()
    self.ask('self,self-red,nosuch Give me')
    watcher.once()
    self.ask('')
    watcher.once()
    (probe, _, probeEnv), (suites, _, suitesEnv), (every, _, _) = self.runner.runs
    self.assertEqual([sys.executable, '-m', 'unittas.selftest', 'test_core.'], probe)
    self.assertEqual('2026-11-05_21-00-00', probeEnv['UNITTAS_STAMP'])
    self.assertNotIn('UNITTAS_WATCHED', probeEnv)
    self.assertEqual(['./unittas.sh', 'self,self-red,nosuch', 'Give me'], suites)
    self.assertEqual('1', suitesEnv['UNITTAS_WATCHED'])
    self.assertEqual(['./unittas.sh', '', ''], every)
    self.assertIn('asked for: every suite', self.out.getvalue())

  def test_notify_lines_handed_to_request_task(self) -> None:
    told = os.path.join(self.root, 'told.txt')
    script = os.path.join(self.root, 'request_task.sh')
    with open(script, 'w', encoding='utf-8') as file:
      file.write('#!/bin/sh\nprintf "%%s\\n" "$1" >> "%s"\n' % told)
    os.chmod(script, os.stat(script).st_mode | stat.S_IXUSR)
    os.makedirs(self.queue)
    with open(os.path.join(self.queue, 'notify'), 'w', encoding='utf-8') as file:
      file.write('full run done, 144/144\n\nwaiting for you\n')
    self.assertEqual(2, self.watcher().notifyOnce())
    with open(told, encoding='utf-8') as file:
      self.assertEqual('full run done, 144/144\nwaiting for you\n', file.read())
    self.assertFalse(os.path.exists(os.path.join(self.queue, 'notify')))
    self.assertFalse(os.path.exists(os.path.join(self.queue, 'notify.sending')))
    self.assertIn('notify: waiting for you', self.out.getvalue())

  def test_notify_without_request_task_is_only_shown(self) -> None:
    os.makedirs(self.queue)
    with open(os.path.join(self.queue, 'notify'), 'w', encoding='utf-8') as file:
      file.write('hello\n')
    self.assertEqual(1, self.watcher().notifyOnce())
    self.assertIn('no executable ./request_task.sh, so only shown here', self.out.getvalue())

  def test_the_command_line(self) -> None:
    from unittas import cli
    out = io.StringIO()
    self.assertEqual(2, cli.main(['watch', 'extra'], out=out, environ={}, cwd=self.root))
    self.assertIn('unittas watch', out.getvalue())


if __name__ == '__main__':
  unittest.main()

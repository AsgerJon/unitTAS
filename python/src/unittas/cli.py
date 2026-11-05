"""
The 'cli' module is the 'unittas' command (SPEC.md 9.3, step 8a):

  unittas run [TESTS ...] [--instance FILE] [--results DIR] [--watched]
  unittas launch [--instance FILE] [--results DIR] [--world]
  unittas watch [--queue DIR]
  unittas compare BEFORE/report.txt AFTER/report.txt

- run: the tests on the game the instance spec names. TESTS are
  unittest's names (a module, module.Class, module.Class.test); none, and
  they are discovered from the current folder (test*.py). The report goes
  into the results folder (unittas-results/<time>/ beside the spec, unless
  --results says), each test's line shown as it ends. Exit 0 for OK, 1 for
  FAILED, 2 for a mistake in the command or the spec, 130 after Ctrl+C.
  --watched (or UNITTAS_WATCHED=1): where a fixed limit would decide the
  game is stuck, an alarm asks the watcher first (unittas.watch).
- launch: the spec's game as a run has it, nothing run, for looking at;
  --world opens the test world in it.
- watch: the runs a session that can't open windows asks for, in the
  queue folder (unittas-queue/ here), made here (unittas.watcher).
- compare: two reports test by test (unittas.compare).

SIGTERM ends a run or a launch as Ctrl+C does.

The spec is --instance's, else UNITTAS_INSTANCE's, else unittas.toml in
the current folder.

- main: the command, with its arguments; its exit code.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
from typing import TYPE_CHECKING

from . import compare, session

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Callable, Optional, TextIO

USAGE = '''usage:
  unittas run [TESTS ...] [--instance FILE] [--results DIR] [--watched]
  unittas launch [--instance FILE] [--results DIR] [--world]
  unittas watch [--queue DIR]
  unittas compare BEFORE/report.txt AFTER/report.txt'''


class _Parser(argparse.ArgumentParser):
  """argparse, with its mistakes raised (as UsageError) rather than printed and exited on."""

  def error(self, message: str) -> None:
    raise session.UsageError(message)


def _parser() -> _Parser:
  parser = _Parser(prog='unittas', usage=USAGE, add_help=False)
  commands = parser.add_subparsers(dest='command', parser_class=_Parser)
  run = commands.add_parser('run', usage=USAGE, add_help=False)
  run.add_argument('tests', nargs='*')
  run.add_argument('--instance')
  run.add_argument('--results')
  run.add_argument('--watched', action='store_true')
  launch = commands.add_parser('launch', usage=USAGE, add_help=False)
  launch.add_argument('--instance')
  launch.add_argument('--results')
  launch.add_argument('--world', action='store_true')
  queue = commands.add_parser('watch', usage=USAGE, add_help=False)
  queue.add_argument('--queue')
  reports = commands.add_parser('compare', usage=USAGE, add_help=False)
  reports.add_argument('before')
  reports.add_argument('after')
  return parser


def _stopAsCtrlC(signum: int, frame: Any) -> None:
  raise KeyboardInterrupt()


def main(argv: Optional[list] = None, out: Optional[TextIO] = None, environ: Optional[dict] = None,
         cwd: Optional[str] = None, gameFor: Optional[Callable] = None) -> int:
  """
  The command (the console script's entry point); its exit code. 'gameFor'
  starts the spec's game (a test bench's stands in for unittas.specgame's).
  """
  argv = sys.argv[1:] if argv is None else list(argv)
  out = sys.stdout if out is None else out
  environ = os.environ if environ is None else environ
  cwd = os.getcwd() if cwd is None else cwd
  if argv[:1] in (['-h'], ['--help'], ['help']):
    print(USAGE, file=out)
    return 0
  try:
    args = _parser().parse_args(argv)
    if args.command is None:
      raise session.UsageError('no command given')
    if args.command == 'compare':
      return compare.main(args.before, args.after, out=out)
    if args.command == 'watch':
      from .watcher import QueueWatcher
      return QueueWatcher(cwd, queue=args.queue, out=out, environ=environ).serve()
    spec = session.readSpec(session.findSpec(args.instance, environ, cwd))
    results = session.resultsFolder(spec, args.results, environ)
    #  SIGTERM ends a run or a launch as Ctrl+C does: properly, the game quit and the folder's own files put back
    mainThread = threading.current_thread() is threading.main_thread()
    before = signal.signal(signal.SIGTERM, _stopAsCtrlC) if mainThread else None
    try:
      if args.command == 'launch':
        return session.launchGame(spec, results, out, world=args.world, gameFor=gameFor)
      return session.runTests(spec, args.tests, results, out, cwd, environ, gameFor=gameFor, watched=args.watched)
    finally:
      if mainThread:
        signal.signal(signal.SIGTERM, before)
  except session.UsageError as error:
    print('unittas: %s\n%s' % (error, USAGE), file=out)
    return 2


if __name__ == '__main__':
  sys.exit(main())

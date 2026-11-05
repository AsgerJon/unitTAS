"""
The 'session' module starts the game an instance spec names and runs tests
on it (SPEC.md 9.3, step 8a), for 'unittas run', 'unittas launch' and
plain 'python -m unittest' alike.

- The spec: the one given (--instance), else UNITTAS_INSTANCE's, else
  unittas.toml in the current folder.
- The results: the folder given, else unittas-results/<time>/ beside the
  spec ('latest' pointing at it; UNITTAS_STAMP names it).
- The tests are loaded before the game starts, so a suite that can't load
  costs no launch; a game that can't start leaves every test NO RESULT
  (SPEC.md 9.8), under a unitTAS.game problem.

- UsageError: a mistake in how the command was called.
- findSpec, resultsFolder: where the spec and the results are.
- runTests: 'unittas run'; watchFor its watch; launchGame: 'unittas
  launch'.
- autoRun, endAutoRun: the run plain unittest's first GameTestCase starts.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import atexit
import os
import sys
import time
from typing import TYPE_CHECKING

from .api import Game
from .errors import NO_RESULT_ERRORS, NoResult, UnitTasError, whyNoResult
from .gamefiles import removeTree
from .run import FOLDER, Run, loadSuites, reportNames, runSuite
from .spec import InstanceSpec, SpecError
from .specgame import gameFor
from .watch import Watch

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Callable, Optional, TextIO

  from .game import LaunchedGame
  from .link import Connection
  from .mappings import Mappings

SPEC_NAME = 'unittas.toml'
#  From the game's hello to its first tick at the title screen: every mod loaded (a modpack takes its time).
READY_SECONDS = float(os.environ.get('UNITTAS_READY_SECONDS', '600'))
NO_RUN = ('no unitTAS run: start the tests with "unittas run", or give plain unittest an instance spec to start one '
          'from: UNITTAS_INSTANCE, or %s in the current folder (%s)')
CTRL_C = 'the run was stopped by Ctrl+C'


class UsageError(Exception):
  """The command was called wrong: its message says how, for exit code 2."""


# ---------------------------------------------------------------- where things are


def findSpec(given: Optional[str], environ: dict, cwd: str) -> str:
  """The instance spec's path: the one given, else UNITTAS_INSTANCE's, else unittas.toml in cwd. UsageError if none."""
  if given:
    if not os.path.isfile(given):
      raise UsageError('--instance %s: no such file' % given)
    return os.path.abspath(given)
  named = environ.get('UNITTAS_INSTANCE')
  if named:
    if not os.path.isfile(named):
      raise UsageError('UNITTAS_INSTANCE=%s: no such file' % named)
    return os.path.abspath(named)
  here = os.path.join(cwd, SPEC_NAME)
  if os.path.isfile(here):
    return os.path.abspath(here)
  raise UsageError('no instance spec: give one with --instance FILE, set UNITTAS_INSTANCE, or put %s in this folder '
                   '(%s)' % (SPEC_NAME, cwd))


def resultsFolder(spec: InstanceSpec, given: Optional[str], environ: dict) -> str:
  """
  The run's folder, made: the one given, else unittas-results/<time>/
  beside the spec, with 'latest' there pointing at it (only ever a link
  replaced, never a folder).
  """
  if given:
    folder = os.path.abspath(given)
    os.makedirs(folder, exist_ok=True)
    return folder
  stamp = environ.get('UNITTAS_STAMP') or time.strftime('%Y-%m-%d_%H-%M-%S')
  root = os.path.join(spec.folder, 'unittas-results')
  folder = os.path.join(root, stamp)
  os.makedirs(folder, exist_ok=True)
  latest = os.path.join(root, 'latest')
  if os.path.islink(latest) or not os.path.lexists(latest):
    if os.path.lexists(latest):
      os.remove(latest)
    os.symlink(stamp, latest)
  return folder


def readSpec(path: str) -> InstanceSpec:
  """The spec; a mistake in it is a UsageError naming the file and the key."""
  try:
    return InstanceSpec.read(path)
  except SpecError as error:
    raise UsageError(str(error)) from None


# ---------------------------------------------------------------- the game


def _why(error: BaseException) -> str:
  """What went wrong, in words: the package's own errors as they say it, anything else with its type."""
  if isinstance(error, NO_RESULT_ERRORS):
    return whyNoResult(error)
  return _said(error)


def _said(error: BaseException) -> str:
  """An error's own words (the package's, a spec's), or anything else's with its type: why a game didn't start."""
  if isinstance(error, (UnitTasError, SpecError)):
    return str(error)
  return '%s: %s' % (type(error).__name__, error)


def mappingsFor(connection: Connection, launched: LaunchedGame, environ: dict) -> Optional[Mappings]:
  """
  The mappings a real client's reflection needs (its hello says names:
  srg): from the Gradle cache (UNITTAS_GRADLE_HOME, GRADLE_USER_HOME, or
  ~/.gradle) or the download cache. None for a development client.
  """
  if connection.hello.names != 'srg':
    return None
  from .cache import Cache
  from .launcher import Sources
  from .mappings import Mappings
  gradleHome = (environ.get('UNITTAS_GRADLE_HOME') or environ.get('GRADLE_USER_HOME')
                or os.path.join(os.path.expanduser('~'), '.gradle'))
  return Mappings.load(Sources(gradleHome=gradleHome, cache=getattr(launched, 'cache', None) or Cache()))


def _ready(launched: LaunchedGame) -> Connection:
  """The game started and at its title screen ('ready'); stopped again if it doesn't get there."""
  connection = launched.start()
  try:
    connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
  except BaseException:
    launched.stop()
    raise
  return connection


def _unstarted(results: str, problems: list, names: list, why: str) -> str:
  """The report of a run whose game never started: its problems, and every test NO RESULT."""
  run = Run(None, '', results)
  for name, detail in problems:
    run.problem(name, detail)
  run.problem('unitTAS.game', "the game didn't start: %s" % why)
  run.notRun(names, "not run: the game didn't start: %s" % why)
  return run.writeReport()


# ---------------------------------------------------------------- unittas run


def _show(out: TextIO, report: str) -> bool:
  """The report's path and its verdict, for the terminal; whether it says OK."""
  with open(report, encoding='utf-8') as file:
    lines = [line for line in file.read().split('\n') if line]
  print('report: %s' % report, file=out)
  headline = [line for line in lines[1:2] if line.startswith('NO TEST RESULT')]
  for line in headline:
    print(line, file=out)
  print(lines[-1], file=out)
  return lines[-1] == 'OK'


def watchFor(run: Run, environ: dict, watched: bool = False) -> Watch:
  """
  The run's watch, started: watched by the flag or UNITTAS_WATCHED=1, live
  pictures every UNITTAS_PICTURE_SECONDS (10), an alarm's answer awaited
  UNITTAS_DECIDE_SECONDS (300). Its first progress line says which.
  """
  watched = watched or environ.get('UNITTAS_WATCHED') == '1'
  watch = Watch(run, watched=watched, pictures=int(environ.get('UNITTAS_PICTURE_SECONDS', '10')),
                decide=int(environ.get('UNITTAS_DECIDE_SECONDS', '300')))
  run.progress('unitTAS run: %d test%s%s' % (run.total, '' if run.total == 1 else 's', (
    '; watched: alarms in %s' % os.path.join(run.results, 'alarm.txt')) if watched else ''))
  watch.start()
  return watch


def runTests(spec: InstanceSpec, names: list, results: str, out: TextIO, cwd: str, environ: dict,
             gameFor: Optional[Callable] = None, watched: bool = False) -> int:
  """
  'unittas run': the tests on the spec's game, watched (watchFor), the
  report shown. 0 for OK, 1 for FAILED, 130 after Ctrl+C (the run ended
  properly all the same).
  """
  start = gameFor or globals()['gameFor']
  suite, problems = loadSuites(names, cwd)
  wanted = reportNames(suite)

  def say(line: str) -> None:
    print('[%s] %s' % (time.strftime('%H:%M:%S'), line), file=out)
    out.flush()

  if suite.countTestCases() == 0:
    run = Run(None, '', results, say=say)
    for name, detail in problems:
      run.problem(name, detail)
    if not problems:
      run.problem('unitTAS.suites', 'no tests to run: none %s' % (
        'named' if names else 'found under %s (test*.py)' % cwd))
    _show(out, run.writeReport())
    return 1
  launched = start(spec, results, 'game')
  try:
    connection = _ready(launched)
  except Exception as error:  # whatever kept the game from starting: no test has a result
    _show(out, _unstarted(results, problems, wanted, _said(error)))
    return 1
  run = Run(Game(connection), launched.gameDir, results, stop=launched.stop, say=say)
  run.total = len(wanted)
  watch = watchFor(run, environ, watched)
  try:
    run.game.mappings = mappingsFor(connection, launched, environ)
  except Exception as error:  # reflection by readable names won't work: unitTAS's own trouble, said
    run.problem('unitTAS.mappings', "a real client's readable names can't be had: %s" % _why(error))
  for name, detail in problems:
    run.problem(name, detail)
  interrupted = False
  passedUnittest = True
  try:
    try:
      run.begin()
    except Exception as error:  # the run's world or its plugins' beforeRun: nothing after it has a result
      run.problem('unitTAS.run', "the run couldn't begin: %s" % _why(error))
      run.stopped = "the run couldn't begin: %s" % _why(error)
    with open(os.path.join(results, 'unittest.txt'), 'w', encoding='utf-8') as log:
      passedUnittest = runSuite(run, suite, stream=log, verbosity=2).wasSuccessful()
  except KeyboardInterrupt:
    interrupted = True
    if run.stopped is None:
      run.stopped = CTRL_C
  finally:
    watch.stop()
    if run.stopped is not None:
      run.notRun(wanted, 'not run: no test result could be obtained after %s' % run.stopped)
    report = run.finish()
  passed = _show(out, report)
  if interrupted:
    return 130
  return 0 if passed and passedUnittest else 1


# ---------------------------------------------------------------- unittas launch


def launchGame(spec: InstanceSpec, results: str, out: TextIO, world: bool = False,
               gameFor: Optional[Callable] = None) -> int:
  """
  'unittas launch': the spec's game as a run has it, for a person to look
  at, until its window closes or Ctrl+C; with 'world', in the test world.
  """
  if spec.display == 'headless':
    raise UsageError('%s: window.display is "headless": a launch would have nothing to look at (say "nested" or '
                     '"plain")' % spec.path)
  launched = (gameFor or globals()['gameFor'])(spec, results, 'launch')
  print("unittas launch: %s's game, for looking at: the probe drops the real mouse and keyboard (PROTOCOL.md 2.5), "
        'so it can\'t be played. Close its window, or press Ctrl+C here, to end it.' % spec.path, file=out)
  out.flush()
  try:
    connection = _ready(launched)
    if world:
      game = Game(connection)
      folder = os.path.join(launched.gameDir, 'saves', FOLDER)
      if os.path.lexists(folder):
        removeTree(folder)
      game.request('world.create', {'folder': FOLDER}, timeout=240)
      game.request('world.prepare')
    print('the game is up%s (its output: %s)' % (' in the test world' if world else '', results), file=out)
    out.flush()
    while not connection.closed:
      time.sleep(0.2)
    print('the game has gone: %s' % connection.closedBecause, file=out)
    return 0
  except KeyboardInterrupt:
    print('Ctrl+C: the game is asked to quit', file=out)
    return 0
  except Exception as error:  # the game didn't start, or its world didn't come
    print("unittas launch: the game didn't come up: %s" % _said(error), file=out)
    return 1
  finally:
    launched.stop()


# ---------------------------------------------------------------- plain unittest

#  The run plain unittest started, its game, and why it couldn't be had (tried once, then said again).
_auto = {'run': None, 'launched': None, 'failed': None}


def autoRun(environ: Optional[dict] = None, cwd: Optional[str] = None, gameFor: Optional[Callable] = None) -> Run:
  """
  The run plain unittest's first GameTestCase starts, from the spec
  (UNITTAS_INSTANCE, or unittas.toml in the current folder), and ends at
  exit. RuntimeError with no spec; NoResult if its game can't start (then
  it isn't tried again).
  """
  if _auto['run'] is not None:
    return _auto['run']
  if _auto['failed'] is not None:
    raise NoResult(_auto['failed'])
  environ = os.environ if environ is None else environ
  cwd = os.getcwd() if cwd is None else cwd
  try:
    spec = readSpec(findSpec(None, environ, cwd))
  except UsageError as error:
    raise RuntimeError(NO_RUN % (SPEC_NAME, error)) from None
  results = resultsFolder(spec, None, environ)
  launched = (gameFor or globals()['gameFor'])(spec, results, 'game')
  try:
    connection = _ready(launched)
  except Exception as error:  # whatever kept the game from starting
    _auto['failed'] = "the game didn't start: %s (its output: %s)" % (_said(error), results)
    raise NoResult(_auto['failed']) from error
  run = Run(Game(connection), launched.gameDir, results, stop=launched.stop)
  _auto.update(run=run, launched=launched, watch=watchFor(run, environ))
  Run.current = run
  atexit.register(_atExit)
  try:
    run.game.mappings = mappingsFor(connection, launched, environ)
  except Exception as error:  # reflection by readable names won't work
    run.problem('unitTAS.mappings', "a real client's readable names can't be had: %s" % _why(error))
  try:
    run.begin()
  except Exception as error:  # nothing after it has a result
    run.problem('unitTAS.run', "the run couldn't begin: %s" % _why(error))
    run.stopped = "the run couldn't begin: %s" % _why(error)
  return run


def endAutoRun() -> Optional[str]:
  """Ends plain unittest's run, if one was started: the game quits, its files go back; the report's path."""
  run = _auto['run']
  if run is None:
    return None
  if _auto.get('watch') is not None:
    _auto['watch'].stop()
  _auto.update(run=None, launched=None, watch=None)
  atexit.unregister(_atExit)
  if Run.current is run:
    Run.current = None
  return run.finish()


def forgetAutoRun() -> None:
  """For a test bench: no run, and no failure remembered."""
  endAutoRun()
  _auto['failed'] = None


def _atExit() -> None:
  report = endAutoRun()
  if report is not None:
    print('unitTAS report: %s' % report, file=sys.stderr)

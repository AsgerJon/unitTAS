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
- runTests: 'unittas run' (in save mode with --saves); runJava: 'unittas
  run --java'; findSaves, savesIn, savesOut: the old saves in and out;
  watchFor a run's watch; launchGame: 'unittas launch'.
- autoRun, endAutoRun: the run plain unittest's first GameTestCase starts.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import atexit
import os
import shutil
import sys
import time
from typing import TYPE_CHECKING

from .api import Game
from .errors import NO_RESULT_ERRORS, LinkTimeout, NoResult, UnitTasError, whyNoResult
from .gamefiles import copyExactly, removeTree
from .run import FOLDER, Run, loadSuites, reportNames, runSaves, runSuite
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
#  Meanwhile its log is watched (SPEC.md, after 9.8): a game loading its mods writes to it all along. Nothing new in
#  it for the first, the terminal says so; for the second, the game is given up as hung while it loaded.
LOG_QUIET_SAY_SECONDS = 120.0
LOG_QUIET_SECONDS = float(os.environ.get('UNITTAS_LOG_QUIET_SECONDS', '300'))
READY_POLL_SECONDS = 1.0
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
  if isinstance(error, NoResult):
    return error.why
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


def _span(seconds: float) -> str:
  """'5 minutes', '2 minutes', '90 s', '0.3 s'."""
  if seconds >= 60 and seconds % 60 == 0:
    minutes = int(seconds // 60)
    return '%d minute%s' % (minutes, '' if minutes == 1 else 's')
  return '%g s' % seconds


def _logOf(launched: LaunchedGame) -> Optional[str]:
  """The file the game's output is in (gradle.log, client.log), where a loading game writes; None if it has none."""
  name = getattr(launched, 'outputName', None)
  return None if name is None else os.path.join(launched.results, name())


def _size(path: Optional[str]) -> int:
  try:
    return os.path.getsize(path) if path is not None else -1
  except OSError:
    return -1


def _awaitReady(connection: Connection, launched: LaunchedGame, say: Callable[[str], Any]) -> None:
  """
  'ready' waited for, the game's log watched meanwhile: nothing new in it
  for LOG_QUIET_SAY_SECONDS, said; for LOG_QUIET_SECONDS, LinkTimeout (a
  game hung while it loaded its mods). READY_SECONDS is the outer bound.
  The game's own end (LinkClosed) comes through as it is.
  """
  log = _logOf(launched)
  started = time.monotonic()
  size, grewAt, said = _size(log), started, False
  while True:
    try:
      connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_POLL_SECONDS)
      return
    except LinkTimeout:
      pass
    now = time.monotonic()
    if now - started >= READY_SECONDS:
      raise LinkTimeout('it never came to its title screen within %s (its log: %s)' % (_span(READY_SECONDS), log))
    if log is None:
      continue
    grown = _size(log)
    if grown != size:
      size, grewAt, said = grown, now, False
      continue
    quiet = now - grewAt
    if quiet >= LOG_QUIET_SECONDS:
      raise LinkTimeout('nothing new in its log for %s while it loaded (%s)' % (_span(LOG_QUIET_SECONDS), log))
    if quiet >= LOG_QUIET_SAY_SECONDS and not said:
      said = True
      say("the game's log has had nothing new for %s while it loads its mods (%s); at %s it is given up" % (
        _span(LOG_QUIET_SAY_SECONDS), log, _span(LOG_QUIET_SECONDS)))


def _stderr(line: str) -> None:
  print('unitTAS: %s' % line, file=sys.stderr)
  sys.stderr.flush()


def _ready(launched: LaunchedGame, results: Optional[str] = None, say: Optional[Callable[[str], Any]] = None,
           meanwhile: Optional[Callable[[Connection], Any]] = None) -> Connection:
  """
  The game started and at its title screen ('ready'), its log watched
  while it loads (_awaitReady; 'say' for what the terminal is told,
  stderr by default); stopped again if it doesn't get there. 'meanwhile'
  is given the connection after the hello, while the game loads its mods:
  work of the run's own that then never stands between the ready and the
  run's first world (the no-world guard). The opening guard's first
  picture: the game as it came up (screenshots/opened.png in the results),
  evidence that it did.
  """
  connection = launched.start()
  try:
    if meanwhile is not None:
      meanwhile(connection)
    _awaitReady(connection, launched, say or _stderr)
  except BaseException:
    launched.stop()
    raise
  if results is not None:
    picture = os.path.join(results, 'screenshots', 'opened.png')
    os.makedirs(os.path.dirname(picture), exist_ok=True)
    try:
      connection.request('screenshot', {'file': picture}, timeout=60)
    except UnitTasError:  # a picture is evidence, not the run: its absence says it
      pass
  return connection


def _mappingsMeanwhile(launched: LaunchedGame, environ: dict, box: dict) -> Callable[[Connection], None]:
  """
  For _ready: the mappings loaded while the game loads its mods (a real
  client's may be downloaded first), into box['mappings'], or what kept
  them into box['problem'].
  """
  def load(connection: Connection) -> None:
    try:
      box['mappings'] = mappingsFor(connection, launched, environ)
    except Exception as error:  # reflection by readable names won't work: unitTAS's own trouble, said in the report
      box['problem'] = "a real client's readable names can't be had: %s" % _why(error)
  return load


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
  #  OK, or OK with its counts ('OK (skipped=1)'): skipped tests and expected failures are no failure
  return lines[-1] == 'OK' or lines[-1].startswith('OK (')


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


# ---------------------------------------------------------------- old saves


def findSaves(pristine: str) -> list:
  """The saves in a pristine folder: each folder in it that holds a level.dat, by name. UsageError if none."""
  if not os.path.isdir(pristine):
    raise UsageError('--saves %s: no such folder' % pristine)
  names = sorted(name for name in os.listdir(pristine) if os.path.isfile(os.path.join(pristine, name, 'level.dat')))
  if not names:
    raise UsageError('--saves %s: no saves in it (a save is a folder holding level.dat)' % pristine)
  return names


def savesIn(pristine: str, gameDir: str, results: str) -> list:
  """
  The pristine folder's saves into the game's saves/ as fresh copies; a
  copy of the same name already there goes into the results'
  saves-before-this-run/, never deleted (as unittas-oldsaves.sh has it).
  Their names.
  """
  names = findSaves(pristine)
  saves = os.path.join(gameDir, 'saves')
  os.makedirs(saves, exist_ok=True)
  for name in names:
    there = os.path.join(saves, name)
    if os.path.lexists(there):
      before = os.path.join(results, 'saves-before-this-run')
      os.makedirs(before, exist_ok=True)
      shutil.move(there, os.path.join(before, name))
    copyExactly(os.path.join(pristine, name), there)
  return names


def savesOut(names: list, gameDir: str, results: str) -> None:
  """After the run: the copies as the game left them, into the results' saves-after/."""
  after = os.path.join(results, 'saves-after')
  for name in names:
    there = os.path.join(gameDir, 'saves', name)
    if os.path.lexists(there):
      os.makedirs(after, exist_ok=True)
      shutil.move(there, os.path.join(after, name))


def runJava(spec: InstanceSpec, suites: list, results: str, out: TextIO, environ: dict,
            pristine: Optional[str] = None, gameFor: Optional[Callable] = None, watched: bool = False) -> int:
  """
  'unittas run --java': Java suites in the spec's game, by java.run, with
  its saves when given (Java's own save loop: TasRunner.runSaves). The
  Java runner's progress shown as it comes; its report is the run's.
  """
  saveNames = findSaves(pristine) if pristine else []

  def say(line: str) -> None:
    print('[%s] %s' % (time.strftime('%H:%M:%S'), line), file=out)
    out.flush()

  launched = (gameFor or globals()['gameFor'])(spec, results, 'game')
  try:
    connection = _ready(launched, results, say=say)
  except Exception as error:  # whatever kept the game from starting: no test has a result
    run = Run(None, '', results, say=say)
    run.problem('unitTAS.game', "the game didn't start: %s" % _said(error))
    _show(out, run.writeReport())
    return 1
  progress = os.path.join(results, 'progress.txt')
  shown = [0]

  def follow() -> None:
    """The Java runner's progress lines, each once, as they come."""
    try:
      with open(progress, encoding='utf-8', errors='replace') as file:
        lines = file.read().split('\n')[:-1]
    except OSError:
      return
    for line in lines[shown[0]:]:
      say(line)
    shown[0] = len(lines)

  copied = []
  interrupted = False
  failure = None
  pending = None
  try:
    if pristine:
      copied = savesIn(pristine, launched.gameDir, results)
    args = {'suites': suites, 'results': results, 'watched': bool(watched or environ.get('UNITTAS_WATCHED') == '1'),
            'watch_pictures': int(environ.get('UNITTAS_PICTURE_SECONDS', '10')),
            'watch_decide': int(environ.get('UNITTAS_DECIDE_SECONDS', '300'))}
    if copied:
      args.update(saves=copied, oldsaves=os.path.abspath(pristine))
    pending = connection.send('java.run', args)
    while True:
      try:
        pending.result(0.5)
        break
      except LinkTimeout:
        follow()
  except KeyboardInterrupt:
    interrupted = True
    if pending is not None:
      try:
        #  as the watch's stop: the test running now, none after it; the Java runner writes its report
        connection.cancel(pending)
        pending.result(120)
      except Exception:  # cancelled, or past answering: the game is stopped below either way
        pass
  except Exception as error:  # java.run refused, or the game went: said in the report if the runner wrote none
    failure = _said(error)
  finally:
    follow()
    try:
      connection.request('quit', {'reason': 'the Java run is done'}, timeout=10)
    except Exception:  # stuck or gone: the stop below ends it
      pass
    launched.stop()
    if copied:
      savesOut(copied, launched.gameDir, results)
  report = os.path.join(results, 'report.txt')
  if not os.path.isfile(report):
    run = Run(None, '', results)
    run.problem('unitTAS.java', 'java.run gave no report: %s' % (failure or 'stopped by Ctrl+C'))
    report = run.writeReport()
  passed = _show(out, report)
  return 130 if interrupted else (0 if passed else 1)


def multiplayerFor(spec: InstanceSpec, run: Run, results: str, launched: LaunchedGame, environ: dict) -> Any:
  """
  The run's other games for its multiplayer classes (SPEC.md 11.3, step
  5), or None where a run can't hold them: real clients only (D1), each
  in a folder of its own in the results. The server gets the clients'
  mods but those the spec's [server] exclude names, the spec's EULA
  acceptance and memory, and the Gradle cache and the download cache.
  """
  if spec.client != 'real':
    return None
  from .launcher import Sources, findJava
  from .multiplayer import Multiplayer, megabytes
  from .servergame import ServerGame
  from .specgame import RealGame
  cache = getattr(launched, 'cache', None)
  gradleHome = (environ.get('UNITTAS_GRADLE_HOME') or environ.get('GRADLE_USER_HOME')
                or os.path.join(os.path.expanduser('~'), '.gradle'))

  def clientFor(name: str) -> Any:
    #  the run's own client built the spec's mods already: this one takes them as they are
    return RealGame(spec, results, 'client-' + name, cache=cache, folder=os.path.join(results, 'client-%s-game' % name),
                    username=name, built=True)

  def serverFor(players: tuple) -> Any:
    return ServerGame(spec.folder, results, 'server', folder=os.path.join(results, 'server-world'),
                      mods=launched.serverMods(), players=players, eula=spec.serverEula, memory=spec.serverMemory,
                      java=findJava(spec.java), sources=Sources(gradleHome=gradleHome, cache=cache))

  return Multiplayer(run, serverFor, clientFor, serverMb=megabytes(spec.serverMemory))


def runTests(spec: InstanceSpec, names: list, results: str, out: TextIO, cwd: str, environ: dict,
             gameFor: Optional[Callable] = None, watched: bool = False, pristine: Optional[str] = None,
             multiplayer: bool = False) -> int:
  """
  'unittas run': the tests on the spec's game, watched (watchFor), the
  report shown; with 'pristine', in save mode on its saves (runSaves). 0
  for OK, 1 for FAILED, 130 after Ctrl+C (the run ended properly all the
  same).
  """
  start = gameFor or globals()['gameFor']
  #  asked for by the flag or the variable alike (D4)
  multiplayer = bool(multiplayer) or environ.get('UNITTAS_MULTIPLAYER') == '1'
  if multiplayer:
    #  refused before anything starts (SPEC.md 11.6): real clients (D1), and the EULA the user accepted themselves
    if spec.client != 'real':
      raise UsageError('--multiplayer needs real clients, each with a folder of its own: %s says client = "%s", and '
                       'a multiplayer run needs client = "real"' % (spec.path, spec.client))
    if not spec.serverEula:
      raise UsageError("--multiplayer starts a dedicated server, which needs Mojang's EULA (https://aka.ms/MinecraftEULA)"
                       ' accepted, by you: say eula = true in the [server] table of %s' % spec.path)
  saveNames = findSaves(pristine) if pristine else []
  suite, problems = loadSuites(names, cwd)
  wanted = reportNames(suite)
  if saveNames:
    wanted = ['%s [%s, load %d]' % (name, folder, load) for load in (1, 2) for folder in saveNames for name in wanted]

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
  #  the saves in before the game starts: a big save's copy never stands between its ready and its first world
  copied = savesIn(pristine, launched.gameDir, results) if saveNames else []
  mapped = {}
  try:
    connection = _ready(launched, results, say=say, meanwhile=_mappingsMeanwhile(launched, environ, mapped))
  except Exception as error:  # whatever kept the game from starting: no test has a result
    if copied:
      savesOut(copied, launched.gameDir, results)
    _show(out, _unstarted(results, problems, wanted, _said(error)))
    return 1
  run = Run(Game(connection), launched.gameDir, results, stop=launched.stop, say=say)
  run.total = len(wanted)
  run.game.mappings = mapped.get('mappings')
  watch = watchFor(run, environ, watched)
  #  its multiplayer classes run only when asked for (D4), in a run that can hold them (D1)
  run.multiplayerAllowed = multiplayer
  run.multiplayer = globals()['multiplayerFor'](spec, run, results, launched, environ)
  if 'problem' in mapped:
    run.problem('unitTAS.mappings', mapped['problem'])
  for name, detail in problems:
    run.problem(name, detail)
  interrupted = False
  passedUnittest = True
  try:
    if saveNames:
      with open(os.path.join(results, 'unittest.txt'), 'w', encoding='utf-8') as log:
        runSaves(run, names, copied, os.path.abspath(pristine), stream=log, verbosity=2, start=cwd)
    else:
      try:
        run.begin()
      except Exception as error:  # the run's world or its plugins' beforeRun: nothing after it has a result
        why = "the run couldn't begin: %s" % run.whyText(error)
        run.problem('unitTAS.run', why)
        if run.stopped is None:
          run.stopped = why
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
    if copied:
      savesOut(copied, launched.gameDir, results)
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
    connection = _ready(launched, results, say=lambda line: print(line, file=out, flush=True))
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
  mapped = {}
  try:
    connection = _ready(launched, results, meanwhile=_mappingsMeanwhile(launched, environ, mapped))
  except Exception as error:  # whatever kept the game from starting
    _auto['failed'] = "the game didn't start: %s (its output: %s)" % (_said(error), results)
    raise NoResult(_auto['failed']) from error
  run = Run(Game(connection), launched.gameDir, results, stop=launched.stop)
  run.game.mappings = mapped.get('mappings')
  _auto.update(run=run, launched=launched, watch=watchFor(run, environ))
  run.multiplayerAllowed = environ.get('UNITTAS_MULTIPLAYER') == '1'
  run.multiplayer = globals()['multiplayerFor'](spec, run, results, launched, environ)
  Run.current = run
  atexit.register(_atExit)
  if 'problem' in mapped:
    run.problem('unitTAS.mappings', mapped['problem'])
  try:
    run.begin()
  except Exception as error:  # nothing after it has a result
    why = "the run couldn't begin: %s" % run.whyText(error)
    run.problem('unitTAS.run', why)
    if run.stopped is None:
      run.stopped = why
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

"""
The 'run' module is a run's lifecycle (SPEC.md 9.3, step 6a), today's four
levels owned in Python, in PROTOCOL.md section 13's order:

- the run: beforeRun; the test world made (saves/unittas) and given the
  steady settings (world.prepare, the Java runner's own), closed, kept
  aside exactly as made, opened again;
- each class: its world, the kept one put back (tearDownWorld, closed, the
  copy over it exactly, opened, setUpWorld) unless it shares the one before
  it; then a reset, for its setUpClass;
- each test: a reset and an event mark before it, refs.clear after it, and
  its line in the report;
- the end: tearDownWorld, afterRun, quit.

The report is report.txt in the Java report's shape (SPEC.md 9.6, decision
9): a line per test, the world line before each class's first, the text
under each that didn't pass, its screenshot, the chat during a failure,
the counts. So bin/compare_reports.py and the self-red checker read both.

- Run: one run on one game.
- RunResult: the result suites run with, which writes unittest's class
  fixtures into the report as the Java report has them.
- loadSuites: the tests by unittest's names, or discovered; reportNames
  the report's names for them.
- runSuite, runSuites: a loaded suite, or suites by name, run on a Run.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import importlib
import os
import re
import sys
import time
import traceback
import unittest
from typing import TYPE_CHECKING

from worktoy.ezdata import EZData, EZField

from .errors import NO_RESULT_ERRORS, LinkError, NoResult, NotReady, UnitTasError, whyNoResult
from .gamefiles import copyExactly, removeTree
from .reset import reset

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Callable, Optional

  from .api import Game

#  The test world's folder in the game's saves, as the Java runner's (Worlds.FOLDER).
FOLDER = 'unittas'
DASHES = '-' * 70
#  The report's outcome words, in the order its counts line gives them.
COUNTED = (('FAIL', 'failures'), ('ERROR', 'errors'), ('skipped', 'skipped'), ('expected failure', 'expected failures'),
           ('unexpected success', 'unexpected successes'), ('NO RESULT', 'no results'), ('problem', 'problems'))
FAILING = ('FAIL', 'ERROR', 'unexpected success', 'NO RESULT', 'problem')
#  A test whose verdict was never reached (SPEC.md 9.8): the game stuck, gone, or past a wall-clock guard.
NO_RESULT = 'NO RESULT'
#  Save mode, as the Java runner's (TasRunner.SAVE_SETTLE_TICKS): client ticks for a save's world to settle in.
SAVE_SETTLE_TICKS = 60


class OpenSave(EZData, frozen=True):
  """
  The save a run in save mode has open, as TasSave has it: its folder,
  which load (1: as found, 2: after this game saved it), its pristine copy
  and building list (empty when the run named no pristine folder), what was
  logged while it loaded ('[logger] message (thrown)'), and how long it took.
  """
  folder = EZField[str]('')
  load = EZField[int](1)
  pristine = EZField[str]('')
  buildings = EZField[str]('')
  loadErrors = EZField[tuple]()
  loadWarnings = EZField[tuple]()
  loadSeconds = EZField[float](0.0)


def _logged(line) -> str:
  """A log line as TasLogErrors words one: '[logger] message (thrown)', the message cut at 200."""
  message = line.message if len(line.message) <= 200 else line.message[:200] + '...'
  return '[%s] %s%s' % (line.logger, message, ' (%s)' % line.thrownText if line.thrownText else '')


class _Line:
  """One line of the report, and what goes under it."""

  def __init__(self, name: str, outcome: str, seconds: float, detail: str, chat: tuple, screenshot: Optional[str],
               worldNote: Optional[str]) -> None:
    self.name = name
    self.outcome = outcome
    self.seconds = seconds
    self.detail = detail
    self.chat = chat
    self.screenshot = screenshot
    self.worldNote = worldNote


class Run:
  """
  One run on one game ('game', a unittas.api.Game). 'gameDir' is the
  game's folder (its saves), 'results' the run's folder (report.txt,
  screenshots/). 'stop' ends the game after the quit, if the caller
  launched it (a LaunchedGame's stop). 'say' is given each line of the
  run's progress (progress.txt): each report line as it is added, a world
  line before its class's first, the watch's alarms.
  """

  current: Optional[Run] = None

  def __init__(self, game: Game, gameDir: str, results: str, stop: Optional[Callable[[], Any]] = None,
               say: Optional[Callable[[str], Any]] = None) -> None:
    self.game = game
    self.say = say
    #  the run's watch (unittas.watch, which sets it), or None: then no time limit and no alarms
    self.watch = None
    #  how many tests the run has, when known (for 'test 3/40')
    self.total = 0
    #  the test running: its number (from 1), whether one is between its reset and its line, why it was stopped
    self.testNumber = 0
    self.inTest = False
    self.testStopped = None
    #  the progress's count, as the Java runner's: each test's line one more, a failed setUpClass its tests' worth
    self.counted = 0
    #  tests a failed setUpClass's line accounts for: counted there, never given a line of their own
    self.covered = set()
    #  save mode (runSaves): the saves are the worlds, so no fresh ones, no resets, no world hooks; the save open, and
    #  the suffix its lines are named with (' [folder, load N]')
    self.saveMode = False
    self.save = None
    self.suffix = ''
    self.gameDir = gameDir
    self.results = results
    self.stop = stop
    self.lines = []
    self.worldNumber = 0
    self.worldNote = None
    self.lastClass = None
    self.started = time.monotonic()
    self.begun = False
    #  whether a world has been asked for yet (world.create or world.open sent): the watch's no-world guard waits on it
    self.worldAsked = False
    self.finished = False
    #  why no more test results can be had, or None while they can
    self.stopped = None
    #  a no result whose game may yet tick again: checked before the next test (SPEC.md 9.8)
    self.suspect = None

  # ---------------------------------------------------------------- where the world is

  def worldFolder(self) -> str:
    return os.path.join(self.gameDir, 'saves', FOLDER)

  def keptFolder(self) -> str:
    """The world as made, in the game's own folder, not among its saves (as the Java runner keeps it)."""
    return os.path.join(self.gameDir, 'unittas', 'world.pristine')

  def whyNoResult(self, error: BaseException) -> str:
    """Why an error leaves no result, in words: a connection that ended after the game's crash names the crash."""
    crash = None if self.game is None else getattr(self.game, 'crashed', None)
    if crash is not None and isinstance(error, LinkError):
      return 'the game crashed: %s (its crash report: %s)' % (crash['summary'], crash['report'] or 'none was saved')
    return whyNoResult(error)

  def whyText(self, error: BaseException) -> str:
    """What went wrong, in words, once: a NoResult's reason, a no-result error's why, anything else as it says it."""
    if isinstance(error, NoResult):
      return error.why
    if isinstance(error, NO_RESULT_ERRORS):
      return self.whyNoResult(error)
    if isinstance(error, UnitTasError):
      return str(error)
    return '%s: %s' % (type(error).__name__, error)

  # ---------------------------------------------------------------- the run

  def begin(self) -> None:
    """beforeRun, then the test world made, prepared, closed, kept aside as made, and opened again."""
    self.begun = True
    # an earlier run's test world goes first, that folder only, as the Java runner's does (world.create makes a new one)
    if os.path.lexists(self.worldFolder()):
      removeTree(self.worldFolder())
    self.game.request('hooks.run', {'hook': 'beforeRun'})
    self._load('world.create', {'folder': FOLDER})
    self.game.request('world.prepare')
    self.game.request('world.close', timeout=240)
    copyExactly(self.worldFolder(), self.keptFolder())
    self._load('world.open', {'folder': FOLDER})
    self.worldNumber = 1

  def enterClass(self, name: str, shared: bool = False) -> None:
    """
    A class's world: the one before it shared, or the kept one put back;
    then a reset, for its setUpClass. In save mode, the save as it is.
    """
    if self.saveMode:
      self.lastClass = name
      return
    if self.lastClass is None:
      self.game.request('hooks.run', {'hook': 'setUpWorld'})
      self.worldNote = 'world 1: the run\'s first, for %s' % name
    elif shared:
      self.worldNote = 'world %d, shared: %s runs in it as %s left it' % (self.worldNumber, name, self.lastClass)
    else:
      started = time.monotonic()
      self.game.request('hooks.run', {'hook': 'tearDownWorld'})
      self.game.request('world.close', timeout=240)
      copyExactly(self.keptFolder(), self.worldFolder())
      self._load('world.open', {'folder': FOLDER})
      self.game.request('hooks.run', {'hook': 'setUpWorld'})
      self.worldNumber += 1
      self.worldNote = 'world %d: fresh for %s (the kept world put back, opened in %.1f s)' % (
        self.worldNumber, name, time.monotonic() - started)
    self.lastClass = name
    reset(self.game.connection)

  def _load(self, op: str, args: dict, what: str = 'the test world') -> Any:
    """
    A world made or opened. Unwatched, by world.open's own limit (180 s:
    TimedOut, no result). Watched, the watch judges it (Watch.guardLoad):
    an alarm after a minute, and the watcher's answer. The probe's opening
    guard pictures a dropped login into the run's screenshots/ and opens it
    again; its warning goes into the progress. A world that doesn't open is
    no result (NoResult), whatever the game said: it is no test's verdict.
    A run already stopped (the watch's no-world guard) asks for none.
    """
    if self.stopped is not None:
      raise NoResult(self.stopped)
    self.worldAsked = True
    pictures = os.path.join(self.results, 'screenshots')
    os.makedirs(pictures, exist_ok=True)
    args = dict(args, pictures=pictures)
    try:
      if self.watch is None or not self.watch.watched:
        pending = self.game.connection.send(op, args)
        value = pending.result(240)
      else:
        pending = self.game.connection.send(op, dict(args, max_seconds=3600))
        value = self.watch.guardLoad(pending, what)
    except NO_RESULT_ERRORS:
      raise
    except NoResult:
      raise
    except UnitTasError as error:
      raise NoResult("%s didn't open: %s" % (what, error)) from error
    for warning in pending.warnings:
      self.progress('%s: %s' % (what, warning))
    return value

  # ---------------------------------------------------------------- save mode

  def beginSaves(self) -> None:
    """Save mode's start: beforeRun, and no test world (the saves are the worlds)."""
    self.begun = True
    self.saveMode = True
    self.game.request('hooks.run', {'hook': 'beforeRun'})

  def openSave(self, folder: str, load: int, pristine: Optional[str] = None) -> Optional[str]:
    """
    Opens the save (load 1: as found, 2: as this game saved it) and lets it
    settle; self.save is it then, with the log's errors and warnings from
    the asking to the settled world. None, or what went wrong.
    """
    self.progress('opening %s %s' % (folder, 'as it was found' if load == 1 else 'again, as this game saved it'))
    mark = self.game.mark()
    started = time.monotonic()
    try:
      self._load('world.open', {'folder': folder}, folder)
      self.game.ticks(SAVE_SETTLE_TICKS)
    except NoResult as error:
      return "couldn't open %s: %s" % (folder, error.why)
    except NO_RESULT_ERRORS as error:
      return "couldn't open %s: %s" % (folder, self.whyNoResult(error))
    except UnitTasError as error:
      return "couldn't open %s: %s" % (folder, error)
    seconds = time.monotonic() - started
    logged = self.game.logs(mark)
    self.save = OpenSave(
      folder=folder, load=load, pristine=os.path.join(pristine, folder) if pristine else '',
      buildings=os.path.join(pristine, folder + '.buildings') if pristine else '',
      loadErrors=tuple(_logged(line) for line in logged if line.level in ('ERROR', 'FATAL')),
      loadWarnings=tuple(_logged(line) for line in logged if line.level == 'WARN'), loadSeconds=seconds)
    self.progress('%s loaded in %.0f s' % (folder, seconds))
    return None

  def closeSave(self) -> Optional[str]:
    """Saves and leaves the open save, back to the title screen; None, or what went wrong."""
    self.save = None
    try:
      self.game.request('world.close', timeout=240)
    except NotReady:
      #  no world open: it never opened
      return None
    except NO_RESULT_ERRORS as error:
      return "the save didn't close: %s" % self.whyNoResult(error)
    except UnitTasError as error:
      return "the save didn't close: %s" % error
    return None

  def beforeTest(self, name: Optional[str] = None, limit: Optional[int] = None) -> int:
    """
    The reset before a test, and the mark its events are read from. After a
    no result, the game is checked first: a client tick, by the probe's stall
    rule. It ticks: the run goes on. It doesn't, or it's gone: the run stops,
    and this test and every one after it is not run (NoResult). 'name' and
    'limit' (its time limit, seconds) are for the watch.
    """
    self.testNumber += 1
    self.testStopped = None
    self.game.resume()
    if self.stopped is not None:
      raise NoResult('not run: no test result could be obtained after %s' % self.stopped)
    if self.suspect is not None:
      try:
        self.game.request('ticks.wait', {'side': 'client', 'n': 1})
      except NO_RESULT_ERRORS as error:
        then = self.whyNoResult(error)
        self.stopped = self.suspect if then == self.suspect else '%s; and then: %s' % (self.suspect, then)
        raise NoResult('not run: no test result could be obtained after %s' % self.stopped) from error
      self.suspect = None
    if not self.saveMode:
      reset(self.game.connection)
    mark = self.game.mark()
    self.inTest = True
    if self.watch is not None:
      self.watch.testBegan(self.testNumber, name or 'test %d' % self.testNumber, limit)
    return mark

  def _testOver(self) -> None:
    self.inTest = False
    if self.watch is not None:
      self.watch.testEnded()

  def stopTest(self, number: int, why: str) -> None:
    """
    Stops the test with that number, if it is still running (its time limit,
    the watcher): no result, and why. What it waits on is cancelled, and its
    requests are refused from then on (Game.stop).
    """
    if self.inTest and self.testNumber == number and self.testStopped is None:
      self.testStopped = why
      self.progress('%s: stopped, %s' % ('test %d' % number, why))
      self.game.stop(why)

  def abort(self, why: str) -> None:
    """The run stops (the watcher's abort): the test running is stopped, and every one after it is not run."""
    if self.stopped is None:
      self.stopped = why
    if self.inTest:
      self.stopTest(self.testNumber, why)

  def progress(self, line: str) -> None:
    """A line of the run as it goes: progress.txt in the results, and the terminal ('say')."""
    os.makedirs(self.results, exist_ok=True)
    with open(os.path.join(self.results, 'progress.txt'), 'a', encoding='utf-8') as file:
      file.write(line + '\n')
    if self.say is not None:
      self.say(line)

  def shout(self, line: str) -> None:
    """A line nobody may miss: the progress, and the terminal even when the run has none (plain unittest's: stderr)."""
    self.progress(line)
    if self.say is None:
      print('unitTAS: %s' % line, file=sys.stderr)
      sys.stderr.flush()

  def picture(self, name: str) -> Optional[str]:
    """A screenshot of the game as it is now, for a test that didn't pass: its path in the results, or None."""
    path = os.path.join(self.results, 'screenshots', name + '.png')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
      self.game.request('screenshot', {'file': path})
      return path
    except Exception:  # a picture is evidence, not the test: its failure is no failure of the test
      return None

  def afterTest(self, name: str, outcome: str, seconds: float, detail: str, mark: int,
                screenshot: Optional[str] = None) -> None:
    """refs.clear, and the test's line in the report (outcome as the report words it: ok, FAIL, ERROR, ...)."""
    self._testOver()
    try:
      self.game.request('refs.clear')
    finally:
      chat = tuple(line.plain for line in self.game.chat(mark)) if outcome in ('FAIL', 'ERROR') else ()
      self._add(_Line(name, outcome, seconds, detail, chat, screenshot, self.worldNote))

  def noResult(self, name: str, why: str, seconds: float = 0.0, suspect: bool = True) -> None:
    """
    A test with no result: its line says why. The game is checked before
    the next test (beforeTest), unless it isn't 'suspect' (a test stopped by
    its time limit or the watcher, in a game that was ticking).
    """
    self._testOver()
    if suspect and self.stopped is None and self.suspect is None:
      self.suspect = why
    self._add(_Line(name, NO_RESULT, seconds, why, (), None, self.worldNote))

  def fixture(self, name: str, outcome: str, detail: str, seconds: float = 0.0, notRun: tuple = ()) -> None:
    """
    A class fixture's line (setUpClass, tearDownClass) or a line for a test
    it kept from running; 'notRun' names the tests it kept from running,
    which its line accounts for (notRun gives them no line of their own).
    """
    self.covered.update(notRun)
    self._add(_Line(name, outcome, seconds, detail, (), None, self.worldNote), len(notRun))

  def problem(self, name: str, detail: str) -> None:
    """unitTAS's own trouble, outside any test: a problem line, which fails the run."""
    self._add(_Line(name, 'problem', 0.0, detail, (), None, None))

  def notRun(self, names: list, why: str) -> None:
    """A NO RESULT line, saying why, for each of these tests that has no line yet: those a stopped run never reached."""
    done = set(line.name for line in self.lines) | self.covered
    for name in names:
      if name not in done:
        self.noResult(name, why)

  def _add(self, line: _Line, notRun: int = 0) -> None:
    """
    The line into the report, and into the progress as the Java runner's
    has it: 'test N/M Class.method ... outcome', a world line before its
    class's first, a problem as what it says.
    """
    self.lines.append(line)
    if line.outcome == 'problem':
      #  a problem line never carries the world line: that stays for the class's first test
      self.progress(line.detail.split('\n')[0] if line.detail else line.name)
      return
    self.worldNote = None
    if line.worldNote:
      self.progress(line.worldNote)
    if not _FIXTURE_NAME.search(line.name):
      self.counted += 1
    self.counted += notRun
    count = '%d/%d' % (self.counted, self.total) if self.total else '%d' % self.counted
    self.progress('test %s %s ... %s' % (count, line.name, line.outcome))

  def finish(self) -> str:
    """tearDownWorld, afterRun, quit; then the report, whose path this returns."""
    if not self.finished:
      self.finished = True
      try:
        if self.stopped is None:
          if self.begun:
            if not self.saveMode:
              self.game.request('hooks.run', {'hook': 'tearDownWorld'})
            self.game.request('hooks.run', {'hook': 'afterRun'})
          self.game.request('quit', {'reason': 'the run is done'})
        else:
          #  a game that stopped ticking, or went: asked to quit if it still can be, nothing more (a game the run
          #  stopped refuses requests: the quit is the run's own)
          self.game.resume()
          try:
            self.game.request('quit', {'reason': 'no test result could be had: %s' % self.stopped}, timeout=10)
          except Exception:  # it is stuck or gone: the stop below ends it
            pass
      finally:
        if self.stop is not None:
          self.stop()
        # the kept copy is the run's own, and goes with it
        if os.path.lexists(self.keptFolder()):
          removeTree(self.keptFolder())
    return self.writeReport()

  # ---------------------------------------------------------------- the report

  def writeReport(self) -> str:
    out = ['unitTAS report, %s' % time.strftime('%Y-%m-%d %H:%M:%S')]
    none = [line for line in self.lines if line.outcome == NO_RESULT]
    if none:
      #  said first, before any line: these tests have no verdict at all
      out.append('NO TEST RESULT could be obtained for %d %s: %s' % (
        len(none), 'test' if len(none) == 1 else 'tests', none[0].detail))
    out.append('')
    counts = {word: 0 for word, _ in COUNTED}
    tests = 0
    for line in self.lines:
      if line.worldNote:
        out.append(line.worldNote)
      out.append('%s ... %s (%.1f s)' % (line.name, line.outcome, line.seconds))
      if line.outcome in counts:
        counts[line.outcome] += 1
      if line.outcome != 'problem':
        tests += 1
      if line.outcome != 'ok' and line.detail:
        out.extend('    ' + each for each in line.detail.split('\n'))
      if line.screenshot:
        out.append('    screenshot: ' + os.path.relpath(line.screenshot, self.results))
      if line.outcome in ('FAIL', 'ERROR'):
        out.append('    chat during the test:')
        out.extend('      | ' + each for each in line.chat)
    out.append(DASHES)
    problems = counts['problem']
    out.append('Ran %d %s in %.1f s%s' % (tests, 'test' if tests == 1 else 'tests', time.monotonic() - self.started,
                                          ', %d problem%s outside them' % (problems, '' if problems == 1 else 's')
                                          if problems else ''))
    out.append('')
    within = ', '.join('%s=%d' % (label, counts[word]) for word, label in COUNTED if counts[word])
    passed = not any(counts[word] for word in FAILING)
    out.append(('OK' if passed else 'FAILED') + (' (%s)' % within if within else ''))
    os.makedirs(self.results, exist_ok=True)
    path = os.path.join(self.results, 'report.txt')
    with open(path, 'w', encoding='utf-8') as file:
      file.write('\n'.join(out) + '\n')
    return path


# ---------------------------------------------------------------- suites on a run

_FIXTURE = re.compile(r'^(setUpClass|tearDownClass|setUpModule|tearDownModule) \((.+)\)$')
#  A report line's name that is a fixture's, not a test's (Class.setUpClass): not counted as a test in the progress.
_FIXTURE_NAME = re.compile(r'\.(setUpClass|tearDownClass|setUpModule|tearDownModule)$')


def _exceptionText(error: tuple) -> str:
  return ''.join(traceback.format_exception(*error)).rstrip()


class RunResult(unittest.TextTestResult):
  """
  The result suites run with on a Run: unittest's own, and the class
  fixtures in the run's report too, as the Java report has them (each test's
  line is GameTestCase's). A setUpClass that fails is one ERROR line, its
  tests not run; a skip in setUpClass a skipped line for each of its tests;
  a tearDownClass that fails an ERROR line of its own. One that met a stuck
  or vanished game is NO RESULT (SPEC.md 9.8), and so are the tests it kept
  from running.
  """

  run: Optional[Run] = None
  classTests: dict = {}

  def _fixture(self, test: Any):
    found = _FIXTURE.match(getattr(test, 'description', '') or '')
    if not found or self.run is None:
      return None
    return found.group(1), found.group(2).rsplit('.', 1)[-1]

  def addError(self, test: Any, error: tuple) -> None:
    super().addError(test, error)
    fixture = self._fixture(test)
    if fixture is None:
      return
    which, className = fixture
    tests = self.classTests.get(className, [])
    if isinstance(error[1], NoResult):
      #  GameTestCase has given each of the class's tests its NO RESULT line already
      return
    if isinstance(error[1], NO_RESULT_ERRORS):
      why = self.run.whyNoResult(error[1])
      self.run.noResult('%s.%s%s' % (className, which, self.run.suffix), why)
      if which == 'setUpClass':
        for name in tests:
          self.run.noResult('%s.%s%s' % (className, name, self.run.suffix),
                            'not run: no test result could be obtained (%s)' % why)
      return
    detail = _exceptionText(error)
    notRun = tuple('%s.%s%s' % (className, name, self.run.suffix) for name in tests) if which == 'setUpClass' else ()
    if notRun:
      detail += '\n(its %d test%s not run)' % (len(notRun), '' if len(notRun) == 1 else 's')
    self.run.fixture('%s.%s%s' % (className, which, self.run.suffix), 'ERROR', detail, notRun=notRun)

  def addSkip(self, test: Any, reason: str) -> None:
    super().addSkip(test, reason)
    fixture = self._fixture(test)
    if fixture is None:
      return
    which, className = fixture
    for name in self.classTests.get(className, []):
      self.run.fixture('%s.%s%s' % (className, name, self.run.suffix), 'skipped', '%s: %s' % (which, reason))


def _tests(suite: unittest.TestSuite) -> list:
  out = []
  for item in suite:
    if isinstance(item, unittest.TestSuite):
      out.extend(_tests(item))
    else:
      out.append(item)
  return out


def _named(loader: unittest.TestLoader, name: str) -> tuple:
  """
  The tests a name names (a module, a class in one, a test of a class), as
  (suite, None); or (None, the problem) when it names nothing to run.
  """
  parts = name.split('.')
  module = None
  for cut in range(len(parts), 0, -1):
    tried = '.'.join(parts[:cut])
    try:
      module = importlib.import_module(tried)
      break
    except ModuleNotFoundError as error:
      missing = error.name or ''
      if tried != missing and not tried.startswith(missing + '.'):
        #  the module is there, but something it imports isn't
        return None, "the suite %s can't be loaded: %s" % (tried, error)
    except Exception:  # its own code failed as it loaded
      return None, "the suite %s can't be loaded:\n%s" % (tried, _exceptionText(sys.exc_info()))
  if module is None:
    return None, "no suite called '%s' (no module of that name)" % name
  found, parent = module, None
  for part in parts[cut:]:
    if not hasattr(found, part):
      if hasattr(found, '__path__'):
        return None, "no suite called '%s' (no module of that name)" % name
      return None, "no test called '%s'" % name
    found, parent = getattr(found, part), found
  if found is module:
    return loader.loadTestsFromModule(module), None
  if isinstance(found, type) and issubclass(found, unittest.TestCase):
    return loader.loadTestsFromTestCase(found), None
  if callable(found) and isinstance(parent, type) and issubclass(parent, unittest.TestCase):
    return unittest.TestSuite([parent(parts[-1])]), None
  return None, "'%s' is no test: neither a module, a TestCase class nor a test of one" % name


def loadSuites(names: list, start: Optional[str] = None) -> tuple:
  """
  The tests to run, as (suite, problems): by unittest's names (a module,
  module.Class, module.Class.test), in the order given; or, with no names,
  discovered from 'start' (test*.py, as 'python -m unittest' finds them).
  Each problem is (name, detail) for the run's report: a suite that isn't
  there or can't be loaded. 'start' goes on the path first, as unittest
  has the current folder there.
  """
  loader = unittest.TestLoader()
  problems = []
  if start is not None and os.path.abspath(start) not in [os.path.abspath(each or '.') for each in sys.path]:
    sys.path.insert(0, os.path.abspath(start))
  if not names:
    discovered = loader.discover(os.path.abspath(start or '.'), pattern='test*.py', top_level_dir=os.path.abspath(
      start or '.'))
    for error in loader.errors:
      problems.append(('unitTAS.suites', "a suite can't be loaded:\n%s" % error.strip()))
    kept = [test for test in _tests(discovered) if type(test).__name__ != '_FailedTest']
    return unittest.TestSuite(kept), problems
  suites = []
  for name in names:
    suite, problem = _named(loader, name)
    if problem is not None:
      problems.append(('unitTAS.suites', problem))
    else:
      suites.append(suite)
  return unittest.TestSuite(suites), problems


def reportNames(suite: unittest.TestSuite) -> list:
  """The report's names of the suite's game tests (Class.test), in the order they run."""
  return [test.reportName() for test in _tests(suite) if hasattr(test, 'reportName')]


def runSuite(run: Run, suite: unittest.TestSuite, stream: Any = None, verbosity: int = 1) -> unittest.TestResult:
  """The suite on the run, with RunResult; Run.current is the run meanwhile (its total, if not known yet, the suite's)."""
  if not run.total:
    run.total = len(reportNames(suite))
  classTests = {}
  for test in _tests(suite):
    if isinstance(test, unittest.TestCase):
      classTests.setdefault(type(test).__name__, []).append(test._testMethodName)
  result = type('BoundRunResult', (RunResult,), {'run': run, 'classTests': classTests})
  previous = Run.current
  Run.current = run
  try:
    runner = unittest.TextTestRunner(stream=stream or sys.stderr, verbosity=verbosity, resultclass=result)
    return runner.run(suite)
  finally:
    Run.current = previous


def runSuites(run: Run, names: list, stream: Any = None, verbosity: int = 1) -> unittest.TestResult:
  """
  The suites by unittest's names (loadSuites) on the run: each in the order
  given, its classes and their tests in name order, as the Java runner
  sorts them, with RunResult. A suite that isn't there is a problem line,
  before any test.
  """
  suite, problems = loadSuites(names)
  for name, detail in problems:
    run.problem(name, detail)
  return runSuite(run, suite, stream=stream, verbosity=verbosity)


def runSaves(run: Run, names: list, saves: list, pristine: Optional[str] = None, stream: Any = None,
             verbosity: int = 1, start: Optional[str] = None) -> None:
  """
  Save mode (SPEC.md 9.3 step 9b), in the Java runner's order
  (TasRunner.runSaves): for each load (1: as found, 2: as this game saved
  it), each save opened and settled, the tests by their names run in it,
  loaded afresh each time, with no resets and no world hooks (they would
  change the save), each line named 'Class.test [folder, load N]'; then
  the save closed. A save that doesn't open is a problem line, and the run
  goes on with the next; one that doesn't close stops the run. A run that
  can't begin, or is stopped (the watch), ends here with its own why: the
  tests it never reached are the caller's to give their lines
  (Run.notRun).
  """
  suite, problems = loadSuites(names, start)
  for name, detail in problems:
    run.problem(name, detail)
  if not run.total:
    run.total = len(reportNames(suite)) * len(saves) * 2
  try:
    run.beginSaves()
  except Exception as error:  # beforeRun failed, or the run was stopped meanwhile: nothing after it has a result
    why = "the run couldn't begin: %s" % run.whyText(error)
    run.problem('unitTAS.run', why)
    if run.stopped is None:
      run.stopped = why
    return
  try:
    for load in (1, 2):
      for folder in saves:
        if run.stopped is not None:
          return
        run.suffix = ' [%s, load %d]' % (folder, load)
        problem = run.openSave(folder, load, pristine)
        if problem is not None:
          run.problem('unitTAS.openSave' + run.suffix, problem)
          if run.stopped is not None:
            #  stopped as it opened: no world to close, and the why stays the run's own
            return
        else:
          runSuite(run, loadSuites(names, start)[0], stream=stream, verbosity=verbosity)
        problem = run.closeSave()
        if problem is not None:
          run.problem('unitTAS.closeSave' + run.suffix, problem)
          run.stopped = problem
          return
  finally:
    run.suffix = ''

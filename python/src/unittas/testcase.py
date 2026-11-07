"""
The 'testcase' module holds GameTestCase (SPEC.md 9.3, step 6a): a plain
unittest.TestCase whose fixture is the game, with today's levels.

- The class: its world, the run's kept world put back for it, unless it
  says 'shared_world = True' (then it runs in the world the class before
  it left). A class that needs real terrain (a map, say) asks for a world
  of its own: 'world = {"type": "default", "seed": 1234}', world.create's
  own arguments; it is made fresh for the class, and the reset starts
  where the game put the player in it. A subclass's own setUpClass calls super().setUpClass() first,
  as unittest has it, and then runs in its world after a reset.
- Each test: a reset of the player before it and an event mark, whatever
  its own setUp does; refs.clear after it. A failure or an error is
  pictured before the next reset. Its line goes into the run's report.
  'timeout_seconds' (60) stops a test that never ends, with no result,
  where the run has a watch (unittas.watch; a watched run asks first).

No worktoy metaclass here, on purpose (PIVOT.md 5, 'Built on worktoy'):
unittest keeps every test class for the whole run, and a metaclass's state
can leak from one class into another. Everything a test touches,
'self.game' and its values, is the package's.

The run is Run.current: 'unittas run' makes it, and a test bench may set
it. Under plain 'python -m unittest' the first GameTestCase starts one
from the instance spec (UNITTAS_INSTANCE, or unittas.toml in the current
folder), ended at exit (unittas.session.autoRun).

- GameTestCase: the base of a mod's test classes.
- MultiplayerTestCase: one whose tests have a dedicated server and
  several clients (SPEC.md 11.3, step 5).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import sys
import time
import traceback
import unittest
from typing import TYPE_CHECKING

from .errors import NO_RESULT_ERRORS, NoResult
from .run import NO_RESULT, Run

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Optional

  from .api import Game

#  What stops a run at once, said as the reason its tests have no result.
CTRL_C = 'the run was stopped by Ctrl+C'


def _theRun() -> Run:
  """The run: 'unittas run's, or under plain unittest one started from the spec (unittas.session.autoRun)."""
  run = Run.current
  if run is None:
    from . import session
    run = session.autoRun()
  return run


def _said(error: tuple) -> str:
  """An exception as the report gives it: its line, and for an error the frames of the test and the game."""
  kind, value, trace = error
  return ''.join(traceback.format_exception(kind, value, trace)).rstrip()


def _failed(error: tuple) -> str:
  """An assertion as the report gives it: its message, and where in the test it was (not in unittest's own asserts)."""
  kind, value, trace = error
  frames = [frame for frame in traceback.extract_tb(trace) if os.sep + 'unittest' + os.sep not in frame.filename]
  where = frames[-1] if frames else None
  line = ''.join(traceback.format_exception_only(kind, value)).strip()
  return line if where is None else '%s\n  at %s:%d in %s' % (line, where.filename, where.lineno, where.name)


class _Recorder:
  """The result a test reports to, seen on the way: its outcome and what it said, the failure pictured first."""

  def __init__(self, result: unittest.TestResult, test: GameTestCase) -> None:
    self.__dict__['_result'] = result
    self.__dict__['_test'] = test
    self.__dict__['outcome'] = 'ok'
    self.__dict__['detail'] = ''
    self.__dict__['screenshot'] = None

  def __getattr__(self, name: str) -> Any:
    return getattr(self._result, name)

  def __setattr__(self, name: str, value: Any) -> None:
    setattr(self._result, name, value)

  def _note(self, outcome: str, detail: str) -> None:
    #  the first that didn't pass wins: a failing test whose tearDown also fails is a failure, as unittest counts it
    if self.__dict__['outcome'] in ('ok',):
      self.__dict__['outcome'] = outcome
      self.__dict__['detail'] = detail

  def _picture(self) -> None:
    if self.__dict__['screenshot'] is None:
      self.__dict__['screenshot'] = _theRun().picture(self._test.reportName())

  def addFailure(self, test: Any, error: tuple) -> None:
    self._picture()
    self._note('FAIL', _failed(error))
    self._result.addFailure(test, error)

  def addError(self, test: Any, error: tuple) -> None:
    if isinstance(error[1], NoResult):
      #  the test was stopped (its time limit, the watcher), or the run before it: no verdict, said as such
      self._note(NO_RESULT, error[1].why)
      self._result.addError(test, error)
      return
    if isinstance(error[1], NO_RESULT_ERRORS):
      #  no verdict at all (SPEC.md 9.8): said as such, to the report and to unittest; no picture of a stuck game
      why = _theRun().whyNoResult(error[1])
      self._note(NO_RESULT, why)
      self._result.addError(test, _noResultError(why, error[1]))
      return
    self._picture()
    self._note('ERROR', _said(error))
    self._result.addError(test, error)

  def addSkip(self, test: Any, reason: str) -> None:
    self._note('skipped', reason)
    self._result.addSkip(test, reason)

  def addExpectedFailure(self, test: Any, error: tuple) -> None:
    self._note('expected failure', _failed(error))
    self._result.addExpectedFailure(test, error)

  def addUnexpectedSuccess(self, test: Any) -> None:
    self._note('unexpected success', 'marked as an expected failure, but it passed: the mark can go')
    self._result.addUnexpectedSuccess(test)

  def addSubTest(self, test: Any, subtest: Any, error: Optional[tuple]) -> None:
    if error is not None:
      self._picture()
      failure = issubclass(error[0], test.failureException)
      self._note('FAIL' if failure else 'ERROR', ('%s\n' % subtest.id()) + (_failed(error) if failure else _said(error)))
    self._result.addSubTest(test, subtest, error)


def _noResultError(why: str, cause: Optional[BaseException] = None) -> tuple:
  """A NoResult as unittest takes an error: its exc_info, chained to what caused it."""
  try:
    raise NoResult(why) from cause
  except NoResult:
    return sys.exc_info()


class GameTestCase(unittest.TestCase):
  """
  A test class whose fixture is the game: 'self.game' (unittas.api.Game)
  and the helpers below. 'shared_world = True' runs the class in the world
  the class before it left, rather than a fresh one. 'world' (None: the
  run's own superflat world, which most tests are fine in) asks for a
  world of the class's own, by world.create's arguments ('type' default,
  flat, large_biomes or amplified, as the game version has them; 'seed';
  'generator'; 'game_mode'; 'cheats'; 'structures'; 'name'): made fresh
  for it, the player reset to where the game put it there.
  """

  shared_world = False
  world: Optional[dict] = None
  #  How long one test may take, by the clock, before it is stopped with no result (a watched run asks first): a guard
  #  for a test that never ends, as Java's timeoutSeconds(). Its verdict is never the clock's.
  timeout_seconds = 60
  game: Game = None

  @classmethod
  def setUpClass(cls) -> None:
    super().setUpClass()
    run = _theRun()
    cls.game = run.game
    if run.stopped is None:
      try:
        run.enterClass(cls.__name__, shared=bool(cls.shared_world), world=cls.world)
      except NoResult as error:
        #  the watcher gave up on the class's world, or aborted the run
        if run.stopped is None:
          run.stopped = error.why
      except NO_RESULT_ERRORS as error:
        #  the class's world couldn't be had
        run.stopped = run.whyNoResult(error)
    if run.stopped is not None:
      #  no test result can be had: each test of the class says so, and the class's own setUpClass doesn't go on to a
      #  game with no world (what it met there would be an ERROR, a verdict, which it isn't)
      cls._notRun(run, 'not run: no test result could be obtained after %s' % run.stopped)

  @classmethod
  def _notRun(cls, run: Run, why: str) -> None:
    """A NO RESULT line for each of the class's tests, saying why; then NoResult, which ends its setUpClass."""
    for name in unittest.TestLoader().getTestCaseNames(cls):
      run.noResult('%s.%s%s' % (cls.__name__, name, run.suffix), why)
    raise NoResult(why)

  # (MultiplayerTestCase is below, after the helpers it shares)

  def reportName(self) -> str:
    """The test as the report names it: Class.method, and in save mode its save ('Class.method [folder, load N]')."""
    run = Run.current
    return '%s.%s%s' % (type(self).__name__, self._testMethodName, run.suffix if run is not None else '')

  def run(self, result: Optional[unittest.TestResult] = None) -> Any:
    if result is None:
      return super().run(result)
    started = time.monotonic()
    run = Run.current
    try:
      run = _theRun()
      self.mark = run.beforeTest(self.reportName(), type(self).timeout_seconds)
    except NoResult as error:
      return self._noResult(result, run, error.why, started, error.__cause__)
    except NO_RESULT_ERRORS as error:
      return self._noResult(result, run, run.whyNoResult(error), started, error)
    except Exception:  # no run, or the reset failed (a mod's resetPlayer, say): the test's own error
      error = sys.exc_info()
      result.startTest(self)
      result.addError(self, error)
      result.stopTest(self)
      if Run.current is not None:
        Run.current.afterTest(self.reportName(), 'ERROR', time.monotonic() - started, _said(error), 0)
      return result
    recorder = _Recorder(result, self)
    interrupted = False
    try:
      return super().run(recorder)
    except KeyboardInterrupt:
      #  unittest lets Ctrl+C through, and the test never reached its verdict: no result, and the run stops
      interrupted = True
      if run.stopped is None:
        run.stopped = CTRL_C
      raise
    finally:
      seconds = time.monotonic() - started
      if interrupted:
        run.noResult(self.reportName(), 'stopped by Ctrl+C during the test', seconds)
      elif run.testStopped is not None:
        #  stopped by its time limit or the watcher, whatever it reported after that: no result, in a ticking game
        run.noResult(self.reportName(), run.testStopped, seconds, suspect=False)
      elif recorder.outcome == NO_RESULT:
        run.noResult(self.reportName(), recorder.detail, seconds)
      else:
        try:
          run.afterTest(self.reportName(), recorder.outcome, seconds, recorder.detail, self.mark,
                        screenshot=recorder.screenshot)
        except NO_RESULT_ERRORS as error:
          #  the game went after the verdict: the verdict is kept (its line is in), the run stops here
          run.stopped = run.whyNoResult(error)

  def _noResult(self, result: unittest.TestResult, run: Run, why: str, started: float,
                cause: Optional[BaseException] = None) -> unittest.TestResult:
    """This test has no result: to unittest a NoResult, to the report a NO RESULT line."""
    result.startTest(self)
    result.addError(self, _noResultError(why, cause))
    result.stopTest(self)
    if run is not None:
      run.noResult(self.reportName(), why, time.monotonic() - started)
    return result

  # ---------------------------------------------------------------- the game's everyday helpers

  def command(self, text: str, side: Optional[str] = None) -> Any:
    return self.game.command(text, side)

  def held(self, side: Optional[str] = None) -> Any:
    return self.game.held(side)

  def player(self, side: Optional[str] = None) -> Any:
    return self.game.player(side)

  def save(self) -> Any:
    """The save open, in save mode (unittas.run.OpenSave: its folder, load, pristine copy, buildings, load errors); else None."""
    return _theRun().save

  def worldNumber(self) -> int:
    """The world this test runs in, as the report numbers them: 1 for the run's first, one more for each fresh one."""
    return _theRun().worldNumber

  def chat(self) -> tuple:
    """The chat lines the client was shown during this test."""
    return self.game.chat(self.mark)

  def sounds(self) -> tuple:
    """The sounds the client was asked to play during this test."""
    return self.game.sounds(self.mark)


#  Why a multiplayer class didn't run, for its skipped lines (SPEC.md 11.6, D4 and D1).
MULTIPLAYER_ASK = ('a multiplayer class runs only when the run is asked for multiplayer: unittas run --multiplayer (or '
                   'UNITTAS_MULTIPLAYER=1). It starts a dedicated server and more clients, about 2 GB each')
MULTIPLAYER_REAL = ('a multiplayer class needs real clients, each with a folder of its own: its run\'s instance spec '
                    'says client = "real" for that (a development run\'s runClient has one folder)')


class MultiplayerTestCase(GameTestCase):
  """
  A test class whose fixture is several games (SPEC.md 11.3, step 5;
  PROTOCOL.md 9): 'clients' names them ('alice', 'bob'), the first the
  run's own client. 'self.server' is the dedicated server's Game, and
  each name is its client's ('self.alice', 'self.bob'); 'self.game' is the
  first. Each client's player has the name its game has
  (self.bob.playerName()). A fresh server world for each class unless
  'shared_world = True' (after another multiplayer class). Before each
  test the player is reset across the games. It runs only in a run asked
  for multiplayer, with real clients; otherwise its tests are skipped,
  saying why. Short of memory for the other games, its tests are NO
  RESULT, and the run goes on.
  """

  clients = ('alice', 'bob')
  server: Game = None

  @classmethod
  def setUpClass(cls) -> None:
    from .multiplayer import MemoryShort
    run = _theRun()
    cls.game = run.game
    if run.stopped is not None:
      cls._notRun(run, 'not run: no test result could be obtained after %s' % run.stopped)
    if cls.world is not None:
      raise TypeError("%s.world: a multiplayer class can't ask for a world of its own yet: its server's world is the "
                      "run's superflat one" % cls.__name__)
    if not run.multiplayerAllowed:
      raise unittest.SkipTest(MULTIPLAYER_ASK)
    if run.multiplayer is None:
      raise unittest.SkipTest(MULTIPLAYER_REAL)
    names = tuple(cls.clients)
    taken = set(dir(MultiplayerTestCase))
    for name in names:
      if not isinstance(name, str) or not name.isidentifier() or name.startswith('_') or name in taken:
        raise TypeError('%s.clients names its games: %r is no name a game can have here' % (cls.__name__, name))
    if not names or len(set(names)) != len(names):
      raise TypeError('%s.clients names one game or more, each once: %r' % (cls.__name__, names))
    try:
      games = run.enterMultiplayer(cls.__name__, names, shared=bool(cls.shared_world))
    except MemoryShort as error:
      #  this class's tests only: the run goes on with its others
      cls._notRun(run, 'not run: %s' % error)
    except NoResult as error:
      if run.stopped is None:
        run.stopped = error.why
      cls._notRun(run, 'not run: no test result could be obtained after %s' % run.stopped)
    except NO_RESULT_ERRORS as error:
      run.stopped = run.whyNoResult(error)
      cls._notRun(run, 'not run: no test result could be obtained after %s' % run.stopped)
    cls.server = games['server']
    for name in names:
      setattr(cls, name, games[name])
    cls.game = games[names[0]]

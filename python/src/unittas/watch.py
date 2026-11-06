"""
The 'watch' module is the run's eyes, for whoever watches it, most likely
an LLM (SPEC.md 9.3, step 8b; README.md, "Watching a run"), as the Java
runner's TasWatch has them, with the same files and words:

- always: watch.txt every few seconds (what the run is doing, the client
  and the server from the probe's heartbeat, the open alarm), and a live
  picture (screenshots/watch-live.png, the one before it watch-previous.png)
  while the client ticks;
- a test's time limit (GameTestCase.timeout_seconds): past it, the test is
  stopped, with no result;
- the no-world guard: a run that has asked for no world NO_WORLD_SAY_TICKS
  client ticks after the game was ready says so, and at NO_WORLD_TICKS it
  stops, every test with no result (the game stands at its title screen,
  and nothing is coming);
- in a watched run, where a fixed limit would decide (a test past its time
  limit, a test world that doesn't load), an alarm asks instead: alarm.txt
  says what it sees, with two pictures a few seconds apart (the threads,
  when the client doesn't tick), and the watcher answers in decision.txt:
  wait longer, fail, or abort the run. Without an answer in time, the run
  does what it does unwatched. Only whether the game is stuck is the
  watcher's call; whether a test passed never is.

Its clock and its sleep can be given, so a test bench can move time on.

- Decision: an alarm's answer.
- Watch: the watch of one run.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import re
import threading
import time
from typing import TYPE_CHECKING

from worktoy.ezdata import EZData, EZField

from .errors import LinkTimeout, NoResult

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Callable, Optional

  from .run import Run

#  How long the test world may load before a watched run asks (an unwatched one goes by world.open's own limit).
LOAD_SECONDS = 60
STATUS_SECONDS = 5
PICTURE_GAP_SECONDS = 3
REMIND_SECONDS = 60
#  How long the probe may be silent (no heartbeat) before watch.txt says so.
SILENT_SECONDS = 5
#  A client that ticked within this many seconds is ticking: a picture of it can be taken.
TICKING_SECONDS = 3
#  A malformed decision gets this long to be finished being written before it is taken as said.
WRITING_SECONDS = 2
#  The no-world guard (SPEC.md, after 9.8): client ticks from the game's ready (the first heartbeat the watch hears) with
#  no world asked for by the run, before it says so, and before the run stops with no results. Ticks, not seconds:
#  a slow machine ticks slower, so it is given the more time.
NO_WORLD_SAY_TICKS = 600
NO_WORLD_TICKS = 1200
NO_WORLD = 'no world began loading %d client ticks after the game was ready'
DECISION = re.compile(r'^\s*#?(\d+)?\s*(wait|fail|abort)\b\s*(.*)$', re.IGNORECASE)
WAIT, FAIL, ABORT, CLEARED, NO_ANSWER = 'wait', 'fail', 'abort', 'cleared', 'no answer'


class Decision(EZData, frozen=True):
  """
  The answer to an alarm: 'action' is wait, fail or abort (the watcher's),
  cleared (the situation passed by itself, or the run ended) or no answer
  (none in time). 'seconds' for a wait, 'why' for a fail or an abort.
  """
  alarm = EZField[int](0)
  action = EZField[str](CLEARED)
  seconds = EZField[int](0)
  why = EZField[str]('')


def _said(decision: Decision) -> str:
  if decision.action == WAIT:
    return 'wait %d s' % decision.seconds
  return decision.action + (': ' + decision.why if decision.why else '')


class Watch:
  """
  The watch of one run (it sets run.watch). 'watched': alarms ask before
  a fixed limit decides. 'pictures': seconds between live pictures (0 for
  none). 'decide': seconds an alarm waits for its answer. 'start' runs it
  on a thread of its own, a round a second; 'stop' ends it.
  """

  def __init__(self, run: Run, watched: bool = False, pictures: int = 10, decide: int = 300,
               clock: Callable[[], float] = time.time, sleep: Callable[[float], Any] = time.sleep) -> None:
    self.run = run
    self.watched = watched
    self.pictures = pictures
    self.decide = max(10, decide)
    self.clock = clock
    self.sleep = sleep
    self.results = run.results
    os.makedirs(os.path.join(self.results, 'screenshots'), exist_ok=True)
    run.watch = self
    #  the last heartbeat (the probe's tick event) and when it came, by this watch's clock
    self.beat = None
    self.heardAt = None
    #  the client's tick count in the first heartbeat heard, the game ready by then: the no-world guard counts from it
    self.readyClient = None
    self.noWorldSaid = False
    self.noWorldDone = False
    #  the test running: {'number', 'name', 'began', 'limit', 'deadline'}, or None
    self.test = None
    #  what is loading, and since when, or None
    self.loading = None
    self.loadingSince = 0.0
    self.alarms = 0
    self.openAlarm = 0
    self.alarmLock = threading.Lock()
    self.lastPicture = 'none yet'
    self.nextPicture = clock() + pictures
    self.nextStatus = clock()
    self.malformed = None
    self.ended = threading.Event()
    self.thread = None

  # ---------------------------------------------------------------- the run tells it

  def start(self) -> None:
    """The heartbeat listened to, and a round a second on the watch's own thread, until stop."""
    self.run.game.connection.events.subscribe(self.heard)
    self.thread = threading.Thread(target=self._loop, name='unittas watch', daemon=True)
    self.thread.start()

  def stop(self) -> None:
    self.ended.set()
    if self.thread is not None and self.thread is not threading.current_thread():
      self.thread.join(30)

  def heard(self, event: dict) -> None:
    """An event from the game: the heartbeat kept."""
    if event.get('event') == 'tick':
      if self.readyClient is None and event.get('client') is not None:
        self.readyClient = event['client']
      self.beat = event
      self.heardAt = self.clock()

  def testBegan(self, number: int, name: str, limit: Optional[int]) -> None:
    now = self.clock()
    self.test = {'number': number, 'name': name, 'began': now, 'limit': limit,
                 'deadline': now + limit if limit else None}

  def testEnded(self) -> None:
    self.test = None

  # ---------------------------------------------------------------- the rounds

  def _loop(self) -> None:
    while not self.ended.is_set():
      try:
        self.round()
      except Exception as error:  # a round that failed is the watch's trouble, never the run's
        self._log('a round failed: %r' % error)
      self.ended.wait(1.0)

  def round(self) -> None:
    """
    One round: watch.txt and the live picture when due; no world yet, said
    or the run stopped; a test past its time limit stopped, or asked about.
    """
    self.housekeeping()
    self._noWorld()
    test = self.test
    if test is not None and test['deadline'] is not None and self.clock() >= test['deadline']:
      self._overTime(test)

  def housekeeping(self) -> None:
    now = self.clock()
    if self.pictures > 0 and now >= self.nextPicture:
      self.nextPicture = now + self.pictures
      self._livePicture()
    if now >= self.nextStatus:
      self.nextStatus = now + STATUS_SECONDS
      self._writeStatus()

  def _ticksWithNoWorld(self) -> Optional[int]:
    """The client ticks since the game was ready, while the run has asked for no world yet; None otherwise."""
    if self.run.worldAsked or self.readyClient is None or self.beat is None:
      return None
    client = self.beat.get('client')
    return None if client is None else client - self.readyClient

  def _noWorld(self) -> None:
    """
    The no-world guard, from the watch's own thread, so a run held up
    anywhere can't hide it: said at NO_WORLD_SAY_TICKS; at NO_WORLD_TICKS
    the run stops, what it waits on in the game cancelled, its requests
    refused from then on (Game.stop), so no world is asked for after it.
    """
    ticks = self._ticksWithNoWorld()
    if ticks is None or self.noWorldDone or self.run.stopped is not None:
      return
    if ticks >= NO_WORLD_TICKS:
      self.noWorldDone = True
      why = NO_WORLD % NO_WORLD_TICKS
      self._log('no world: %s' % why)
      self.run.shout('NO WORLD: %s: the run stops, and no test has a result' % why)
      self.run.abort(why)
      self.run.game.stop(why)
    elif ticks >= NO_WORLD_SAY_TICKS and not self.noWorldSaid:
      self.noWorldSaid = True
      self.run.shout('NO WORLD YET: %d client ticks since the game was ready, and the run has asked for no world: at '
                     '%d it stops, with no results' % (ticks, NO_WORLD_TICKS))

  def _overTime(self, test: dict) -> None:
    limit = test['limit']
    number = test['number']
    if not self.watched:
      test['deadline'] = None
      self.run.stopTest(number, 'ran past its time limit (%d s): no verdict' % limit)
      return
    decision = self.ask('the test has run past its time limit (%d s)' % limit, False,
                        lambda: self.test is test and test['deadline'] is not None and self.clock() >= test['deadline'],
                        'stop this test (it has no result), with your reason, and go on with the next',
                        'the test is stopped as having run out of time (no result)', fromRound=True)
    if decision.action == WAIT:
      test['deadline'] = self.clock() + decision.seconds
    elif decision.action == FAIL:
      test['deadline'] = None
      self.run.stopTest(number, 'stopped by the watcher (alarm %d): %s' % (decision.alarm, decision.why))
    elif decision.action == ABORT:
      test['deadline'] = None
      self.run.abort('the watcher aborted the run (alarm %d): %s' % (decision.alarm, decision.why))
    elif decision.action == NO_ANSWER:
      test['deadline'] = None
      self.run.stopTest(number, 'ran past its time limit (%d s), and alarm %d had no answer: no verdict' % (
        limit, decision.alarm))

  def guardLoad(self, pending: Any, what: str) -> Any:
    """
    A world being made or opened, in a watched run (on the run's own
    thread): its answer, waited for; after LOAD_SECONDS an alarm asks.
    Given up (fail, abort, no answer): the request cancelled, and NoResult.
    """
    began = self.clock()
    askAt = began + LOAD_SECONDS
    self.loading = what
    self.loadingSince = began
    try:
      while True:
        try:
          #  a tenth of a second by the real clock, for an answer that is on its way
          return pending.result(0.1)
        except LinkTimeout:
          pass
        now = self.clock()
        if now >= askAt:
          decision = self.ask("%s hasn't loaded in %d s" % (what, now - began), True, lambda: not pending.done,
                              'give up on it: the run stops, and no test after it has a result',
                              'it is given up: the run stops, with no results after it')
          if decision.action == WAIT:
            askAt = self.clock() + decision.seconds
          elif decision.action != CLEARED:
            try:
              self.run.game.connection.cancel(pending)
            except Exception:  # the game may be past answering: the run stops all the same
              pass
            if decision.action == FAIL:
              raise NoResult('the watcher gave up on %s (alarm %d): %s' % (what, decision.alarm, decision.why))
            if decision.action == ABORT:
              why = 'the watcher aborted the run (alarm %d): %s' % (decision.alarm, decision.why)
              self.run.abort(why)
              raise NoResult(why)
            raise NoResult("%s didn't load (alarm %d had no answer)" % (what, decision.alarm))
          continue
        self.sleep(0.1)
    finally:
      self.loading = None

  # ---------------------------------------------------------------- an alarm and its answer

  def ask(self, what: str, threads: bool, stillSo: Callable[[], bool], failMeans: str, fallback: str,
          fromRound: bool = False) -> Decision:
    """
    Raises an alarm and waits for its answer: the watcher's decision,
    cleared when the situation passes by itself (or the run ends), no
    answer after the decision time. One alarm at a time; the watch's own
    round only tries (it never waits on another's alarm) and keeps
    watch.txt and the pictures going meanwhile.
    """
    if not self.alarmLock.acquire(blocking=not fromRound):
      return Decision(0, CLEARED)
    try:
      if self.ended.is_set() or not stillSo():
        return Decision(0, CLEARED)
      self.alarms += 1
      number = self.alarms
      alarmFile = os.path.join(self.results, 'alarm.txt')
      decisionFile = os.path.join(self.results, 'decision.txt')
      _remove(decisionFile)
      ticking = self.clientTicking()
      pictures = self._alarmPictures(number) if ticking else (
        "none: the client isn't ticking, so no picture can be taken (the threads show where it is)")
      dump = self._threads(number) if threads or not ticking else None
      answerBy = self.clock() + self.decide
      _writeWhole(alarmFile, self._alarmText(number, what, pictures, dump, failMeans, fallback, answerBy))
      self.openAlarm = number
      self.malformed = None
      self._log('alarm %d opened: %s' % (number, what))
      self.run.progress('ALARM %d: %s; look, then answer in decision.txt (%s)' % (number, what, alarmFile))
      remind = self.clock() + REMIND_SECONDS
      try:
        while True:
          if fromRound:
            self.housekeeping()
          decision = self._readDecision(decisionFile, number, alarmFile)
          if decision is not None:
            self._log('alarm %d answered: %s' % (number, _said(decision)))
            self.run.progress('alarm %d answered: %s' % (number, _said(decision)))
            return decision
          if self.ended.is_set():
            self._log('alarm %d closed: the run ended' % number)
            return Decision(number, CLEARED)
          if not stillSo():
            self._log('alarm %d cleared by itself' % number)
            self.run.progress('alarm %d cleared by itself' % number)
            return Decision(number, CLEARED)
          now = self.clock()
          if now >= answerBy:
            self._log('alarm %d: no answer in %d s, so %s' % (number, self.decide, fallback))
            self.run.progress('alarm %d: no answer in %d s, so %s' % (number, self.decide, fallback))
            return Decision(number, NO_ANSWER)
          if now >= remind:
            remind += REMIND_SECONDS
            self.run.progress('ALARM %d still open (%d s left before: %s)' % (number, answerBy - now, fallback))
          self.sleep(1)
      finally:
        self.openAlarm = 0
        _remove(alarmFile)
    finally:
      self.alarmLock.release()

  def _readDecision(self, path: str, number: int, alarmFile: str) -> Optional[Decision]:
    """The decision for this alarm in decision.txt, or None while there is none (one for another alarm is dropped)."""
    try:
      with open(path, encoding='utf-8') as file:
        text = file.read().strip()
    except OSError:
      return None
    if not text:
      return None
    line = text.split('\n', 1)[0].strip()
    found = DECISION.match(line)
    if not found:
      #  a moment for a decision still being written, then it is taken as said
      if self.malformed is None or self.malformed[0] != line:
        self.malformed = (line, self.clock())
        return None
      if self.clock() - self.malformed[1] < WRITING_SECONDS:
        return None
      self.malformed = None
      _remove(path)
      self._log("alarm %d: decision.txt said '%s', which is none of wait, fail, abort" % (number, line))
      _append(alarmFile, "\ndecision.txt said '%s': that's none of the three; write it again.\n" % line)
      return None
    _remove(path)
    if found.group(1) is not None and int(found.group(1)) != number:
      self._log('a decision for alarm %s came while alarm %d is open: dropped' % (found.group(1), number))
      return None
    action = found.group(2).lower()
    rest = found.group(3).strip()
    if action == WAIT:
      try:
        seconds = int(rest.split()[0])
      except (IndexError, ValueError):  # "wait" alone, or words after it: a minute
        seconds = 60
      return Decision(number, WAIT, max(1, min(seconds, 24 * 3600)), '')
    return Decision(number, action, 0, rest or 'no reason given')

  # ---------------------------------------------------------------- what it sees

  def clientTicking(self) -> bool:
    """Whether the last heartbeat, heard lately, shows a client that ticked within a few seconds."""
    ago = self._ago('client_ago_ms')
    return ago is not None and ago < TICKING_SECONDS

  def _ago(self, field: str) -> Optional[float]:
    """Seconds since the side ticked, by the last heartbeat and the time since it came; None if not known."""
    if self.beat is None or self.beat.get(field) is None:
      return None
    return self.beat[field] / 1000.0 + (self.clock() - self.heardAt)

  def situation(self) -> str:
    """'test 12/40 FooTests.testBar, 34 s in (its limit 60 s)', or what else the run is doing."""
    now = self.clock()
    test = self.test
    if test is not None:
      total = getattr(self.run, 'total', 0)
      limit = ' (its limit %d s)' % test['limit'] if test['limit'] else ''
      return 'test %d%s %s, %d s in%s' % (test['number'], '/%d' % total if total else '', test['name'],
                                         now - test['began'], limit)
    if self.loading is not None:
      return 'loading %s, %d s in' % (self.loading, now - self.loadingSince)
    if self.run.stopped is not None:
      return 'stopped: %s' % self.run.stopped
    ticks = self._ticksWithNoWorld()
    if ticks is not None:
      return 'waiting for its first world: none asked for yet, %d client ticks after the game was ready' % ticks
    return 'between tests'

  def _ticking(self, side: str) -> str:
    if self.beat is None:
      return 'not heard from yet'
    if side == 'server' and self.beat.get('server') is None:
      return 'none running'
    ago = self._ago(side + '_ago_ms')
    if ago is None:
      return "hasn't ticked yet"
    return 'ticking' if ago < 2 else 'last ticked %d s ago' % ago

  def _writeStatus(self) -> None:
    now = self.clock()
    if self.heardAt is None:
      probe = 'no heartbeat yet'
    elif now - self.heardAt >= SILENT_SECONDS:
      probe = ('silent for %d s (no heartbeat: the game is gone, or its whole JVM is held up)' % (now - self.heardAt))
    else:
      probe = 'heard from %d s ago' % (now - self.heardAt)
    crashed = getattr(self.run.game, 'crashed', None)
    lines = [
      'unitTAS watch, %s' % _clock(now),
      'run: %s' % self.situation(),
      'client: %s' % self._ticking('client'),
      'server: %s' % self._ticking('server'),
      'probe: %s' % probe,
      'picture: %s (the one before it: screenshots/watch-previous.png)' % self.lastPicture,
      'alarm: %s' % ('none open' if not self.openAlarm else '%d open: %s' % (
        self.openAlarm, os.path.join(self.results, 'alarm.txt'))),
    ]
    if crashed is not None:
      lines.append('crash: %s (its crash report: %s)' % (crashed['summary'], crashed['report']))
    _writeWhole(os.path.join(self.results, 'watch.txt'), '\n'.join(lines) + '\n')

  def _picture(self, name: str) -> Optional[str]:
    """A screenshot into the results' screenshots/; its path, or None. The watch's own request: a stopped test's
    refusal is the test's, not the watch's."""
    path = os.path.join(self.results, 'screenshots', name)
    _remove(path)
    try:
      self.run.game.connection.request('screenshot', {'file': path}, timeout=30)
    except Exception:  # no picture is no failure of anything
      return None
    return path if os.path.isfile(path) else None

  def _livePicture(self) -> None:
    now = self.clock()
    if not self.clientTicking():
      self.lastPicture = "none at %s: the client isn't ticking" % _clock(now)
      return
    fresh = self._picture('watch-new.png')
    if fresh is None:
      self.lastPicture = 'none at %s: the screenshot failed (the game\'s log says why)' % _clock(now)
      return
    shots = os.path.join(self.results, 'screenshots')
    live = os.path.join(shots, 'watch-live.png')
    if os.path.isfile(live):
      os.replace(live, os.path.join(shots, 'watch-previous.png'))
    os.replace(fresh, live)
    self.lastPicture = '%s, taken %s' % (live, _clock(now))

  def _alarmPictures(self, number: int) -> str:
    first = self._picture('alarm-%d-a.png' % number)
    self.sleep(PICTURE_GAP_SECONDS)
    second = self._picture('alarm-%d-b.png' % number)
    return '%s\n  and %d s later: %s' % (first or 'none (the screenshot failed)', PICTURE_GAP_SECONDS,
                                         second or 'none (the screenshot failed)')

  def _threads(self, number: int) -> str:
    """Every thread's stack (debug.threads, which answers while the game threads are stuck): its file."""
    path = os.path.join(self.results, 'alarm-%d-threads.txt' % number)
    try:
      text = self.run.game.connection.request('debug.threads', timeout=30)['text']
    except Exception as error:  # a probe past answering: said in the alarm
      return 'none (%s)' % error
    _writeWhole(path, text)
    return path

  def _alarmText(self, number: int, what: str, pictures: str, dump: Optional[str], failMeans: str, fallback: str,
                 answerBy: float) -> str:
    decision = os.path.join(self.results, 'decision.txt')
    live = os.path.join(self.results, 'screenshots', 'watch-live.png')
    lines = [
      'unitTAS alarm %d, %s' % (number, _clock(self.clock())),
      'what: %s' % what,
      'run: %s' % self.situation(),
      'client: %s; server: %s' % (self._ticking('client'), self._ticking('server')),
      'pictures: %s' % pictures,
      '  (the live picture, every %d s: %s)' % (self.pictures, live) if self.pictures > 0 else
      '  (no live pictures in this run)',
    ]
    if dump is not None:
      lines.append('threads: %s' % dump)
    lines += [
      'the run so far: %s' % os.path.join(self.results, 'progress.txt'),
      '',
      'Look at the pictures, decide whether the game is working or stuck, and write one line to',
      '%s:' % decision,
      '  %d wait <seconds>   it is working: give it that long (a new alarm comes if it is still at it then)' % number,
      '  %d fail <why>       %s' % (number, failMeans),
      '  %d abort <why>      stop the whole run, with your reason' % number,
      'No answer by %s (%d s): %s.' % (_clock(answerBy), self.decide, fallback),
    ]
    return '\n'.join(lines) + '\n'

  def _log(self, line: str) -> None:
    _append(os.path.join(self.results, 'alarms.txt'), '%s  %s\n' % (_clock(self.clock()), line))


# ---------------------------------------------------------------- files and time


def _clock(seconds: float) -> str:
  return time.strftime('%H:%M:%S', time.localtime(seconds))


def _writeWhole(path: str, text: str) -> None:
  """The file whole or not at all: a reader never sees half of it."""
  temporary = path + '.tmp'
  with open(temporary, 'w', encoding='utf-8') as file:
    file.write(text)
  os.replace(temporary, path)


def _append(path: str, text: str) -> None:
  with open(path, 'a', encoding='utf-8') as file:
    file.write(text)


def _remove(path: str) -> None:
  try:
    os.remove(path)
  except FileNotFoundError:
    pass

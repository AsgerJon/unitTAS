"""
The 'watcher' module is 'unittas watch' (SPEC.md 9.3, step 8b): the runs
an LLM's session asks for, made in the person's own session (their display,
their Gradle), for a session that can't open windows. The same files and
behaviour as unittas-watch.sh, which it replaces once its person restarts
into it (SPEC.md 9.6, decision 10):

- QUEUE/request: one line, a run to make. Once it is taken, QUEUE/run
  holds the run's results folder (known before the game starts, so its
  alarms can be found), and QUEUE/done its exit code when it ends.
- QUEUE/notify: lines for the person. Each is shown, and handed to
  ./request_task.sh (theirs, when there is one) as its one argument, also
  while a run is going.

A request line is 'unittas run's arguments (the tests), and the run is
watched (--watched): where a fixed limit would decide, its alarm asks in
its results folder. In unitTAS's own repository (its unittas.sh is there),
a line is as unittas-watch.sh takes it: '<suites> [filter]' for
./unittas.sh, watched, and 'probe [filter]' for the probe's own tests.

Nothing goes through a shell: a request's words are arguments, never a
command.

- QueueWatcher: the watcher of one folder.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
  from typing import Callable, Optional, TextIO

QUEUE = 'unittas-queue'
POLL_SECONDS = 2.0


def _run(argv: list, cwd: str, env: dict) -> int:
  return subprocess.call(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL)


def _writeWhole(path: str, text: str) -> None:
  """The file whole or not at all: the asking session never reads half of it."""
  temporary = path + '.tmp'
  with open(temporary, 'w', encoding='utf-8') as file:
    file.write(text)
  os.replace(temporary, path)


def _remove(path: str) -> None:
  try:
    os.remove(path)
  except FileNotFoundError:
    pass


class QueueWatcher:
  """
  The watcher of 'root' (the folder the runs are made from) and its queue
  folder. 'runner' runs a command (its words, its folder, its environment)
  and gives its exit code; 'stamp' names a run's results folder.
  """

  def __init__(self, root: str, queue: Optional[str] = None, runner: Callable[[list, str, dict], int] = _run,
               out: Optional[TextIO] = None, environ: Optional[dict] = None,
               stamp: Optional[Callable[[], str]] = None) -> None:
    self.root = os.path.abspath(root)
    self.queue = os.path.abspath(queue or os.path.join(self.root, QUEUE))
    self.runner = runner
    self.out = sys.stdout if out is None else out
    self.environ = dict(os.environ if environ is None else environ)
    self.stamp = stamp or (lambda: time.strftime('%Y-%m-%d_%H-%M-%S'))
    self.lock = threading.Lock()

  def say(self, line: str) -> None:
    with self.lock:
      print('[%s] %s' % (time.strftime('%H:%M:%S'), line), file=self.out)
      self.out.flush()

  def ownRepository(self) -> bool:
    """unitTAS's own repository: its scripts' requests (suites for ./unittas.sh, 'probe' for its own tests)."""
    return os.path.isfile(os.path.join(self.root, 'unittas.sh')) and os.path.isdir(
      os.path.join(self.root, 'python', 'tests', 'probe'))

  def command(self, line: str, stamp: str) -> tuple:
    """A request's command: (its words, its environment, its results folder)."""
    results = os.path.join(self.root, 'unittas-results', stamp)
    environment = dict(self.environ, UNITTAS_STAMP=stamp)
    if self.ownRepository():
      #  as unittas-watch.sh's 'read -r SUITES FILTER': the first word, and the rest of the line as it is
      parts = line.strip().split(None, 1)
      suites = parts[0] if parts else ''
      wanted = parts[1].strip() if len(parts) > 1 else ''
      if suites == 'probe':
        return [sys.executable, '-m', 'unittas.selftest', wanted], environment, results
      environment['UNITTAS_WATCHED'] = '1'
      return ['./unittas.sh', suites, wanted], environment, results
    argv = [sys.executable, '-m', 'unittas', 'run'] + line.split() + ['--watched', '--results', results]
    return argv, environment, results

  def once(self) -> bool:
    """The request waiting, run; False when there is none."""
    request = os.path.join(self.queue, 'request')
    if not os.path.isfile(request):
      return False
    with open(request, encoding='utf-8', errors='replace') as file:
      line = file.readline().rstrip('\n')
    for name in ('request', 'done', 'run'):
      _remove(os.path.join(self.queue, name))
    self.say('asked for: %s' % (line.strip() or 'every suite'))
    stamp = self.stamp()
    argv, environment, results = self.command(line, stamp)
    #  the run's folder, named before the game starts, so its alarms can be found
    _writeWhole(os.path.join(self.queue, 'run'), results + '\n')
    try:
      code = self.runner(argv, self.root, environment)
    except OSError as error:  # the command couldn't start: said, and done says so
      self.say('the run could not start: %s' % error)
      code = 127
    _writeWhole(os.path.join(self.queue, 'done'), '%d\n' % code)
    self.say('finished (exit %d); waiting for the next request' % code)
    return True

  def notifyOnce(self) -> int:
    """Each waiting notify line shown and handed to ./request_task.sh; how many there were."""
    notify = os.path.join(self.queue, 'notify')
    sending = notify + '.sending'
    try:
      if os.path.getsize(notify) == 0:
        return 0
      os.replace(notify, sending)
    except OSError:
      return 0
    with open(sending, encoding='utf-8', errors='replace') as file:
      lines = [line.strip() for line in file if line.strip()]
    script = os.path.join(self.root, 'request_task.sh')
    for line in lines:
      self.say('notify: %s' % line)
      if os.access(script, os.X_OK):
        code = subprocess.call([script, line], cwd=self.root, stdin=subprocess.DEVNULL)
        if code != 0:
          self.say('request_task.sh exited %d for that' % code)
      else:
        self.say('(no executable ./request_task.sh, so only shown here)')
    _remove(sending)
    return len(lines)

  def serve(self, stopped: Optional[threading.Event] = None) -> int:
    """Until Ctrl+C (or 'stopped'): the notifications on a thread of their own, the requests here."""
    stopped = stopped or threading.Event()
    os.makedirs(self.queue, exist_ok=True)

    def notifier() -> None:
      while not stopped.is_set():
        try:
          self.notifyOnce()
        except Exception as error:  # a notification that failed is said, and the next is tried
          self.say('a notification failed: %r' % error)
        stopped.wait(POLL_SECONDS)

    threading.Thread(target=notifier, name='unittas watch notify', daemon=True).start()
    self.say('unitTAS watcher: waiting for requests in %s, notifications from %s (Ctrl+C to stop)' % (
      self.queue, os.path.join(self.queue, 'notify')))
    try:
      while not stopped.is_set():
        self.once()
        stopped.wait(POLL_SECONDS)
    except KeyboardInterrupt:
      return 130
    finally:
      stopped.set()
    return 0

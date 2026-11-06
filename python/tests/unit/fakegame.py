"""
A launched game without a game, for the command line's tests (not a test module itself): the fake probe behind a
real listener, answering the operations a run makes, and a stop that records it was called. 'fakeHandlers' is the
answers FakeRun's fake game gives too.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
from typing import Any, Optional

from fakeprobe import FakeError, FakeProbe, inThread
from unittas.link import Listener
from unittas.wire import Role
from test_values import PLAYER


def fakeHandlers(gameDir: str) -> dict:
  """A fake game's answers for a run's operations: the world made in gameDir's saves/unittas, a reset, quit."""
  world = os.path.join(gameDir, 'saves', 'unittas')
  joined = {'where': None}

  def create(args, side):
    if os.path.exists(world):
      raise FakeError('Exists', 'saves/unittas is there already: world.create makes a new world', what='unittas')
    os.makedirs(os.path.join(world, 'region'))
    with open(os.path.join(world, 'level.dat'), 'w') as file:
      file.write('as made')
    return {'folder': 'unittas', 'load_ms': 10, 'spawn': [0, 4, 0]}

  batchAnswer = [{'ok': True, 'value': {'respawned': False}}, {'ok': True, 'value': {}},
                 {'ok': True, 'value': {'plugins': []}}]
  return {
    'hooks.run': lambda args, side: {'plugins': []},
    'world.create': create,
    'world.prepare': lambda args, side: {},
    'world.close': lambda args, side: {'close_ms': 5},
    'world.open': lambda args, side: {'folder': 'unittas', 'name': 'unitTAS', 'load_ms': 5},
    'client.reset': lambda args, side: {},
    'player.get': lambda args, side: dict(PLAYER, pos=[0.5, 4.0, 0.5]),
    'batch': lambda args, side: batchAnswer,
    'wait.until': lambda args, side: {'held': True, 'tick': 5, 'checks': 1, 'value': dict(PLAYER)},
    'ticks.wait': lambda args, side: {'waited_ms': 50, 'from': 1, 'tick': 2},
    'refs.clear': lambda args, side: {},
    'screenshot': lambda args, side: {'file': args['file']},
    'quit': lambda args, side: {},
    'java.run': javaRun,
    # a multiplayer class's: the run's own client joins and leaves a server, says in its status whether it is in, and
    # its part of the reset
    'server.join': lambda args, side: joined.update(where='127.0.0.1:%s' % args['port']) or {'load_ms': 40},
    'server.leave': lambda args, side: joined.update(where=None) or {'leave_ms': 5},
    'status': lambda args, side: {'joined': joined['where'], 'state': 'world', 'player': PLAYER['name']},
    'client.reset': lambda args, side: {},
  }


def javaRun(args, side):
  """
  java.run as the Java runner does it, in short: one test (SaveTests.test_x) for each save and load, or once in the
  fresh test world with no saves; its numbered lines into results/progress.txt and its report into results/.
  """
  results = args['results']
  saves = args.get('saves') or []
  names = ['SaveTests.test_x [%s, load %d]' % (save, load) for load in (1, 2) for save in saves] or ['SaveTests.test_x']
  os.makedirs(results, exist_ok=True)
  with open(os.path.join(results, 'progress.txt'), 'a', encoding='utf-8') as file:
    for number, name in enumerate(names, 1):
      file.write('test %d/%d %s ... ok\n' % (number, len(names), name))
  report = os.path.join(results, 'report.txt')
  with open(report, 'w', encoding='utf-8') as file:
    file.write('unitTAS report\n\n' + ''.join('%s ... ok (0.1 s)\n' % name for name in names) + '-' * 70 + '\n'
               + 'Ran %d tests in 1.0 s\n\nOK\n' % len(names))
  return {'report': report, 'ok': True, 'counts': {'ran': len(names), 'failures': 0, 'errors': 0, 'skipped': 0,
                                                    'expected_failures': 0, 'unexpected_successes': 0,
                                                    'no_results': 0, 'problems': 0}}


class FakeLaunched:
  """
  A LaunchedGame's face for a run: 'start' (the fake probe connects, its
  hello welcomed, then 'ready'), 'stop', 'gameDir', 'results', and its
  log (outputName, in the results), a line written to it as it starts.
  'failing' is raised by start instead, for a game that can't start.
  'ready': True sends ready at once, False never, a function is run with
  this game on a thread of its own after the hello (it loads, as it
  likes: 'log' and 'sendReady'). 'asked' holds the requests, 'stops' how
  often stop was called, 'savesAtStart' the saves there as it started.
  """

  def __init__(self, gameDir: str, results: str, failing: Optional[BaseException] = None,
               handlers: Optional[dict] = None, ready: Any = True) -> None:
    self.gameDir = gameDir
    self.results = results
    self.failing = failing
    self.handlers = fakeHandlers(gameDir) if handlers is None else handlers
    self.ready = ready
    self.asked = []
    self.stops = 0
    self.starts = 0
    self.savesAtStart = None
    self.fake = None
    self.connection = None
    self.listener = None
    os.makedirs(gameDir, exist_ok=True)

  def outputName(self) -> str:
    return 'game.log'

  def log(self, line: str) -> None:
    os.makedirs(self.results, exist_ok=True)
    with open(os.path.join(self.results, self.outputName()), 'a', encoding='utf-8') as file:
      file.write(line + '\n')

  def sendReady(self) -> None:
    self.fake.event('ready', screen='net.minecraft.client.gui.GuiMainMenu', load_ms=10, mods=[], mixins=[],
                    window={'title': 'unitTAS', 'width': 854, 'height': 480, 'pointer_grabbed': False})

  def start(self) -> Any:
    self.starts += 1
    saves = os.path.join(self.gameDir, 'saves')
    self.savesAtStart = sorted(os.listdir(saves)) if os.path.isdir(saves) else []
    if self.failing is not None:
      raise self.failing
    self.log('[main/INFO] [FML]: Forge Mod Loader is loading its mods')
    self.listener = Listener()
    expected = self.listener.prepare(self.gameDir, 'alice', Role.CLIENT)
    self.fake = FakeProbe(expected.startFile)
    thread, _ = inThread(self.fake.connect)
    self.connection = self.listener.accept(timeout=10)
    thread.join(10)
    self.asked = self.fake.serve(self.handlers)
    if self.ready is True:
      self.sendReady()
    elif callable(self.ready):
      inThread(self.ready, self)
    return self.connection

  def stop(self) -> None:
    self.stops += 1
    if self.connection is not None:
      self.connection.close()
    if self.fake is not None:
      self.fake.close()
    if self.listener is not None:
      self.listener.close()

  def ops(self) -> list:
    return [request['op'] for request in self.asked]


class Factory:
  """A gameFor for the command line: hands out one FakeLaunched (made on first use), and records each call."""

  def __init__(self, gameDir: str, failing: Optional[BaseException] = None, ready: Any = True) -> None:
    self.gameDir = gameDir
    self.failing = failing
    self.ready = ready
    self.calls = []
    self.game = None

  def __call__(self, spec: Any, results: str, name: str = 'game', **_: Any) -> FakeLaunched:
    self.calls.append((spec.path, results, name))
    self.game = FakeLaunched(self.gameDir, results, failing=self.failing, ready=self.ready)
    return self.game

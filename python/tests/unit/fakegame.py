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
  }


class FakeLaunched:
  """
  A LaunchedGame's face for a run: 'start' (the fake probe connects, its
  hello welcomed, then 'ready'), 'stop', 'gameDir', 'results'. 'failing'
  is raised by start instead, for a game that can't start. 'asked' holds
  the requests, 'stops' how often stop was called.
  """

  def __init__(self, gameDir: str, results: str, failing: Optional[BaseException] = None,
               handlers: Optional[dict] = None) -> None:
    self.gameDir = gameDir
    self.results = results
    self.failing = failing
    self.handlers = fakeHandlers(gameDir) if handlers is None else handlers
    self.asked = []
    self.stops = 0
    self.starts = 0
    self.fake = None
    self.connection = None
    self.listener = None
    os.makedirs(gameDir, exist_ok=True)

  def start(self) -> Any:
    self.starts += 1
    if self.failing is not None:
      raise self.failing
    self.listener = Listener()
    expected = self.listener.prepare(self.gameDir, 'alice', Role.CLIENT)
    self.fake = FakeProbe(expected.startFile)
    thread, _ = inThread(self.fake.connect)
    self.connection = self.listener.accept(timeout=10)
    thread.join(10)
    self.asked = self.fake.serve(self.handlers)
    self.fake.event('ready', screen='net.minecraft.client.gui.GuiMainMenu', load_ms=10, mods=[], mixins=[],
                    window={'title': 'unitTAS', 'width': 854, 'height': 480, 'pointer_grabbed': False})
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

  def __init__(self, gameDir: str, failing: Optional[BaseException] = None) -> None:
    self.gameDir = gameDir
    self.failing = failing
    self.calls = []
    self.game = None

  def __call__(self, spec: Any, results: str, name: str = 'game', **_: Any) -> FakeLaunched:
    self.calls.append((spec.path, results, name))
    self.game = FakeLaunched(self.gameDir, results, failing=self.failing)
    return self.game

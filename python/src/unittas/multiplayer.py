"""
The 'multiplayer' module is a run's other games, for its multiplayer
classes (SPEC.md 11.3, step 5; PROTOCOL.md 9): a dedicated server, and
the clients a class names beyond the first, which is the run's own client
(decision D2). A real game each (D1).

- The first multiplayer class: the memory checked first (D5); the server
  started, its world prepared and its setUpWorld run; the other clients
  started; then all join it. The server's operators are the players, by
  the names their games have.
- A fresh world for a class is a restart (PROTOCOL.md 9.2): the clients
  leave, the server's tearDownWorld runs and it stops, its world folder
  goes, and a new server starts (on a new port) and makes the world again
  from the same seed. A shared class after a multiplayer one runs on as
  it is.
- Before each test, a client a test put out (kicked, or left) joins again
  ('rejoin'), so the class's next tests have it.
- 'leave' before a singleplayer class; 'stop' at the run's end.

- MemoryShort: the machine hasn't the memory for the games a class needs.
- megabytes, availableMb: memory in words, and the machine's.
- Multiplayer: one run's other games.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from .api import Game
from .errors import NotReady, UnitTasError
from .gamefiles import removeTree

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Callable, Optional

  from .run import Run

#  A real 1.7.10 client's memory (the launcher's -Xmx), and what is kept to spare beside the games (D5).
CLIENT_MB = 2048
MARGIN_MB = 1024
#  From a game's start to its ready: every mod loaded.
READY_SECONDS = float(os.environ.get('UNITTAS_READY_SECONDS', '600'))
_MEMORY = re.compile(r'^([1-9][0-9]*)([MG])$')


class MemoryShort(UnitTasError):
  """The machine hasn't the memory for the games a multiplayer class needs: nothing was started; the message says."""


def megabytes(memory: str) -> int:
  """'2G' or '1536M' as megabytes; ValueError for anything else."""
  found = _MEMORY.match(memory or '')
  if not found:
    raise ValueError("memory is as -Xmx takes it, '2G' or '1536M', not %r" % (memory,))
  return int(found.group(1)) * (1024 if found.group(2) == 'G' else 1)


def availableMb(path: str = '/proc/meminfo') -> Optional[int]:
  """The machine's available memory (MemAvailable), in megabytes; None where it can't be read."""
  try:
    with open(path, encoding='ascii') as file:
      for line in file:
        if line.startswith('MemAvailable:'):
          return int(line.split()[1]) // 1024
  except (OSError, ValueError, IndexError):
    return None
  return None


class Multiplayer:
  """
  One run's other games. 'serverFor(players)' makes a dedicated server's
  launch (its 'ready', 'stop', 'port', 'worldFolder'), its operators the
  players named; 'clientFor(name)' makes a further client's (its 'start',
  'stop'), its player of that name. 'serverMb' and 'clientMb' are their
  memory, 'available' the machine's (megabytes, or None: unknown, not
  checked).
  """

  def __init__(self, run: Run, serverFor: Callable[[tuple], Any], clientFor: Callable[[str], Any],
               serverMb: int = 2048, clientMb: int = CLIENT_MB,
               available: Callable[[], Optional[int]] = availableMb) -> None:
    self.run = run
    self.serverFor = serverFor
    self.clientFor = clientFor
    self.serverMb = serverMb
    self.clientMb = clientMb
    self.available = available
    self.server = None
    self.serverGame = None
    #  the further clients, by the name a class gave them: (their launch, their Game)
    self.others = {}
    #  the class's clients, in its order (the first the run's own), and the server's operators
    self.names = ()
    self.players = ()
    self.joined = False

  # ---------------------------------------------------------------- what the classes see

  def games(self) -> dict:
    """The games by the names the class gave them, and 'server'."""
    out = {'server': self.serverGame, self.names[0]: self.run.game}
    for name in self.names[1:]:
      out[name] = self.others[name][1]
    return out

  def otherGames(self) -> list:
    """The server and the further clients, each by its name: what a NO RESULT may have to name."""
    out = [('server', self.serverGame)] if self.serverGame is not None else []
    return out + [(name, game) for name, (_, game) in sorted(self.others.items())]

  def connections(self) -> list:
    """The clients' connections, the run's own first: the reset's clients."""
    return [self.run.game.connection] + [self.others[name][1].connection for name in self.names[1:]]

  # ---------------------------------------------------------------- the classes come and go

  def check(self, names: tuple) -> None:
    """MemoryShort, before anything starts, if the machine hasn't the memory for what these names need started."""
    missing = [name for name in names[1:] if name not in self.others]
    parts = []
    if self.server is None:
      parts.append(('the server', self.serverMb))
    parts += [(name, self.clientMb) for name in missing]
    if not parts:
      return
    need = sum(mb for _, mb in parts) + MARGIN_MB
    have = self.available()
    if have is not None and have < need:
      raise MemoryShort('a multiplayer class needs about %d MB for its other games (%s, and %d to spare), and %d MB '
                        'is available' % (need, ', '.join('%s %d' % part for part in parts), MARGIN_MB, have))

  def enter(self, names: tuple, shared: bool) -> bool:
    """
    The games these names need, started and joined, the run's own client
    at the title screen already: a fresh world unless 'shared' (and the
    server's operators are all there). Whether the world is fresh.
    """
    for name in names[1:]:
      if name not in self.others:
        self.others[name] = self._client(name)
    self.names = tuple(names)
    players = (self.run.game.playerName(),) + tuple(self.others[name][1].playerName() for name in names[1:])
    fresh = True
    if self.server is not None and self.joined and shared and set(players) <= set(self.players):
      fresh = False
    elif self.server is not None:
      self._restart(players)
    else:
      self._startServer(players)
    if fresh or not self.joined:
      self._joinAll()
    else:
      #  shared: the clients this class doesn't name leave, so the server has the class's players only, and those it
      #  names that an earlier class let go join again
      for name, (_, game) in self.others.items():
        if name not in self.names and game.request('status').get('joined') is not None:
          game.leave()
      self.rejoin()
    return fresh

  def rejoin(self) -> None:
    """Before a test: each of the class's clients that is out of the server (a test kicked it) joins it again."""
    if not self.joined:
      return
    port = self.server.port
    for game in [self.run.game] + [self.others[name][1] for name in self.names[1:]]:
      if game.request('status').get('joined') is None:
        game.join(port)

  def leave(self) -> None:
    """The clients that joined leave the server, for a singleplayer class: the run's own back at its title screen."""
    if not self.joined:
      return
    for game in [self.run.game] + [game for _, game in self.others.values()]:
      try:
        game.leave()
      except NotReady:
        #  it wasn't in (kicked by a test, say): out all the same
        pass
    self.joined = False

  def stop(self) -> None:
    """The run's end: the clients leave, the others stop, the server's tearDownWorld runs and it stops."""
    try:
      self.leave()
    finally:
      for launched, _ in self.others.values():
        try:
          launched.stop()
        except Exception:  # each is stopped whatever the one before did
          pass
      self.others = {}
      self._stopServer()

  # ---------------------------------------------------------------- the games

  def _client(self, name: str) -> tuple:
    launched = self.clientFor(name)
    try:
      connection = launched.start()
      connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    except BaseException:
      launched.stop()
      raise
    self._watched(name, connection)
    return launched, Game(connection)

  def _startServer(self, players: tuple) -> None:
    launched = self.serverFor(players)
    connection, _ = launched.ready(READY_SECONDS)
    self.server = launched
    self.serverGame = Game(connection)
    self.players = players
    self._watched('server', connection)
    self.serverGame.request('world.prepare')
    self.serverGame.request('hooks.run', {'hook': 'setUpWorld'})

  def _stopServer(self) -> None:
    if self.server is None:
      return
    try:
      self.serverGame.request('hooks.run', {'hook': 'tearDownWorld'})
    except UnitTasError:
      #  a server past answering: stopped all the same
      pass
    finally:
      self.server.stop()
      world = self.server.worldFolder()
      if os.path.lexists(world):
        removeTree(world)
      self.server = None
      self.serverGame = None

  def _restart(self, players: tuple) -> None:
    self.leave()
    self._stopServer()
    self._startServer(players)

  def _joinAll(self) -> None:
    port = self.server.port
    self.run.game.join(port)
    for name in self.names[1:]:
      self.others[name][1].join(port)
    self.joined = True

  def _watched(self, name: str, connection: Any) -> None:
    watch = getattr(self.run, 'watch', None)
    if watch is not None:
      watch.addGame(name, connection)

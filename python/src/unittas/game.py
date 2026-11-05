"""
The 'game' module holds what every launch of a test game shares, for the
probe's tests: the start file written first, the game folder's options.txt
and config/ kept aside meanwhile and put back once the game has exited,
the hello waited for with its fail-fast rules, and the stop. The orchestrator
proper, with its own launcher for any instance, is phase 3; this is the
probe's test bench.

- LaunchedGame: one launch of a game; DevGame (the development client) and
  ReleaseGame (the real client) say which game and how it starts.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import signal
import subprocess
import time
from typing import TYPE_CHECKING

from worktoy.desc import Field
from worktoy.mcls import BaseObject

from .errors import LinkClosed, LinkTimeout, UnitTasError
from .gamefiles import GameFiles
from .link import Listener
from .wire import Role

if TYPE_CHECKING:  # pragma: no cover
  from typing import Callable, Optional

  from .link import Connection, Expected

#  How long a launch may take from its start to the probe's hello (a cold build included).
HELLO_SECONDS = float(os.environ.get('UNITTAS_HELLO_SECONDS', '600'))
#  What FML logs once every mod has loaded; the probe has said hello long before (it dials as Minecraft starts).
LOADED = 'Forge Mod Loader has successfully loaded'
LOADED_GRACE = 10.0


class LaunchedGame(BaseObject):
  """
  One launch of a game. 'launch' starts it; 'start' launches and waits
  for its hello; 'stop' asks it to quit and makes sure it has gone;
  'ended' waits for it to go by itself. The launch's own output goes to
  '<results>/<name>/'. A kind of game says its folder (gameFolder), its
  command (command), the file in the results its game's output is in
  (outputName) and its command's own (launchName, the same by default),
  and what it needs before it starts (prepare).
  """

  name: Field[str] = Field()
  gameDir: Field[str] = Field()
  listener: Field[Listener] = Field()
  connection: Field[object] = Field()
  results: Field[str] = Field()

  def __init__(self, root: str, results: str, name: str = 'game') -> None:
    self.__root__ = os.path.abspath(root)
    self.__game_name__ = name
    self.__results__ = os.path.join(results, name)
    self.__listener__ = None
    self.__connection__ = None
    self.__process__ = None
    self.__files__ = None

  @name.GET
  def _getName(self) -> str:
    return self.__game_name__

  @gameDir.GET
  def _getGameDir(self) -> str:
    return self.gameFolder()

  @listener.GET
  def _getListener(self) -> Optional[Listener]:
    return self.__listener__

  @connection.GET
  def _getConnection(self) -> Optional[Connection]:
    return self.__connection__

  @results.GET
  def _getResults(self) -> str:
    return self.__results__

  # ---------------------------------------------------------------- what a kind of game says

  def root(self) -> str:
    """unitTAS's repository."""
    return self.__root__

  def gameFolder(self) -> str:
    """The game's folder (its saves, mods/, config/, the start file)."""
    raise NotImplementedError

  def command(self) -> list:
    """The command that starts the game, run from the repository."""
    raise NotImplementedError

  def outputName(self) -> str:
    """The file in the results the game's output is in, where FML's lines are."""
    raise NotImplementedError

  def launchName(self) -> str:
    """The file in the results the command's own output goes to: the game's, unless the command writes that itself."""
    return self.outputName()

  def prepare(self) -> None:
    """What the game needs before it starts, after its folder's own files are kept aside; nothing by default."""

  def workingDir(self) -> str:
    """Where the command runs: the repository, by default."""
    return self.__root__

  def environment(self) -> dict:
    """The command's environment: this process's, by default."""
    return dict(os.environ)

  def terminate(self) -> None:
    """Asks a game that can't be asked over its connection to stop (SIGTERM)."""
    self.__process__.send_signal(signal.SIGTERM)

  def process(self) -> Optional[subprocess.Popen]:
    return self.__process__

  # ---------------------------------------------------------------- the launch

  def launch(self, beforeLaunch: Optional[Callable[[Expected], None]] = None) -> Expected:
    """
    Writes the start file and starts the game, not waiting for it.
    'beforeLaunch' sees the start file first (a test that spoils it).
    """
    os.makedirs(self.results, exist_ok=True)
    os.makedirs(self.gameDir, exist_ok=True)
    #  the game folder's own files aside first: what prepare writes there for the run (options, config) is then undone
    self.__files__ = GameFiles(self.gameDir)
    self.__files__.keep()
    self.prepare()
    self.__listener__ = Listener()
    expected = self.__listener__.prepare(self.gameDir, self.name, Role.CLIENT)
    if beforeLaunch is not None:
      beforeLaunch(expected)
    output = open(os.path.join(self.results, self.launchName()), 'ab')
    environment = dict(self.environment(), UNITTAS_RESULTS=self.results)
    self.__process__ = subprocess.Popen(
      self.command(), cwd=self.workingDir(), env=environment,
      stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
    output.close()
    return expected

  def accept(self, seconds: float = HELLO_SECONDS) -> Connection:
    """
    The game's connection, once its hello is welcomed. LinkClosed if the
    game ends first; LinkTimeout after 'seconds', at once when its hello
    was refused, or once the game has loaded every mod (FML says so in its
    log) and no hello came within LOADED_GRACE seconds: a probe that
    never woke.
    """
    deadline = time.monotonic() + seconds
    loadedAt = None
    while True:
      left = deadline - time.monotonic()
      if left <= 0:
        raise LinkTimeout('%s: no hello within %s s (its output: %s)' % (self.name, seconds, self.results))
      if loadedAt is None and self._loaded():
        loadedAt = time.monotonic()
      if loadedAt is not None and time.monotonic() - loadedAt > LOADED_GRACE:
        raise LinkTimeout('%s: the game has loaded every mod, but its probe never said hello (its output: %s)' % (
          self.name, self.results))
      try:
        self.__connection__ = self.__listener__.accept(timeout=min(5.0, left))
        return self.__connection__
      except LinkTimeout as timeout:
        #  a refused game quits: no point waiting for it
        if 'refused meanwhile' in str(timeout):
          raise LinkTimeout('%s: its hello was refused (%s)' % (self.name, timeout)) from timeout
        if self.__process__.poll() is not None:
          raise LinkClosed('%s ended before it connected (exit %s; its output: %s)' % (
            self.name, self.__process__.returncode, self.results))

  def _loaded(self) -> bool:
    """Whether FML has said, in the game's output, that it loaded every mod."""
    try:
      with open(os.path.join(self.results, self.outputName()), encoding='utf-8', errors='replace') as log:
        return any(LOADED in line for line in log)
    except OSError:
      return False

  def start(self, seconds: float = HELLO_SECONDS) -> Connection:
    """Launches the game and waits for its hello; on any failure it is stopped again."""
    self.launch()
    try:
      return self.accept(seconds)
    except BaseException:
      self.stop()
      raise

  def ended(self, seconds: float) -> bool:
    """Whether the game's process ends within the time, by itself."""
    if self.__process__ is None:
      return True
    try:
      self.__process__.wait(seconds)
      return True
    except subprocess.TimeoutExpired:
      return False

  def stop(self, seconds: float = 60.0) -> Optional[int]:
    """
    Asks the game to quit and waits 'seconds' for it, then makes it go
    (terminate). A game that can't be asked (it never connected, or its
    connection is gone) gets 5 s, not the full wait. Then the folder's own
    files are put back. Returns the exit code.
    """
    try:
      connection = self.__connection__
      asked = False
      if connection is not None and not connection.closed:
        try:
          connection.request('quit', {'reason': 'the tests are done'}, timeout=10)
          asked = True
        except UnitTasError:
          pass
      #  only a game that was asked gets the time to quit by itself; one nobody can ask is stopped now
      if not self.ended(seconds if asked else 5.0) and self.__process__ is not None:
        self.terminate()
        if not self.ended(45):
          os.killpg(self.__process__.pid, signal.SIGKILL)
          self.ended(15)
      return None if self.__process__ is None else self.__process__.returncode
    finally:
      if self.__connection__ is not None:
        self.__connection__.close()
      if self.__listener__ is not None:
        self.__listener__.close()
      if self.__files__ is not None:
        self.__files__.putBack()

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
from .gameoutput import GameOutput
from .launcher import FAILED as LAUNCHER_FAILED
from .link import Listener
from .wire import Role

if TYPE_CHECKING:  # pragma: no cover
  from typing import Callable, Optional

  from .link import Connection, Expected

#  How long a launch may go without a sign of life (nothing new in its output) before the probe's hello: a launcher
#  fetching or installing, or a build, says what it does as it goes, so one quiet this long is stuck (Asger,
#  2026-11-17: "if you open a game, it must never hang")
HELLO_SECONDS = float(os.environ.get('UNITTAS_HELLO_SECONDS', '120'))
#  What the agent says as it wakes in the game (its premain, as the JVM starts); its probe dials seconds after (2 s in
#  26.3 beside NeoForge), so a hello not come this long after it never will
WOKE = '[unitTAS] the probe wakes'
HELLO_AFTER_WAKE = 30.0
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
  what it needs before it starts (prepare), and its role (a client
  unless it says otherwise).
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

  def role(self) -> Role:
    """What the game is, for its start file and its hello (PROTOCOL.md 9.1): a client, unless a kind says otherwise."""
    return Role.CLIENT

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
    expected = self.__listener__.prepare(self.gameDir, self.name, self.role())
    if beforeLaunch is not None:
      beforeLaunch(expected)
    output = open(os.path.join(self.results, self.launchName()), 'ab')
    #  why an earlier launch couldn't start is not this one's
    failed = os.path.join(self.results, LAUNCHER_FAILED)
    if os.path.isfile(failed):
      os.remove(failed)
    environment = dict(self.environment(), UNITTAS_RESULTS=self.results)
    self.__process__ = subprocess.Popen(
      self.command(), cwd=self.workingDir(), env=environment,
      stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
    output.close()
    return expected

  def accept(self, seconds: float = HELLO_SECONDS) -> Connection:
    """
    The game's connection, once its hello is welcomed. It never waits on a
    game that shows no sign of life: LinkClosed if the game ends first,
    saying the launcher's reason when it couldn't start the game (it leaves
    it in the results, LAUNCHER_FAILED: in the test display a launch ends
    with gamescope's exit code, not the launcher's); LinkTimeout at once
    when its hello was refused; once 'seconds' pass
    with nothing new in the game's output (a launcher fetching or
    installing, or a build, says what it does as it goes); once the agent
    has woken in the game (WOKE in its output) and no hello came within
    HELLO_AFTER_WAKE; or once FML has loaded every mod (its log says so)
    and none came within LOADED_GRACE: a probe that never woke.
    """
    seen = GameOutput(os.path.join(self.results, self.outputName()), (WOKE, LOADED))
    #  the command's own output, where it is a file of its own (a launch script's lines): a sign of life too
    launching = None if self.launchName() == self.outputName() else GameOutput(
      os.path.join(self.results, self.launchName()), ())
    quietSince = time.monotonic()
    wokeAt = loadedAt = None
    while True:
      now = time.monotonic()
      if seen.grew() | (launching is not None and launching.grew()):
        quietSince = now
      if now - quietSince > seconds:
        raise LinkTimeout('%s: no hello, and nothing new in its output for %s s (its output: %s)' % (
          self.name, seconds, self.results))
      if wokeAt is None and seen.said(WOKE):
        wokeAt = now
      if wokeAt is not None and now - wokeAt > HELLO_AFTER_WAKE:
        raise LinkTimeout('%s: its agent woke, but its probe never said hello in %s s (its output: %s)' % (
          self.name, HELLO_AFTER_WAKE, self.results))
      if loadedAt is None and seen.said(LOADED):
        loadedAt = now
      if loadedAt is not None and now - loadedAt > LOADED_GRACE:
        raise LinkTimeout('%s: the game has loaded every mod, but its probe never said hello (its output: %s)' % (
          self.name, self.results))
      try:
        self.__connection__ = self.__listener__.accept(timeout=1.0)
        return self.__connection__
      except LinkTimeout as timeout:
        #  a refused game quits: no point waiting for it
        if 'refused meanwhile' in str(timeout):
          raise LinkTimeout('%s: its hello was refused (%s)' % (self.name, timeout)) from timeout
        if self.__process__.poll() is not None:
          raise self.__endedFirst__() from None

  def __endedFirst__(self) -> LinkClosed:
    """A game that ended before its hello: the launcher's reason if it left one, else its exit code."""
    failed = os.path.join(self.results, LAUNCHER_FAILED)
    if os.path.isfile(failed):
      with open(failed, encoding='utf-8', errors='replace') as file:
        reason = file.read().strip()
      return LinkClosed("%s: unitTAS's launcher couldn't start it: %s" % (self.name, reason))
    return LinkClosed('%s ended before it connected (exit %s; its output: %s)' % (
      self.name, self.__process__.returncode, self.results))

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

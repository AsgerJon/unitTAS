"""
The 'servergame' module is a dedicated server's folder for a run (SPEC.md
11.3, step 1; PROTOCOL.md 9.2 and 15). Three files, written fresh for each
run and never merged with what was there:

- server.properties: the test world (flat, creative, the seed and layers
  of the client's own test world), listening on 127.0.0.1 alone, with no
  other port opened (no remote console, no query) and no login checks: a
  test client has no Mojang login, and loopback is what keeps that safe;
- eula.txt: only on the user's own acceptance of Mojang's EULA, which
  unitTAS never gives for anyone;
- ops.json: the run's players and nobody else, by their offline ids, so
  that commands run as them.

The address is no argument: there is no way to write another. And it is
checked, not assumed (step 2): the server's probe says in its ready every
address the server listens on, from the server's own endpoints, and a
server that names any but 127.0.0.1, or none, is stopped before any client
joins.

- ServerSetupError: a server that can't be set up or let through as asked.
- freePort: a port free on 127.0.0.1 for the run's server.
- serverFiles: the three files.
- awaitServerReady: the server's ready, waited for and its addresses
  checked.
- ServerGame: one launch of a dedicated server with the probe in it.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import json
import os
import re
import socket
import time
import uuid
from typing import TYPE_CHECKING

from .errors import LinkTimeout, UnitTasError
from .game import LaunchedGame
from .gameoutput import GameOutput
from .launcher import Sources, findJava, offlineId, serverCommand, serverVersionCommand
from .release import putMods
from .wire import Role

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Callable, Iterable, Optional

  from .link import Connection

EULA_URL = 'https://aka.ms/MinecraftEULA'
LOOPBACK = '127.0.0.1'
#  127.0.0.1 as a server's ready may say it: Java on Linux listens through an IPv6 socket, which names it so
LOOPBACK_FORMS = ('127.0.0.1', '::ffff:127.0.0.1')
#  From the server's hello to its world's first tick: how long it may go without a sign of life (nothing new in its
#  output) before its ready, as a game's hello is waited for (SPEC.md 19.7 step 10a; Asger, 2026-11-17: "600s is
#  disgusting"); a server making its world says what it does as it goes
READY_SECONDS = float(os.environ.get('UNITTAS_READY_SECONDS', '120'))
#  A player name as 1.7.10 takes one: letters, digits and the underscore, 1 to 16 of them.
NAME = re.compile(r'^[A-Za-z0-9_]{1,16}$')
#  server.properties, in this order; the port goes in where it says.
PROPERTIES = (
  ('server-ip', LOOPBACK),
  ('server-port', None),
  ('online-mode', 'false'),
  ('enable-rcon', 'false'),
  ('enable-query', 'false'),
  ('snooper-enabled', 'false'),
  ('level-name', 'unittas'),
  ('level-type', 'FLAT'),
  ('generator-settings', '2;7,2x3,2;1;'),
  ('level-seed', '20261029'),
  ('gamemode', '1'),
  ('force-gamemode', 'true'),
  ('difficulty', '1'),
  ('spawn-protection', '0'),
  ('allow-flight', 'true'),
  ('max-players', '8'),
  ('player-idle-timeout', '0'),
  ('announce-player-achievements', 'false'),
  ('enable-command-block', 'true'),
  ('white-list', 'false'),
  ('motd', 'unitTAS'),
)
#  A modern server's test world (SPEC.md 19.7 step 10a): the client's (bedrock, two dirt, grass, on plains, no
#  structures), its layers as server.properties takes them from 1.13 on (JSON)
MODERN_LAYERS = json.dumps({'layers': [{'block': 'minecraft:bedrock', 'height': 1},
                                       {'block': 'minecraft:dirt', 'height': 2},
                                       {'block': 'minecraft:grass_block', 'height': 1}],
                            'biome': 'minecraft:plains'}, separators=(',', ':'))
#  A modern server's server.properties, in this order: 1.7.10's less what a modern server hasn't (the snooper, the
#  achievements' announcement, a rule now), its game mode and difficulty by name, and no chat signing (a test client
#  signs none)
MODERN_PROPERTIES = (
  ('server-ip', LOOPBACK),
  ('server-port', None),
  ('online-mode', 'false'),
  ('enforce-secure-profile', 'false'),
  ('enable-rcon', 'false'),
  ('enable-query', 'false'),
  ('level-name', 'unittas'),
  ('level-type', 'minecraft:flat'),
  ('generator-settings', MODERN_LAYERS),
  ('generate-structures', 'false'),
  ('level-seed', '20261029'),
  ('gamemode', 'creative'),
  ('force-gamemode', 'true'),
  ('difficulty', 'easy'),
  ('spawn-protection', '0'),
  ('allow-flight', 'true'),
  ('max-players', '8'),
  ('player-idle-timeout', '0'),
  ('enable-command-block', 'true'),
  ('white-list', 'false'),
  ('motd', 'unitTAS'),
)


#  1.16.1's (SPEC.md 19.7 step 11f): a world type named without a namespace, and the flat layers' JSON as its codec
#  needs it: its structures (none: StructureSettings' own map, empty), lakes and features said
LAYERS_1_16 = json.dumps({'structures': {'structures': {}},
                          'layers': [{'block': 'minecraft:bedrock', 'height': 1},
                                     {'block': 'minecraft:dirt', 'height': 2},
                                     {'block': 'minecraft:grass_block', 'height': 1}],
                          'lakes': False, 'features': False, 'biome': 'minecraft:plains'}, separators=(',', ':'))
PROPERTIES_1_16 = tuple((key, {'level-type': 'flat', 'generator-settings': LAYERS_1_16}.get(key, value))
                        for key, value in MODERN_PROPERTIES)


class ServerSetupError(UnitTasError):
  """A server folder that can't be written as asked: its message says why."""


def freePort() -> int:
  """A port that is free on 127.0.0.1 now, for the run's server."""
  with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    probe.bind((LOOPBACK, 0))
    return probe.getsockname()[1]


def _dashed(hexId: str) -> str:
  return str(uuid.UUID(hex=hexId))


def _writeWhole(path: str, text: str) -> None:
  temporary = path + '.tmp'
  with open(temporary, 'w', encoding='utf-8') as file:
    file.write(text)
  os.replace(temporary, path)


def serverFiles(folder: str, port: int, players: Iterable[str], eula: bool, minecraft: str = '1.7.10') -> None:
  """
  The server's three files in its folder, for a server of 'minecraft' on
  127.0.0.1 at 'port' with 'players' its operators (server.properties as
  that version reads it: 1.7.10's, 1.16.1's, or a modern one's). 'eula' is the
  user's own acceptance of Mojang's EULA (the spec says so); without it,
  nothing is written and ServerSetupError says how to give it.
  """
  if eula is not True:
    raise ServerSetupError("a dedicated server needs Mojang's EULA (%s) accepted, and only you can accept it: say "
                           "eula = true in the instance spec's [server] table" % EULA_URL)
  if not isinstance(port, int) or not 1024 < port < 65536:
    raise ServerSetupError('a server port is a number from 1025 to 65535, not %r' % (port,))
  players = tuple(players)
  for name in players:
    if not isinstance(name, str) or not NAME.match(name):
      raise ServerSetupError('%r is no player name 1.7.10 takes (letters, digits and _, 1 to 16 of them)' % (name,))
  if len(set(name.lower() for name in players)) != len(players):
    raise ServerSetupError('two players of one name: %s' % ', '.join(players))
  os.makedirs(folder, exist_ok=True)
  lines = ['# unitTAS: written fresh for this run (on 127.0.0.1 only)']
  table = {'1.7.10': PROPERTIES, '1.16.1': PROPERTIES_1_16}.get(minecraft, MODERN_PROPERTIES)
  lines += ['%s=%s' % (key, port if value is None else value) for key, value in table]
  _writeWhole(os.path.join(folder, 'server.properties'), '\n'.join(lines) + '\n')
  _writeWhole(os.path.join(folder, 'eula.txt'), "# accepted by the user, in the instance spec's [server] table (%s)\n"
                                                'eula=true\n' % EULA_URL)
  ops = [{'uuid': _dashed(offlineId(name)), 'name': name, 'level': 4} for name in players]
  _writeWhole(os.path.join(folder, 'ops.json'), json.dumps(ops, indent=2) + '\n')


def awaitServerReady(connection: Connection, stop: Callable[[], Any], seconds: float = READY_SECONDS,
                     since: int = 0, output: Optional[str] = None) -> dict:
  """
  The server's ready event (from the mark 'since'), once it says it
  listens on 127.0.0.1 alone. A server that names any other address, or
  none, is stopped ('stop') before any client joins: ServerSetupError.
  With its 'output' (a file), it is waited for by signs of life: given up
  once 'seconds' pass with nothing new there (LinkTimeout); without, once
  'seconds' pass. Either way, or the server gone first: stopped too, and
  that error.
  """
  try:
    if output is None:
      ready = connection.events.waitFor(lambda event: event.get('event') == 'ready', seconds, since)
    else:
      ready = _readyWhileItWorks(connection, seconds, since, output)
  except BaseException:
    stop()
    raise
  listening = [each for each in ready.get('listening') or () if isinstance(each, dict)]
  said = ['%s:%s' % (each.get('address'), each.get('port')) for each in listening]
  if not listening or any(str(each.get('address')) not in LOOPBACK_FORMS for each in listening):
    stop()
    raise ServerSetupError('the server listens on %s, not on 127.0.0.1 alone: it was stopped before any client joins'
                           % (', '.join(said) or 'nothing it names'))
  return ready


def _readyWhileItWorks(connection: Connection, seconds: float, since: int, output: str) -> dict:
  """The ready event, waited for while the server's output grows; LinkTimeout once it is quiet for 'seconds'."""
  seen = GameOutput(output, ())
  quietSince = time.monotonic()
  while True:
    try:
      return connection.events.waitFor(lambda event: event.get('event') == 'ready', min(1.0, seconds), since)
    except LinkTimeout:
      now = time.monotonic()
      if seen.grew():
        quietSince = now
      if now - quietSince > seconds:
        raise LinkTimeout('the server said nothing new for %s s before its ready (its output: %s)' % (seconds, output))


class ServerGame(LaunchedGame):
  """
  One launch of a dedicated server with the probe in it (SPEC.md 11.3,
  step 2; 19.7 step 10b), in 'folder': its three files (as 'minecraft'
  reads them) made before it starts, 'players' its operators, 'eula' the
  user's own acceptance, 'memory' its -Xmx, on 'port' (a free one unless
  given). A 1.7.10 Forge server's probe is in its mods/ ('mods', the
  probe's jar and a Mixin loader among them); a modern server's is the
  agent ('probe', its jar), as Mojang ships the server or with a loader
  ('loader', 'loaderVersion': Fabric's, SPEC.md 19.7 step 10f). Its
  output is '<results>/<name>/server.log'. 'ready' starts it and lets it
  through only once it says it listens on 127.0.0.1 alone.
  """

  def __init__(self, root: str, results: str, name: str = 'server', folder: Optional[str] = None, mods: Iterable[str] = (),
               players: Iterable[str] = (), eula: bool = False, memory: str = '2G', java: Optional[str] = None,
               sources: Optional[Sources] = None, port: Optional[int] = None, minecraft: str = '1.7.10',
               probe: Optional[str] = None, loader: Optional[str] = None,
               loaderVersion: Optional[str] = None) -> None:
    LaunchedGame.__init__(self, root, results, name)
    self.minecraft = minecraft
    self.loader = loader
    self.loaderVersion = loaderVersion
    self.probe = probe
    self.folder = os.path.abspath(folder or os.path.join(results, name, 'world-folder'))
    self.mods = list(mods)
    self.players = tuple(players)
    self.eula = eula
    self.memory = memory
    self.java = java
    self.sources = sources or Sources()
    self.port = port or freePort()

  def role(self) -> Role:
    return Role.SERVER

  def gameFolder(self) -> str:
    return self.folder

  def outputName(self) -> str:
    return 'server.log'

  def command(self) -> list:
    if self.minecraft == '1.7.10':
      return serverCommand(self.folder, self.java or findJava(), self.sources, self.memory).java
    agents = (self.probe,) if self.probe else ()
    return serverVersionCommand(self.folder, self.java, self.sources, self.minecraft, self.memory, agents=agents,
                                loader=self.loader, loaderVersion=self.loaderVersion).java

  def workingDir(self) -> str:
    #  FML finds mods/ and config/ in the server's working folder
    return self.folder

  def prepare(self) -> None:
    serverFiles(self.folder, self.port, self.players, self.eula, self.minecraft)
    if self.minecraft == '1.7.10' or self.mods:
      putMods(self.folder, self.mods, os.path.join(self.results, 'mods-before-this-run'))

  def worldFolder(self) -> str:
    """The server's world (level-name unittas): removed for a fresh one, which the next start makes again."""
    return os.path.join(self.folder, 'unittas')

  def ready(self, seconds: float = READY_SECONDS) -> tuple:
    """
    Started, its hello welcomed and its ready let through (awaitServerReady, by its output's signs of life, quiet
    for 'seconds' at most): (the connection, the ready event).
    """
    connection = self.start()
    return connection, awaitServerReady(connection, self.stop, seconds, 0,
                                        os.path.join(self.results, self.outputName()))

"""
The 'reset' module puts the player back before a test, in today's order
exactly (PROTOCOL.md section 9.5), the same for one client or for several:

1. client.reset on every client, at once: its screen closed first, since
   an open pause screen stops a singleplayer server;
2. any player outside the overworld brought back (player.reset answers
   'respawned'), and its client waited for until it is there, past the
   terrain screen;
3. one batch on the server side, in one tick: player.reset for every
   player, world.reset, then the mods' resetPlayer hooks;
4. client.reset on every client again, once it is at the start (its
   rain matching the server's clear weather), and three ticks to settle.

- reset: the four steps, on the connections given.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from typing import TYPE_CHECKING

from .errors import GameError, ProbeError, TimedOut, fromWire
from .wire import ErrorType

if TYPE_CHECKING:  # pragma: no cover
  from typing import Iterable, Optional, Sequence

  from .link import Connection

OVERWORLD = 'minecraft:overworld'
#  How long a client may take to arrive back in the overworld, in its ticks (as today's reset allows).
ARRIVE_TICKS = 200


def reset(server: Connection, clients: Optional[Iterable[Connection]] = None,
          at: Sequence[float] = (0.5, 4.0, 0.5), yaw: float = 0.0, pitch: float = 0.0,
          timeout: float = 120.0) -> None:
  """
  The reset, on 'server' (the connection with the server side: in
  singleplayer the one client's own) and 'clients' (each game with a
  client side; by default 'server' alone, singleplayer's case). A mod's
  resetPlayer that throws raises GameError: the player is then not fully
  reset, and the test is an error.
  """
  clients = [server] if clients is None else list(clients)
  for client in clients:
    client.request('client.reset', {'settle_ticks': 0}, timeout=timeout)
  for client in clients:
    #  each client's own player, by the name its hello gave the game's player (offline: the launcher's username)
    name = client.request('player.get', side='client', timeout=timeout)['name']
    args = {'player': name} if len(clients) > 1 else {}
    if server.request('player.get', dict(args), side='server', timeout=timeout)['dimension'] != OVERWORLD:
      if not server.request('player.reset', dict(args), timeout=timeout)['respawned']:
        raise ProbeError(ErrorType.PROBE_ERROR, 'player.reset left the player outside the overworld', {},
                         'player.reset', 0)
      back = client.request('wait.until', {
        'side': 'client', 'op': 'player.get', 'max_ticks': ARRIVE_TICKS,
        'test': {'path': ['dimension'], 'eq': OVERWORLD}}, timeout=timeout)
      if not back['held']:
        raise TimedOut(ErrorType.TIMED_OUT, 'the client didn\'t arrive back in the overworld within %d ticks'
                       % ARRIVE_TICKS, {}, 'reset', 0)
      client.request('wait.until', {
        'side': 'client', 'op': 'screen.get', 'max_ticks': ARRIVE_TICKS,
        'test': {'not': {'path': ['class'], 'contains': 'DownloadTerrain'}}}, timeout=timeout)
  where = {'at': list(at), 'look': {'yaw': yaw, 'pitch': pitch}, 'hooks': 'after'}
  ops = []
  players = [client.request('player.get', side='client', timeout=timeout)['name'] for client in clients]
  for name in players:
    ops.append({'op': 'player.reset', 'args': dict(where, player=name) if len(players) > 1 else dict(where)})
  ops.append({'op': 'world.reset'})
  ops.append({'op': 'hooks.run', 'args': {'hook': 'resetPlayer'}})
  entries = server.request('batch', {'ops': ops}, side='server', timeout=timeout)
  for entry in entries:
    if not entry['ok']:
      raise fromWire(entry['error'], 'reset', 0)
  for plugin in entries[-1]['value']['plugins']:
    if not plugin['ok']:
      error = plugin['error']
      raise GameError(ErrorType.GAME_ERROR, error.get('message', ''), dict(error, plugin=plugin['class']), 'reset', 0)
  #  each client at the start before the last step: after a long move (the first reset after a world opens comes from
  #  the world's own spawn, far off) the server's teleport can reach the client later than the settling ticks, and it
  #  would set back a look the test sets next
  for client in clients:
    there = client.request('wait.until', {
      'side': 'client', 'op': 'player.get', 'max_ticks': ARRIVE_TICKS,
      'test': {'all': [{'path': ['pos', 0], 'eq': at[0]}, {'path': ['pos', 2], 'eq': at[2]}]}}, timeout=timeout)
    if not there['held']:
      raise TimedOut(ErrorType.TIMED_OUT, 'the client wasn\'t at the start within %d ticks: %r' % (
        ARRIVE_TICKS, there['value']['pos']), {}, 'reset', 0)
  for client in clients:
    client.request('client.reset', {'settle_ticks': 3}, timeout=timeout)

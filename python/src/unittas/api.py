"""
The 'api' module is the face of a game a test speaks to (SPEC.md 9.3, step
5): 'Game' over one connection, a helper for each of PROTOCOL.md section
12's rows, each sending the request the protocol names and giving back the
typed value (unittas.values). An error answer comes as the package's own
exception (unittas.errors), whose fields are the error's.

Reflection takes readable names. In a real client (the hello says names:
srg) the path is translated (unittas.mappings) before it goes; in a
development client the readable names are the game's own.

The events a test needs (chat lines, sounds, log lines) are read from a
mark, so each test sees its own.

- CommandResult: what a command said.
- Game: the game.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from worktoy.ezdata import EZData, EZField

from .codec import fromJson, toJson
from .errors import Cancelled, NoResult
from .values import Block, BlockPos, ChatLine, Entity, Inventory, Item, LogLine, Look, Player, Screen, Sound, Vec3

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Optional, Union

  from .link import Connection
  from .mappings import Mappings


class CommandResult(EZData, frozen=True):
  """What command.run gave: the command's result (1 for success in 1.7.10), its chat lines, and the red ones among them."""
  result = EZField[int](0)
  lines = EZField[tuple]()
  errors = EZField[tuple]()


def _vec3(value: Any) -> list:
  return toJson(value if isinstance(value, Vec3) else Vec3(*value))


def _blockPos(value: Any) -> list:
  return toJson(value if isinstance(value, BlockPos) else BlockPos(*value))


def _sided(side: Optional[str]) -> dict:
  return {} if side is None else {'side': side}


class Game:
  """
  One game, through its connection. Each helper's 'side' is the side it
  runs on ('server' or 'client'); left out, the operation's own default
  (PROTOCOL.md 8). 'mappings' translate reflection's readable names in a
  real client; without them, a real client's reflection takes the game's
  own names only.

  'timeout' guards a dead connection only (SPEC.md 9.8): a slow game is the
  probe's to judge, by its stall rule (no tick for 15 s: Stalled), never a
  wall-clock limit here. Running past it is a LinkTimeout, which a
  GameTestCase reports as no result, not as the test's verdict.
  """

  def __init__(self, connection: Connection, mappings: Optional[Mappings] = None, timeout: float = 600.0) -> None:
    self.connection = connection
    self.mappings = mappings
    self.timeout = timeout
    #  the game's crash, once its probe has said so (the 'crash' event: 'summary' and 'report'), else None
    self.crashed = None
    #  why the test is stopped (its time limit, the watcher): every request refused with it, until resume
    self.stopping = None
    self._waiting = set()
    self._lock = threading.Lock()
    connection.events.subscribe(self._heard)

  def _heard(self, event: dict) -> None:
    if event.get('event') == 'crash' and self.crashed is None:
      self.crashed = {'summary': event.get('summary') or 'no summary', 'report': event.get('report')}

  def request(self, op: str, args: Optional[dict] = None, side: Optional[str] = None,
              timeout: Optional[float] = None) -> Any:
    """
    Any operation, as it is: its value, or the package's exception for its
    error. While the test is stopped (stop), NoResult with the reason.
    """
    if self.stopping is not None:
      raise NoResult(self.stopping)
    pending = self.connection.send(op, args or None, side=side)
    with self._lock:
      self._waiting.add(pending)
    try:
      return pending.result(self.timeout if timeout is None else timeout)
    except Cancelled as error:
      if self.stopping is not None:
        raise NoResult(self.stopping) from error
      raise
    finally:
      with self._lock:
        self._waiting.discard(pending)

  def stop(self, why: str) -> None:
    """
    The test is stopped (its time limit, the watcher): what it waits on is
    cancelled, and every request it makes from now on raises NoResult(why),
    until resume. The run's own requests between tests come after resume.
    """
    self.stopping = why
    with self._lock:
      waiting = list(self._waiting)
    for pending in waiting:
      try:
        self.connection.cancel(pending)
      except Exception:  # too late, or the game is past answering: the refusal above still holds
        pass

  def resume(self) -> None:
    self.stopping = None

  # ---------------------------------------------------------------- the session

  def status(self) -> dict:
    return self.request('status')

  def ticks(self, n: int = 1, side: str = 'client', timeout: Optional[float] = None) -> int:
    """Waits n of the side's ticks; the tick it ended at."""
    return self.request('ticks.wait', {'side': side, 'n': n}, timeout=timeout)['tick']

  def waitUntil(self, op: str, args: dict, test: dict, side: str = 'server', maxTicks: int = 200,
                timeout: Optional[float] = None) -> dict:
    """The probe checks the read operation at every tick of the side until the test holds (wait.until): its answer."""
    return self.request('wait.until', {'side': side, 'op': op, 'args': args, 'test': test, 'max_ticks': maxTicks},
                        timeout=timeout)

  def log(self, message: str, level: str = 'info') -> None:
    """A line into the game's log, under unitTAS: a test's edges, for a person reading latest.log."""
    self.request('log.write', {'message': message, 'level': level})

  # ---------------------------------------------------------------- a dedicated server, joined and left (PROTOCOL.md 9.3)

  def join(self, port: int, settleTicks: int = 40, maxSeconds: int = 180) -> int:
    """
    This client joins the dedicated server on 127.0.0.1 at 'port', as
    Direct Connect does, and stands in its world 'settleTicks' client ticks.
    Its milliseconds. Disconnected (with the reason the client was shown)
    when it is refused or kicked; TimedOut past 'maxSeconds'.
    """
    answer = self.request('server.join', {'address': '127.0.0.1', 'port': port, 'settle_ticks': settleTicks,
                                          'max_seconds': maxSeconds}, timeout=maxSeconds + 30)
    return answer['load_ms']

  def leave(self, maxSeconds: int = 60) -> int:
    """This client leaves the server it joined, as the pause menu's Disconnect does; at the title screen then. Its ms."""
    answer = self.request('server.leave', None if maxSeconds == 60 else {'max_seconds': maxSeconds},
                          timeout=maxSeconds + 30)
    return answer['leave_ms']

  # ---------------------------------------------------------------- commands

  def command(self, text: str, side: Optional[str] = None, as_: Optional[str] = None) -> CommandResult:
    """
    A command, as the player (on a dedicated server, the only one in) or,
    with 'as_', as that player by name or as 'server' (the console).
    """
    args = {'command': text}
    if as_ is not None:
      args['as'] = 'server' if as_ == 'server' else {'player': as_}
    said = self.request('command.run', args, side)
    return CommandResult(said.get('result', 0), tuple(said.get('lines', ())), tuple(said.get('errors', ())))

  # ---------------------------------------------------------------- the player

  def player(self, side: Optional[str] = None, name: Optional[str] = None) -> Player:
    """The player: the client's own, or on a server the one named (the only one in, unnamed)."""
    return fromJson(Player, self.request('player.get', None if name is None else {'player': name}, side))

  def playerName(self) -> str:
    """
    A client's own player's name, as its game has it (offline: the name it
    was launched as): its status says it from the title screen on, before
    any world (an older probe's status doesn't: then its player's, in a
    world).
    """
    name = self.request('status').get('player')
    return name if name else self.request('player.get', None, 'client')['name']

  # ---------------------------------------------------------------- players by name, on a server (PROTOCOL.md 9.4)

  def players(self) -> tuple:
    """The players in: each {'name', 'uuid', 'entity', 'dimension', 'pos'}, as players.list gives them."""
    return tuple(self.request('players.list'))

  def kick(self, player: str, reason: str) -> None:
    """The player kicked, as /kick does: its client is shown the reason."""
    self.request('player.kick', {'player': player, 'reason': reason})

  def teleport(self, pos: Any, dimension: Optional[str] = None, look: Optional[Look] = None,
               timeout: Optional[float] = None) -> None:
    args = {'pos': _vec3(pos)}
    if look is not None:
      args['look'] = toJson(look)
    if dimension is not None:
      args['dimension'] = dimension
    self.request('player.teleport', args, timeout=timeout)

  def look(self, yaw: float, pitch: float) -> None:
    self.request('player.look', toJson(Look(yaw, pitch)))

  # ---------------------------------------------------------------- the inventory

  def held(self, side: Optional[str] = None) -> Item:
    return self.slot('held', side)

  def slot(self, name: str, side: Optional[str] = None) -> Item:
    """A slot's stack (main.N, armor.feet ... head, held, cursor); Item.EMPTY for an empty one."""
    return fromJson(Item, self.request('inventory.get', {'slot': name}, side))

  def inventory(self, side: Optional[str] = None) -> Inventory:
    return fromJson(Inventory, self.request('inventory.get', None, side))

  def setSlot(self, name: str, item: Item) -> None:
    self.request('inventory.set', {'slot': name, 'item': toJson(item)})

  # ---------------------------------------------------------------- blocks

  def block(self, pos: Any, tile: bool = False, side: Optional[str] = None) -> Block:
    args = {'pos': _blockPos(pos)}
    if tile:
      args['tile'] = True
    return fromJson(Block, self.request('block.get', args, side))

  def setBlock(self, pos: Any, block: Union[Block, str]) -> None:
    self.request('block.set', {'pos': _blockPos(pos),
                               'block': toJson(block if isinstance(block, Block) else Block(block, 0))})

  # ---------------------------------------------------------------- entities

  def spawn(self, kind: str, pos: Any, nbt: Optional[str] = None) -> Entity:
    args = {'type': kind, 'pos': _vec3(pos)}
    if nbt is not None:
      args['nbt'] = nbt
    return fromJson(Entity, self.request('entity.spawn', args))

  def entity(self, entity: Union[Entity, int], side: Optional[str] = None) -> Entity:
    return fromJson(Entity, self.request('entity.get', {'entity': _entityId(entity)}, side))

  def entities(self, near: Any = 'player', radius: float = 16, type: Optional[str] = None,
               side: Optional[str] = None) -> tuple:
    args = {'near': {'pos': near if near == 'player' else _vec3(near), 'radius': radius}}
    if type is not None:
      args['type'] = type
    return tuple(fromJson(Entity, each) for each in self.request('entity.list', args, side))

  def remove(self, entity: Union[Entity, int]) -> None:
    self.request('entity.remove', {'entity': _entityId(entity)})

  # ---------------------------------------------------------------- input and screens

  def tap(self, key: str) -> None:
    self.request('key.tap', {'key': key})

  def keyDown(self, key: str) -> None:
    self.request('key.down', {'key': key})

  def keyUp(self, key: str) -> None:
    self.request('key.up', {'key': key})

  def screen(self) -> Optional[Screen]:
    return fromJson(Screen, self.request('screen.get'))

  def openScreen(self, screen: Any, **extra: Any) -> None:
    self.request('screen.open', dict(extra, screen=screen))

  def closeScreen(self) -> None:
    self.request('screen.close')

  def type(self, text: str) -> None:
    self.request('screen.type', {'text': text})

  def key(self, name: str) -> None:
    self.request('screen.key', {'key': name})

  def screenshot(self, file: str) -> Any:
    return self.request('screenshot', {'file': file})

  # ---------------------------------------------------------------- reflection

  def path(self, path: list, raw: bool = False) -> list:
    """The path as the game takes it: translated in a real client, unless raw (the game's own names given)."""
    names = self.connection.hello.names
    if raw or names != 'srg' or self.mappings is None:
      return list(path)
    return self.mappings.translate(path)

  def reflect(self, path: list, source: Any = 'player', side: str = 'server', raw: bool = False, as_: str = 'value') -> Any:
    args = {'from': source, 'path': self.path(path, raw)}
    if as_ != 'value':
      args['as'] = as_
    return self.request('reflect.get', args, side)

  def reflectSet(self, path: list, value: Any, source: Any = 'player', side: str = 'server', raw: bool = False) -> None:
    self.request('reflect.set', {'from': source, 'path': self.path(path, raw), 'value': value}, side)

  # ---------------------------------------------------------------- events, per test

  def mark(self) -> int:
    """Where the events are now: the events since it are a test's own."""
    return self.connection.events.mark()

  def _events(self, kind: str, mark: int) -> list:
    return [event for event in self.connection.events.since(mark) if event.get('event') == kind]

  def chat(self, mark: int = 0) -> tuple:
    return tuple(fromJson(ChatLine, event) for event in self._events('chat', mark))

  def sounds(self, mark: int = 0) -> tuple:
    return tuple(fromJson(Sound, event) for event in self._events('sound', mark))

  def logs(self, mark: int = 0) -> tuple:
    return tuple(fromJson(LogLine, event) for event in self._events('log', mark))


def _entityId(entity: Union[Entity, int]) -> int:
  return entity.entity if isinstance(entity, Entity) else int(entity)

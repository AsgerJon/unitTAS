"""
The 'wire' module holds what PROTOCOL.md defines and every other module
speaks: the protocol's closed sets as KeeNums, its lines of JSON, and the
values every message carries (the hello, the ticks of an answer).

- Side, Role, State, ErrorType: the closed sets, each member's value its
  string on the wire, so 'Side("server")' is 'Side.SERVER'.
- encodeLine, decodeLine: one message, one line of UTF-8 JSON (section 3).
- Ticks: each side's tick count when an operation ran, or None.
- Hello: what the probe says of itself when it connects (section 2.2).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING

from worktoy.desc import Field
from worktoy.ezdata import EZData, EZField
from worktoy.keenum import Kee, KeeNum
from worktoy.mcls import BaseObject

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Optional

#  The protocol versions this package speaks (section 2.3).
PROTOCOLS = (1,)
#  The longest line either side sends or takes, newline included (section 3).
MAX_LINE = 16 * 1024 * 1024
#  The only address anything here listens on or dials (section 15).
LOOPBACK = '127.0.0.1'


class Side(KeeNum):
  """The thread an operation runs on, in the game (section 4.1)."""
  CLIENT = Kee[str]('client')
  SERVER = Kee[str]('server')


class Role(KeeNum):
  """What a game is, for its whole life (section 9.1)."""
  CLIENT = Kee[str]('client')
  SERVER = Kee[str]('server')


class State(KeeNum):
  """Where a game is, as 'status' says (section 8.1)."""
  LOADING = Kee[str]('loading')
  MENU = Kee[str]('menu')
  WORLD = Kee[str]('world')
  CHANGING = Kee[str]('changing')
  QUITTING = Kee[str]('quitting')


class ErrorType(KeeNum):
  """The error types an answer can carry (section 6), in the protocol's order."""
  BAD_REQUEST = Kee[str]('BadRequest')
  UNSUPPORTED = Kee[str]('Unsupported')
  NOT_READY = Kee[str]('NotReady')
  NOT_FOUND = Kee[str]('NotFound')
  EXISTS = Kee[str]('Exists')
  GAME_ERROR = Kee[str]('GameError')
  STALLED = Kee[str]('Stalled')
  TIMED_OUT = Kee[str]('TimedOut')
  CANCELLED = Kee[str]('Cancelled')
  DISCONNECTED = Kee[str]('Disconnected')
  PROBE_ERROR = Kee[str]('ProbeError')


def _finite(value: Any) -> Any:
  """The value with every float that isn't finite spelled as the protocol spells it."""
  if isinstance(value, float) and not math.isfinite(value):
    if math.isnan(value):
      return 'NaN'
    return 'Infinity' if value > 0 else '-Infinity'
  if isinstance(value, dict):
    return {key: _finite(item) for key, item in value.items()}
  if isinstance(value, (list, tuple)):
    return [_finite(item) for item in value]
  return value


def encodeLine(message: dict) -> bytes:
  """
  One message as one line: UTF-8 JSON ended by a newline. A newline in a
  value is escaped by JSON, so the line is always whole. Raises
  'ValueError' for a message over the protocol's limit, which is never
  sent.
  """
  text = json.dumps(_finite(message), ensure_ascii=False, separators=(',', ':'), allow_nan=False)
  line = text.encode('utf-8') + b'\n'
  if len(line) > MAX_LINE:
    raise ValueError("a message of %d bytes is over the protocol's limit of 16 MiB a line" % len(line))
  return line


def decodeLine(line: bytes) -> dict:
  """
  The message in one line. Raises 'ValueError' for a line that isn't
  UTF-8 or JSON, or whose JSON isn't an object: every message is one.
  """
  try:
    message = json.loads(line.decode('utf-8'))
  except UnicodeDecodeError as error:
    raise ValueError('the line is not UTF-8: %s' % error) from error
  except json.JSONDecodeError as error:
    raise ValueError('the line is not JSON: %s' % error) from error
  if not isinstance(message, dict):
    raise ValueError('a message is a JSON object; this line is a JSON %s' % type(message).__name__)
  return message


class Ticks(BaseObject):
  """
  Each side's tick count when an operation ran (an answer's 'at'), or
  when an event happened. A side without ticks (no server while no world
  is open) is None.
  """

  client: Field[int] = Field()
  server: Field[int] = Field()

  def __init__(self, client: Optional[int] = None, server: Optional[int] = None) -> None:
    self.__client_ticks__ = client
    self.__server_ticks__ = server

  @client.GET
  def _getClient(self) -> Optional[int]:
    return self.__client_ticks__

  @server.GET
  def _getServer(self) -> Optional[int]:
    return self.__server_ticks__

  @classmethod
  def fromWire(cls, at: Optional[dict]) -> Ticks:
    """The 'at' of a message; a message without one has no ticks."""
    if not isinstance(at, dict):
      return cls()
    client, server = at.get('client'), at.get('server')
    return cls(client if isinstance(client, int) else None, server if isinstance(server, int) else None)

  def __repr__(self) -> str:
    return 'Ticks(client=%r, server=%r)' % (self.client, self.server)


def _take(body: dict, key: str, kind: type, where: str = 'the hello') -> Any:
  """The value under the key, of that kind; 'ValueError' naming what's wrong."""
  if key not in body:
    raise ValueError('%s has no "%s"' % (where, key))
  value = body[key]
  #  a bool is an int to Python, but never a count on the wire
  if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
    raise ValueError('%s\'s "%s" is a %s, not a %s' % (where, key, type(value).__name__, kind.__name__))
  return value


class Hello(EZData, frozen=True):
  """
  What the probe says of itself when it connects (PROTOCOL.md section
  2.2), less its token: the listener checks the token and keeps no copy,
  so a Hello can be shown or logged without it.
  """

  protocol = EZField[tuple]()
  name = EZField[str]('')
  role = EZField[Role](Role.CLIENT)
  probeVersion = EZField[str]('')
  probePort = EZField[str]('')
  minecraft = EZField[str]('')
  loaderName = EZField[str]('')
  loaderVersion = EZField[str]('')
  javaVersion = EZField[str]('')
  names = EZField[str]('')
  development = EZField[bool](False)
  pid = EZField[int](0)
  gameDir = EZField[str]('')
  ops = EZField[tuple]()
  events = EZField[tuple]()

  @classmethod
  def fromWire(cls, body: dict) -> Hello:
    """
    The hello's body as the probe sent it. Fields this package doesn't
    know are ignored (section 1: additive); a field it needs that is
    missing or of the wrong kind raises 'ValueError', naming it.
    """
    probe = _take(body, 'probe', dict)
    loader = _take(body, 'loader', dict)
    java = _take(body, 'java', dict)
    protocol = _take(body, 'protocol', list)
    if not all(isinstance(number, int) and not isinstance(number, bool) for number in protocol):
      raise ValueError('the hello\'s "protocol" is not a list of whole numbers: %r' % (protocol,))
    roleName = _take(body, 'role', str)
    try:
      role = Role(roleName)
    except Exception as error:  # the KeeNum's own resolve error
      raise ValueError('the hello\'s "role" is %r, neither client nor server' % (roleName,)) from error
    return cls(
      tuple(protocol),
      _take(body, 'name', str),
      role,
      _take(probe, 'version', str, 'the hello\'s "probe"'),
      _take(probe, 'port', str, 'the hello\'s "probe"'),
      _take(body, 'minecraft', str),
      _take(loader, 'name', str, 'the hello\'s "loader"'),
      _take(loader, 'version', str, 'the hello\'s "loader"'),
      _take(java, 'version', str, 'the hello\'s "java"'),
      _take(body, 'names', str),
      _take(body, 'development', bool),
      _take(body, 'pid', int),
      _take(body, 'game_dir', str),
      tuple(_take(body, 'ops', list)),
      tuple(_take(body, 'events', list)),
    )

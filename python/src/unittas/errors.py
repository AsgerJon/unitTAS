"""
The 'errors' module holds the exceptions of this package: those of the
connection itself, and one for each error type an answer can carry
(PROTOCOL.md section 6), each named as its type is on the wire.

- UnitTasError: the base of them all.
- LinkError, LinkClosed, LinkTimeout: the connection, not an answer.
- RequestError and its subclasses: an answer that says the operation
  failed, with the error's fields as they came.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from typing import TYPE_CHECKING

from .wire import ErrorType

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Union


class UnitTasError(Exception):
  """The base of every exception this package raises on purpose."""


class LinkError(UnitTasError):
  """The connection to a game, rather than an answer from it."""


class LinkClosed(LinkError):
  """The connection has ended; the message says why."""


class LinkTimeout(LinkError, TimeoutError):
  """Something waited for on the connection didn't come in time."""


class RequestError(UnitTasError):
  """
  An answer that says its operation failed. 'type' is the error's type,
  an ErrorType, or its string as it came when it is a type this package
  doesn't know yet (a later probe's: the protocol only ever adds).
  'fields' are the error's other fields as they came ('side',
  'since_tick_ms', 'trace', ...). 'op' and 'requestId' say which request
  it answers.
  """

  def __init__(self, kind: Union[ErrorType, str], message: str, fields: dict, op: str, requestId: int) -> None:
    self.type = kind
    self.message = message
    self.fields = dict(fields)
    self.op = op
    self.requestId = requestId
    name = kind.value if isinstance(kind, ErrorType) else kind
    super().__init__('%s from %s (request %d): %s' % (name, op, requestId, message))


class BadRequest(RequestError):
  """The request was wrong: the orchestrator's bug."""


class Unsupported(RequestError):
  """This probe lacks the operation, or that argument: a test can skip."""


class NotReady(RequestError):
  """The game isn't where the operation can run."""


class NotFound(RequestError):
  """The handle, id or name names nothing."""


class Exists(RequestError):
  """Something is in the way."""


class GameError(RequestError):
  """The game or a mod threw while the operation ran: its failure, not unitTAS's."""


class Stalled(RequestError):
  """The side stopped ticking."""


class TimedOut(RequestError):
  """An operation's own limit ran out while the game was still alive."""


class Cancelled(RequestError):
  """Cancelled, or not run because an earlier operation in its batch failed."""


class Disconnected(RequestError):
  """A client's connection to its server ended while the operation needed it."""


class ProbeError(RequestError):
  """The probe itself went wrong: unitTAS's problem, not the test's."""


_BY_TYPE = {
  ErrorType.BAD_REQUEST: BadRequest,
  ErrorType.UNSUPPORTED: Unsupported,
  ErrorType.NOT_READY: NotReady,
  ErrorType.NOT_FOUND: NotFound,
  ErrorType.EXISTS: Exists,
  ErrorType.GAME_ERROR: GameError,
  ErrorType.STALLED: Stalled,
  ErrorType.TIMED_OUT: TimedOut,
  ErrorType.CANCELLED: Cancelled,
  ErrorType.DISCONNECTED: Disconnected,
  ErrorType.PROBE_ERROR: ProbeError,
}


def fromWire(error: Any, op: str, requestId: int) -> RequestError:
  """The exception for an answer's 'error', of the class its type names."""
  if not isinstance(error, dict):
    error = {}
  name = error.get('type')
  name = name if isinstance(name, str) else 'unknown'
  message = error.get('message')
  message = message if isinstance(message, str) else ''
  fields = {key: value for key, value in error.items() if key not in ('type', 'message')}
  try:
    kind = ErrorType(name)
  except Exception:  # a type from a later protocol: kept as its string
    return RequestError(name, message, fields, op, requestId)
  return _BY_TYPE[kind](kind, message, fields, op, requestId)

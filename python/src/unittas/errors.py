"""
The 'errors' module holds the exceptions of this package: those of the
connection itself, and one for each error type an answer can carry
(PROTOCOL.md section 6), each named as its type is on the wire.

- UnitTasError: the base of them all.
- LinkError, LinkClosed, LinkTimeout: the connection, not an answer.
- RequestError and its subclasses: an answer that says the operation
  failed, with the error's fields as they came.
- NoResult: no test result could be obtained.
- UnknownVersion: a game whose version mcdex has no release for.
- NoMcdexData: a version mcdex has no data on for a thing's catalogue.
- NoMcdexThing: a thing the game reports that mcdex has no member for.
- NeedFailed, Missing: a test's need the game doesn't meet, a FAIL
  (SPEC.md 13.2, 14.4); Missing is a thing vanilla lacks in that version.
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


class NoResult(UnitTasError):
  """
  No test result could be obtained (SPEC.md 9.8): the game stopped ticking,
  went away, or ran past a wall-clock guard. Not a failure and not an error
  of the test, whose verdict was never reached; its message says so first.
  """

  PREFIX = 'NO TEST RESULT: '

  def __init__(self, why: str) -> None:
    UnitTasError.__init__(self, self.PREFIX + why)
    self.why = why


class UnknownVersion(NoResult):
  """
  The game's version is no release mcdex knows: a snapshot, a version
  never released, or none at all. No mcdex thing has an id there, so a
  test naming one can't reach a verdict on that game (SPEC.md 14.8, M3).

  Attributes
  ----------
  minecraft : str
    The version as the game's hello named it.
  """

  def __init__(self, minecraft: str) -> None:
    import mcdex  # here, not at the top: importing it takes about 0.7 s
    infoSpec = ("mcdex %s knows no release %r, the version this game's "
                "hello names, so no mcdex thing has an id there")
    NoResult.__init__(self, infoSpec % (mcdex.__version__, minecraft))
    self.minecraft = minecraft


#  What ends a test with no result rather than a verdict: the game stuck, gone, or past a wall-clock guard. A mod's
#  code that threw (GameError) is a result: an ERROR.
class NoMcdexData(NoResult):
  """
  mcdex has no data on a thing in the game's version (a particle before
  1.8, say), so whether the game has it can't be told: a test naming it
  there has no result (SPEC.md 14.8, M3).

  Attributes
  ----------
  member : Any
    The mcdex member the test named.
  version : Any
    The game's version, mcdex's member.
  """

  def __init__(self, member: Any, version: Any, why: str) -> None:
    NoResult.__init__(self, '%s.%s: %s' % (type(member).__name__,
                                           member.name, why))
    self.member = member
    self.version = version


class NoMcdexThing(NoResult):
  """
  A thing the game reports that mcdex has no member for in its version
  (1.7.10's lit furnace, say): whether it's the member a test asserts
  can't be told, and the game may well be right, so the test has no
  result (SPEC.md 14.8, M6).

  Attributes
  ----------
  text : str
    The thing as the game reported it.
  version : Any
    The game's version, mcdex's member.
  """

  def __init__(self, text: str, version: Any, member: Any) -> None:
    infoSpec = """mcdex knows no thing by %s in %s, so whether it's %s.%s
    can't be told"""
    info = infoSpec % (text, version.value, type(member).__name__,
                       member.name)
    NoResult.__init__(self, ' '.join(info.split()))
    self.text = text
    self.version = version


class NeedFailed(UnitTasError, AssertionError):
  """
  Something a test needs that the game doesn't meet: a FAIL, saying which
  need and why (SPEC.md 13.2, 14.4). unittest counts an AssertionError as
  a failure, not an error.
  """


class Missing(NeedFailed):
  """
  A thing vanilla lacks in the game's version, by mcdex's own answer
  (NotInVersion), which the message gives: 'MCItems.Elytra: Vanilla
  1.7.10 has no 'elytra'; vanilla added it in 1.9!'.

  Attributes
  ----------
  member : Any
    The mcdex member the test named.
  version : Any
    The game's version, mcdex's member.
  """

  def __init__(self, member: Any, version: Any, why: str) -> None:
    NeedFailed.__init__(self, '%s.%s: %s' % (type(member).__name__,
                                             member.name, why))
    self.member = member
    self.version = version


NO_RESULT_ERRORS = (Stalled, TimedOut, LinkError)


def whyNoResult(error: BaseException) -> str:
  """What a no-result error says happened, for the report."""
  if isinstance(error, Stalled):
    return 'the game stopped ticking: %s' % error
  if isinstance(error, TimedOut):
    return 'a wall-clock guard ran out: %s' % error
  return 'the game is gone, or doesn\'t answer: %s' % error

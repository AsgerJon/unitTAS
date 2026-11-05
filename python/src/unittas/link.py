"""
The 'link' module is the orchestrator's end of PROTOCOL.md: it listens,
writes each game's start file, takes the hello, and then carries
requests, answers and events over one connection per game.

- Listener: listens on 127.0.0.1 alone; 'prepare' writes a game's start
  file with a token new for that launch; 'accept' welcomes the game whose
  hello brings that token and refuses anything else.
- Connection: one game. 'send' a request and get a Pending, 'request'
  and wait for its value; 'events' keeps what the game pushes.
- Pending: one request in flight; 'result' waits for its answer.
- EventLog: the events of one connection, in the order they came.

The game never listens (section 0): it dials this listener. Nothing here
binds or dials any address but 127.0.0.1 (section 15).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import hmac
import itertools
import os
import re
import secrets
import socket
import threading
import time
from typing import TYPE_CHECKING

from worktoy.desc import AttriBox, Field
from worktoy.mcls import BaseObject

from . import __version__
from .errors import LinkClosed, LinkTimeout, fromWire
from .wire import Hello, LOOPBACK, MAX_LINE, PROTOCOLS, Role, Side, Ticks
from .wire import decodeLine, encodeLine

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Callable, Optional, Union

#  A game's name goes into its start file, and later into file names: kept plain.
_NAME = re.compile(r'^[A-Za-z0-9_.-]{1,64}$')


class Expected(BaseObject):
  """
  A game the listener waits for: its name, its role, and the start file
  written for it. The token lives only in that file and in here, and is
  never part of what an Expected shows.
  """

  name: Field[str] = Field()
  role: Field[Role] = Field()
  startFile: Field[str] = Field()

  def __init__(self, name: str, role: Role, startFile: str, token: str) -> None:
    self.__game_name__ = name
    self.__game_role__ = role
    self.__start_file__ = startFile
    self.__token__ = token

  @name.GET
  def _getName(self) -> str:
    return self.__game_name__

  @role.GET
  def _getRole(self) -> Role:
    return self.__game_role__

  @startFile.GET
  def _getStartFile(self) -> str:
    return self.__start_file__

  def matches(self, token: Any) -> bool:
    """Whether the token is this game's, compared in constant time."""
    return isinstance(token, str) and hmac.compare_digest(token.encode('utf-8'), self.__token__.encode('utf-8'))

  def removeStartFile(self) -> None:
    """The start file gone, if it is still there: a later game must not find it."""
    try:
      os.remove(self.__start_file__)
    except FileNotFoundError:
      pass

  def __repr__(self) -> str:
    return 'Expected(%r, %s, %r)' % (self.name, self.role.value, self.startFile)

  __str__ = __repr__


class EventLog(BaseObject):
  """
  The events of one connection, in the order they came. 'mark' is where
  the log stands now, 'since' gives what came after a mark, 'waitFor'
  waits for an event a predicate likes, and 'subscribe' hears each one as
  it comes (on the connection's reading thread: keep it short).
  """

  def __init__(self) -> None:
    self.__events__ = []
    self.__subscribers__ = []
    self.__condition__ = threading.Condition()
    self.__ended__ = None
    self.subscriberErrors = []

  def add(self, event: dict) -> None:
    with self.__condition__:
      self.__events__.append(event)
      self.__condition__.notify_all()
    for subscriber in list(self.__subscribers__):
      try:
        subscriber(event)
      except Exception as error:  # a subscriber's bug must not stop the reading
        self.subscriberErrors.append(error)

  def end(self, reason: str) -> None:
    """No more events will come: waiters stop waiting."""
    with self.__condition__:
      self.__ended__ = reason
      self.__condition__.notify_all()

  def mark(self) -> int:
    with self.__condition__:
      return len(self.__events__)

  def since(self, mark: int = 0) -> list:
    with self.__condition__:
      return list(self.__events__[mark:])

  def subscribe(self, subscriber: Callable[[dict], Any]) -> None:
    self.__subscribers__.append(subscriber)

  def waitFor(self, predicate: Callable[[dict], bool], timeout: float, since: int = 0) -> dict:
    """
    The first event from the mark 'since' on (the whole log by default)
    that the predicate likes, waiting up to 'timeout' seconds for it.
    """
    deadline = time.monotonic() + timeout
    index = since
    with self.__condition__:
      while True:
        while index < len(self.__events__):
          event = self.__events__[index]
          index += 1
          if predicate(event):
            return event
        if self.__ended__ is not None:
          raise LinkClosed('the event waited for never came: %s' % self.__ended__)
        left = deadline - time.monotonic()
        if left <= 0:
          raise LinkTimeout('the event waited for didn\'t come within %s s' % timeout)
        self.__condition__.wait(left)


class Pending(BaseObject):
  """One request in flight: its id and operation; 'result' waits for its answer."""

  id: Field[int] = Field()
  op: Field[str] = Field()
  done: Field[bool] = Field()
  at: Field[Ticks] = Field()
  warnings: Field[list] = Field()

  def __init__(self, requestId: int, op: str) -> None:
    self.__request_id__ = requestId
    self.__op__ = op
    self.__answered__ = threading.Event()
    self.__answer__ = None
    self.__closed_because__ = None

  @id.GET
  def _getId(self) -> int:
    return self.__request_id__

  @op.GET
  def _getOp(self) -> str:
    return self.__op__

  @done.GET
  def _getDone(self) -> bool:
    return self.__answered__.is_set()

  @at.GET
  def _getAt(self) -> Optional[Ticks]:
    answer = self.__answer__
    return None if answer is None else Ticks.fromWire(answer.get('at'))

  @warnings.GET
  def _getWarnings(self) -> list:
    answer = self.__answer__
    found = [] if answer is None else answer.get('warnings')
    return list(found) if isinstance(found, list) else []

  def answered(self, answer: dict) -> None:
    self.__answer__ = answer
    self.__answered__.set()

  def closed(self, reason: str) -> None:
    self.__closed_because__ = reason
    self.__answered__.set()

  def result(self, timeout: Optional[float] = None) -> Any:
    """
    The answer's value, waiting up to 'timeout' seconds (None: until the
    answer or the connection's end). An error answer raises its
    exception; a connection that ended raises LinkClosed.
    """
    if not self.__answered__.wait(timeout):
      raise LinkTimeout('no answer to %s (request %d) within %s s' % (self.op, self.id, timeout))
    if self.__answer__ is None:
      raise LinkClosed('%s (request %d) got no answer: %s' % (self.op, self.id, self.__closed_because__))
    if self.__answer__.get('ok') is True:
      return self.__answer__.get('value')
    raise fromWire(self.__answer__.get('error'), self.op, self.id)


class Connection(BaseObject):
  """
  One game, welcomed. Requests go out with ids of their own and their
  answers come back in any order; events are kept in 'events'. A
  connection that ends (the game hung up, broke the protocol, or 'close'
  was called) fails every request still waiting, with the reason.
  """

  hello: Field[Hello] = Field()
  name: Field[str] = Field()
  protocol: Field[int] = Field()
  events: Field[EventLog] = Field()
  closed: Field[bool] = Field()
  closedBecause: Field[str] = Field()

  def __init__(self, sock: socket.socket, reader: Any, hello: Hello, protocol: int) -> None:
    self.__socket__ = sock
    self.__reader__ = reader
    self.__hello__ = hello
    self.__protocol__ = protocol
    self.__event_log__ = EventLog()
    self.__ids__ = itertools.count(1)
    self.__lock__ = threading.Lock()
    self.__pending__ = {}
    self.__ended__ = threading.Event()
    self.__reason__ = None
    self.strays = 0
    self.__thread__ = threading.Thread(target=self._read, name='unittas link %s' % hello.name, daemon=True)
    self.__thread__.start()

  @hello.GET
  def _getHello(self) -> Hello:
    return self.__hello__

  @name.GET
  def _getName(self) -> str:
    return self.__hello__.name

  @protocol.GET
  def _getProtocol(self) -> int:
    return self.__protocol__

  @events.GET
  def _getEvents(self) -> EventLog:
    return self.__event_log__

  @closed.GET
  def _getClosed(self) -> bool:
    return self.__ended__.is_set()

  @closedBecause.GET
  def _getClosedBecause(self) -> Optional[str]:
    return self.__reason__

  def send(self, op: str, args: Optional[dict] = None, side: Union[Side, str, None] = None) -> Pending:
    """
    Sends the request and returns at once; the Pending waits for the
    answer. A request over the protocol's line limit raises ValueError
    and is never sent.
    """
    if self.closed:
      raise LinkClosed('%s not sent: %s' % (op, self.__reason__))
    requestId = next(self.__ids__)
    message = {'id': requestId, 'op': op}
    if side is not None:
      message['side'] = (side if isinstance(side, Side) else Side(side)).value
    if args:
      message['args'] = args
    line = encodeLine(message)
    pending = Pending(requestId, op)
    with self.__lock__:
      if self.__ended__.is_set():
        raise LinkClosed('%s not sent: %s' % (op, self.__reason__))
      self.__pending__[requestId] = pending
      try:
        self.__socket__.sendall(line)
      except OSError as error:
        self.__pending__.pop(requestId, None)
        failure = 'the connection failed while sending: %s' % error
      else:
        failure = None
    if failure is not None:
      self._end(failure)
      raise LinkClosed('%s not sent: %s' % (op, failure))
    return pending

  def request(self, op: str, args: Optional[dict] = None, side: Union[Side, str, None] = None,
              timeout: Optional[float] = None) -> Any:
    """Sends the request and waits for its value (see Pending.result)."""
    return self.send(op, args, side).result(timeout)

  def cancel(self, pending: Pending, timeout: float = 10.0) -> bool:
    """Asks the game to cancel the request; whether it got there in time (section 4.6)."""
    answer = self.request('cancel', {'id': pending.id}, timeout=timeout)
    return bool(isinstance(answer, dict) and answer.get('cancelled'))

  def close(self) -> None:
    """Ends the connection from this side; the game then quits (section 10)."""
    self._end('closed by this side')

  def _end(self, reason: str) -> None:
    with self.__lock__:
      if self.__ended__.is_set():
        return
      self.__reason__ = reason
      self.__ended__.set()
      waiting = list(self.__pending__.values())
      self.__pending__.clear()
    for pending in waiting:
      pending.closed(reason)
    self.__event_log__.end(reason)
    try:
      self.__socket__.shutdown(socket.SHUT_RDWR)
    except OSError:
      pass
    self.__socket__.close()

  def _read(self) -> None:
    """The reading thread: every line the game sends, until the connection ends."""
    while True:
      try:
        line = self.__reader__.readline(MAX_LINE + 1)
      except (OSError, ValueError) as error:
        self._end('the connection failed: %s' % error)
        return
      if not line:
        self._end('the game closed the connection')
        return
      if not line.endswith(b'\n'):
        if len(line) > MAX_LINE:
          self._end("the game sent a line over the protocol's limit of 16 MiB")
        else:
          self._end('the game closed the connection in the middle of a line')
        return
      try:
        message = decodeLine(line)
      except ValueError as error:
        self._end('the game sent a line that is not a JSON object (%s)' % error)
        return
      if 'event' in message:
        self.__event_log__.add(message)
      elif 'id' in message and 'ok' in message:
        with self.__lock__:
          pending = self.__pending__.pop(message['id'], None)
        if pending is None:
          self.strays += 1
        else:
          pending.answered(message)
      #  anything else is a message of a later protocol: ignored (section 1)


class Listener(BaseObject):
  """
  Listens on 127.0.0.1 for the games this orchestrator starts. For each,
  'prepare' writes its start file with a token new for that launch, and
  'accept' welcomes the game whose hello brings it. A connection with a
  wrong token, no common protocol or a broken hello is refused and
  closed, and accept goes on waiting.
  """

  host: Field[str] = Field()
  port: Field[int] = Field()
  helloTimeout = AttriBox[float](10.0)

  def __init__(self) -> None:
    self.__server__ = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.__server__.bind((LOOPBACK, 0))
    self.__server__.listen(8)
    self.__expected__ = []
    self.__lock__ = threading.Lock()

  @host.GET
  def _getHost(self) -> str:
    return self.__server__.getsockname()[0]

  @port.GET
  def _getPort(self) -> int:
    return self.__server__.getsockname()[1]

  def prepare(self, gameDir: str, name: str = 'game', role: Role = Role.CLIENT) -> Expected:
    """
    Writes the game's start file, 'unittas/probe.properties' in its
    folder, readable by the user alone, and waits for that game from now.
    """
    if not isinstance(name, str) or not _NAME.match(name):
      raise ValueError('a game\'s name is 1 to 64 letters, digits, "_", "." or "-": not %r' % (name,))
    role = role if isinstance(role, Role) else Role(role)
    token = secrets.token_hex(32)
    folder = os.path.join(gameDir, 'unittas')
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, 'probe.properties')
    text = 'connect=%s:%d\ntoken=%s\nprotocol=%s\nname=%s\nrole=%s\n' % (
      LOOPBACK, self.port, token, ','.join(str(number) for number in PROTOCOLS), name, role.value)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
      #  an older file with looser permissions keeps them through O_CREAT: set them again
      os.fchmod(descriptor, 0o600)
      os.write(descriptor, text.encode('utf-8'))
    finally:
      os.close(descriptor)
    expected = Expected(name, role, path, token)
    with self.__lock__:
      self.__expected__.append(expected)
    return expected

  def accept(self, timeout: float = 30.0, helloTimeout: Optional[float] = None) -> Connection:
    """
    The next prepared game to connect, welcomed. Raises LinkTimeout when
    none has within 'timeout' seconds, naming what was refused meanwhile.
    A connection gets 'helloTimeout' seconds to send its hello.
    """
    helloTimeout = self.helloTimeout if helloTimeout is None else helloTimeout
    deadline = time.monotonic() + timeout
    refused = []
    while True:
      left = deadline - time.monotonic()
      if left <= 0:
        detail = '; refused meanwhile: %s' % '; '.join(refused) if refused else ''
        raise LinkTimeout('no game connected within %s s%s' % (timeout, detail))
      self.__server__.settimeout(left)
      try:
        sock, _ = self.__server__.accept()
      except socket.timeout:
        continue
      connection = self._welcome(sock, min(helloTimeout, max(left, 0.01)), refused)
      if connection is not None:
        return connection

  def _welcome(self, sock: socket.socket, helloTimeout: float, refused: list) -> Optional[Connection]:
    sock.settimeout(helloTimeout)
    reader = sock.makefile('rb')
    try:
      line = reader.readline(MAX_LINE + 1)
    except (socket.timeout, OSError):
      return self._refuse(sock, 'a connection that sent no hello within %s s' % helloTimeout, refused, answer=False)
    if not line:
      return self._refuse(sock, 'a connection that closed before its hello', refused, answer=False)
    try:
      message = decodeLine(line)
    except ValueError as error:
      return self._refuse(sock, 'not a hello: %s' % error, refused)
    body = message.get('hello')
    if not isinstance(body, dict):
      return self._refuse(sock, 'the first line is not a hello', refused)
    with self.__lock__:
      expected = next((each for each in self.__expected__ if each.matches(body.get('token'))), None)
    if expected is None:
      return self._refuse(sock, 'a wrong token: no game this orchestrator started has it', refused)
    theirs = body.get('protocol')
    theirs = [number for number in theirs if isinstance(number, int)] if isinstance(theirs, list) else []
    common = set(theirs) & set(PROTOCOLS)
    if not common:
      return self._refuse(sock, 'the probe speaks protocol %s; this unittas speaks %s: update one of them' % (
        sorted(theirs), list(PROTOCOLS)), refused)
    try:
      hello = Hello.fromWire(body)
    except ValueError as error:
      return self._refuse(sock, 'a broken hello: %s' % error, refused)
    if hello.name != expected.name:
      return self._refuse(sock, 'the hello names the game %r; its token is %r\'s' % (hello.name, expected.name), refused)
    protocol = max(common)
    try:
      sock.sendall(encodeLine({'welcome': {'protocol': protocol, 'orchestrator': 'unittas %s' % __version__}}))
    except OSError as error:
      refused.append('%s: the welcome couldn\'t be sent (%s)' % (expected.name, error))
      sock.close()
      return None
    with self.__lock__:
      self.__expected__.remove(expected)
    #  the probe deletes its start file when it reads it; this makes sure
    expected.removeStartFile()
    sock.settimeout(None)
    return Connection(sock, reader, hello, protocol)

  @staticmethod
  def _refuse(sock: socket.socket, reason: str, refused: list, answer: bool = True) -> None:
    refused.append(reason)
    if answer:
      try:
        sock.sendall(encodeLine({'refused': {'reason': reason}}))
      except OSError:
        pass
    try:
      sock.shutdown(socket.SHUT_RDWR)
    except OSError:
      pass
    sock.close()
    return None

  def close(self) -> None:
    """Stops listening, and removes the start files of games that never came."""
    with self.__lock__:
      waiting = list(self.__expected__)
      self.__expected__.clear()
    for expected in waiting:
      expected.removeStartFile()
    self.__server__.close()

  def __enter__(self) -> Listener:
    return self

  def __exit__(self, *_: Any) -> None:
    self.close()

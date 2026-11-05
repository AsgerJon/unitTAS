"""
FakeProbe speaks the probe's side of the protocol (PROTOCOL.md) over a real
socket, for the tests that need no game. It reads the start file as the
probe does, dials, sends its hello, and then does what a test tells it:
read a request, answer it, push an event, send raw bytes, hang up. It is
written apart from 'unittas' on purpose, from the protocol's text, so that
the tests check the package against the protocol and not against itself.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import json
import socket
import threading
from typing import Any, Optional

HELLO = {
  'probe': {'version': '0.2.0', 'port': '1.7.10-forge'},
  'minecraft': '1.7.10',
  'loader': {'name': 'forge', 'version': '10.13.4.1614'},
  'java': {'version': '1.8.0_442', 'max_memory_mb': 2048},
  'names': 'mcp',
  'development': True,
  'pid': 4242,
  'game_dir': '/somewhere/run/client',
  'ops': ['status', 'quit', 'ticks.wait'],
  'events': ['chat', 'log'],
}


def readStartFile(path: str) -> dict:
  """The start file's keys and values, as the probe reads them."""
  values = {}
  with open(path, encoding='utf-8') as file:
    for line in file:
      line = line.split('#', 1)[0].strip()
      if '=' in line:
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip()
  return values


class FakeProbe:
  """
  One fake game. 'connect' dials the address in the start file and sends
  the hello (the token from the file unless 'token' says otherwise, extra
  fields merged in from 'extra'); it returns the orchestrator's first
  line, the welcome or the refusal.
  """

  def __init__(self, startFile, *, token: Optional[str] = None,
               protocol: tuple = (1,), extra: Optional[dict] = None,
               leave: tuple = ()) -> None:
    #  the start file's path, or its values already read (the file is gone once a game is in)
    self.start = dict(startFile) if isinstance(startFile, dict) else readStartFile(startFile)
    self.token = self.start['token'] if token is None else token
    self.protocol = list(protocol)
    self.extra = dict(extra or {})
    self.leave = leave
    self.sock: Optional[socket.socket] = None
    self.reader = None
    self.lock = threading.Lock()

  def hello(self) -> dict:
    """The hello this fake sends, with the fields 'leave' names left out."""
    body = dict(HELLO)
    body.update({
      'protocol': self.protocol,
      'token': self.token,
      'name': self.start.get('name', 'game'),
      'role': self.start.get('role', 'client'),
    })
    body.update(self.extra)
    for key in self.leave:
      body.pop(key, None)
    return {'hello': body}

  def dial(self) -> None:
    """Only the connection, nothing sent: a stray client."""
    host, port = self.start['connect'].rsplit(':', 1)
    self.sock = socket.create_connection((host, int(port)), timeout=10)
    self.reader = self.sock.makefile('rb')

  def connect(self) -> dict:
    """Dials, sends the hello, returns the first line back."""
    self.dial()
    self.send(self.hello())
    return self.read(10)

  def send(self, message: dict) -> None:
    self.sendRaw((json.dumps(message) + '\n').encode('utf-8'))

  def sendRaw(self, data: bytes) -> None:
    with self.lock:
      self.sock.sendall(data)

  def read(self, timeout: float) -> Any:
    """The next line from the orchestrator, decoded; None when it hung up."""
    self.sock.settimeout(timeout)
    line = self.reader.readline()
    if not line:
      return None
    return json.loads(line)

  def readRequest(self, timeout: float = 5.0) -> dict:
    request = self.read(timeout)
    if request is None:
      raise AssertionError('the orchestrator hung up instead of sending a request')
    return request

  def answer(self, request: dict, value: Any = None, *,
             error: Optional[dict] = None, at: Optional[dict] = None,
             extra: Optional[dict] = None) -> None:
    """Answers the request: its value, or the error when one is given."""
    message = {'id': request['id'], 'at': at or {'client': 10, 'server': 9}}
    if error is None:
      message.update({'ok': True, 'value': value})
    else:
      message.update({'ok': False, 'error': error})
    message.update(extra or {})
    self.send(message)

  def event(self, kind: str, **fields: Any) -> None:
    message = {'event': kind, 'at': {'client': 11, 'server': 10}}
    message.update(fields)
    self.send(message)

  def serve(self, handlers: dict) -> list:
    """
    Answers requests on a thread of its own until the orchestrator hangs
    up: each by its op's handler, a function of (args, side) that returns
    the value, or raises FakeError(type, message, **fields) for an error.
    An op with no handler is Unsupported. Returns the list the requests are
    recorded in, as they come.
    """
    asked = []

    def run() -> None:
      while True:
        try:
          request = self.read(30)
        except (OSError, ValueError):
          return
        if request is None:
          return
        asked.append(request)
        handler = handlers.get(request.get('op'))
        try:
          if handler is None:
            self.answer(request, error={'type': 'Unsupported', 'message': 'no operation %s' % request.get('op')})
            continue
          try:
            self.answer(request, handler(request.get('args') or {}, request.get('side')))
          except FakeError as failure:
            self.answer(request, error=dict(failure.fields, type=failure.kind, message=failure.message))
          except OSError:
            raise
          except Exception as failure:  # a handler's own bug answers, so a test never waits for a fake that died
            self.answer(request, error={'type': 'ProbeError', 'message': 'the fake\'s handler failed: %r' % failure})
        except OSError:  # the fake hung up (a handler closed it, as a game that crashed): nothing more to serve
          return

    threading.Thread(target=run, daemon=True).start()
    return asked

  def close(self) -> None:
    if self.sock is not None:
      try:
        self.sock.shutdown(socket.SHUT_RDWR)
      except OSError:
        pass
      self.sock.close()


class FakeError(Exception):
  """An error a served handler answers with: its type, message and fields, as PROTOCOL.md 6 has them."""

  def __init__(self, kind: str, message: str, **fields: Any) -> None:
    Exception.__init__(self, message)
    self.kind = kind
    self.message = message
    self.fields = fields


def inThread(target, *args) -> tuple:
  """Runs target(*args) on a thread of its own; returns (thread, result box)."""
  box = {}

  def run() -> None:
    try:
      box['value'] = target(*args)
    except BaseException as exception:  # the test reads it from the box
      box['error'] = exception

  thread = threading.Thread(target=run, daemon=True)
  thread.start()
  return thread, box

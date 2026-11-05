"""
Tests of unittas.link against FakeProbe: the listener and its start file,
the hello and the welcome or refusal, requests and their answers, events,
and the connection's end. No game: a real socket on 127.0.0.1.

  python -m unittest discover -s python/tests/unit
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import re
import shutil
import stat
import tempfile
import time
import unittest

from fakeprobe import FakeProbe, inThread, readStartFile
from unittas.errors import LinkClosed, LinkTimeout, RequestError, Stalled
from unittas.link import Listener
from unittas.wire import ErrorType, MAX_LINE, Role, Side


class _LinkTest(unittest.TestCase):
  """A listener and a game folder for each test, both gone after it."""

  def setUp(self) -> None:
    self.folder = tempfile.mkdtemp(prefix='unittas-link-')
    self.listener = Listener()
    self.addCleanup(shutil.rmtree, self.folder, True)
    self.addCleanup(self.listener.close)

  def expect(self, name: str = 'alice', role: Role = Role.CLIENT):
    return self.listener.prepare(self.folder, name, role)

  def connected(self, **fakeOptions) -> tuple:
    """A fake game, welcomed: (connection, fake)."""
    self.expected = self.expect()
    self.startValues = readStartFile(self.expected.startFile)
    fake = FakeProbe(self.expected.startFile, **fakeOptions)
    thread, box = inThread(fake.connect)
    connection = self.listener.accept(timeout=10)
    thread.join(10)
    self.addCleanup(connection.close)
    self.addCleanup(fake.close)
    self.assertIn('welcome', box.get('value') or {}, box)
    return connection, fake


class StartFileTests(_LinkTest):

  def test_the_listener_is_on_loopback_only(self) -> None:
    self.assertEqual('127.0.0.1', self.listener.host)
    self.assertGreater(self.listener.port, 0)

  def test_written_for_the_user_alone(self) -> None:
    expected = self.expect()
    self.assertEqual(os.path.join(self.folder, 'unittas', 'probe.properties'), expected.startFile)
    mode = stat.S_IMODE(os.stat(expected.startFile).st_mode)
    self.assertEqual(0o600, mode, oct(mode))

  def test_what_it_says(self) -> None:
    expected = self.expect('bob', Role.SERVER)
    values = readStartFile(expected.startFile)
    self.assertEqual('127.0.0.1:%d' % self.listener.port, values['connect'])
    self.assertRegex(values['token'], r'^[0-9a-f]{64}$')
    self.assertEqual('1', values['protocol'])
    self.assertEqual('bob', values['name'])
    self.assertEqual('server', values['role'])

  def test_a_new_token_each_launch(self) -> None:
    first = readStartFile(self.expect().startFile)['token']
    second = readStartFile(self.expect().startFile)['token']
    self.assertNotEqual(first, second)

  def test_gone_once_the_game_is_in(self) -> None:
    self.connected()
    self.assertFalse(os.path.exists(self.expected.startFile))

  def test_an_unused_start_file_is_removed_at_close(self) -> None:
    expected = self.expect()
    self.listener.close()
    self.assertFalse(os.path.exists(expected.startFile), 'a game started later would dial a listener that is gone')

  def test_a_name_that_could_break_the_file_is_refused(self) -> None:
    for name in ('two\nlines', 'a=b', '', 'x' * 65):
      with self.subTest(name=name):
        with self.assertRaises(ValueError):
          self.expect(name)

  def test_the_token_never_shows(self) -> None:
    expected = self.expect()
    token = readStartFile(expected.startFile)['token']
    self.assertNotIn(token, repr(expected))
    self.assertNotIn(token, str(expected))


class HelloTests(_LinkTest):

  def test_welcomed(self) -> None:
    connection, fake = self.connected()
    self.assertEqual('alice', connection.name)
    self.assertEqual('1.7.10', connection.hello.minecraft)
    self.assertIs(Role.CLIENT, connection.hello.role)
    self.assertFalse(connection.closed)

  def test_the_welcome_names_the_protocol(self) -> None:
    expected = self.expect()
    fake = FakeProbe(expected.startFile, protocol=(1, 2))
    thread, box = inThread(fake.connect)
    connection = self.listener.accept(timeout=10)
    thread.join(10)
    self.addCleanup(connection.close)
    self.addCleanup(fake.close)
    self.assertEqual(1, box['value']['welcome']['protocol'])
    self.assertRegex(box['value']['welcome']['orchestrator'], r'^unittas ')

  def refused(self, **fakeOptions) -> dict:
    """What a fake with these options is told; the listener then times out, naming the refusal."""
    expected = self.expect()
    fake = FakeProbe(expected.startFile, **fakeOptions)
    self.addCleanup(fake.close)
    thread, box = inThread(fake.connect)
    with self.assertRaises(LinkTimeout) as caught:
      self.listener.accept(timeout=2)
    thread.join(10)
    self.assertIn('refused', str(caught.exception))
    answer = box.get('value')
    self.assertIn('refused', answer or {}, box)
    self.assertIsNone(fake.read(5), 'the connection stays open after a refusal')
    return answer['refused']

  def test_a_wrong_token_is_refused(self) -> None:
    refusal = self.refused(token='0' * 64)
    self.assertIn('token', refusal['reason'])
    self.assertNotIn('0' * 64, refusal['reason'])

  def test_no_common_protocol_is_refused(self) -> None:
    refusal = self.refused(protocol=(2,))
    self.assertIn('[2]', refusal['reason'])
    self.assertIn('[1]', refusal['reason'])

  def test_a_hello_missing_a_field_is_refused(self) -> None:
    refusal = self.refused(leave=('minecraft',))
    self.assertIn('minecraft', refusal['reason'])

  def test_a_token_is_good_for_one_launch(self) -> None:
    connection, fake = self.connected()
    again = FakeProbe(self.startValues, token=fake.token)
    self.addCleanup(again.close)
    thread, box = inThread(again.connect)
    with self.assertRaises(LinkTimeout):
      self.listener.accept(timeout=2)
    thread.join(10)
    self.assertIn('refused', box.get('value') or {}, box)

  def test_a_silent_client_is_dropped_and_the_game_still_gets_in(self) -> None:
    expected = self.expect()
    stray = FakeProbe(expected.startFile)
    self.addCleanup(stray.close)
    stray.dial()
    fake = FakeProbe(expected.startFile)
    self.addCleanup(fake.close)

    def later() -> dict:
      time.sleep(0.5)
      return fake.connect()

    thread, box = inThread(later)
    connection = self.listener.accept(timeout=10, helloTimeout=1)
    self.addCleanup(connection.close)
    thread.join(10)
    self.assertIn('welcome', box.get('value') or {}, box)

  def test_unknown_fields_in_the_hello_are_ignored(self) -> None:
    connection, fake = self.connected(extra={'colour': 'green', 'future': {'a': 1}})
    self.assertEqual('alice', connection.name)


class RequestTests(_LinkTest):

  def test_a_request_and_its_answer(self) -> None:
    connection, fake = self.connected()
    pending = connection.send('block.get', {'pos': [3, 4, 5]}, side=Side.SERVER)
    request = fake.readRequest()
    self.assertEqual({'id': pending.id, 'op': 'block.get', 'side': 'server', 'args': {'pos': [3, 4, 5]}}, request)
    fake.answer(request, {'id': 'minecraft:stone', 'meta': 0}, at={'client': 50, 'server': 48})
    self.assertEqual({'id': 'minecraft:stone', 'meta': 0}, pending.result(5))
    self.assertEqual((50, 48), (pending.at.client, pending.at.server))

  def test_no_side_and_no_args_are_left_out(self) -> None:
    connection, fake = self.connected()
    connection.send('status')
    self.assertEqual({'id', 'op'}, set(fake.readRequest()))

  def test_ids_are_positive_and_never_repeat(self) -> None:
    connection, fake = self.connected()
    ids = [connection.send('status').id for _ in range(50)]
    self.assertEqual(len(ids), len(set(ids)))
    self.assertTrue(all(isinstance(number, int) and number > 0 for number in ids))

  def test_answers_in_any_order(self) -> None:
    connection, fake = self.connected()
    first = connection.send('ticks.wait', {'n': 20})
    second = connection.send('status')
    one, two = fake.readRequest(), fake.readRequest()
    fake.answer(two, {'state': 'world'})
    fake.answer(one, {'waited_ms': 1000})
    self.assertEqual({'state': 'world'}, second.result(5))
    self.assertEqual({'waited_ms': 1000}, first.result(5))

  def test_request_waits_for_the_answer(self) -> None:
    connection, fake = self.connected()

    def serve() -> None:
      request = fake.readRequest()
      fake.answer(request, {'state': 'menu'})

    thread, _ = inThread(serve)
    self.assertEqual({'state': 'menu'}, connection.request('status', timeout=5))
    thread.join(5)

  def test_an_error_answer_raises_its_own_exception(self) -> None:
    connection, fake = self.connected()
    pending = connection.send('ticks.wait', {'n': 5}, side=Side.SERVER)
    fake.answer(fake.readRequest(), error={
      'type': 'Stalled', 'message': "the server didn't tick for 15 s", 'side': 'server', 'since_tick_ms': 15004,
    })
    with self.assertRaises(Stalled) as caught:
      pending.result(5)
    error = caught.exception
    self.assertIsInstance(error, RequestError)
    self.assertIs(ErrorType.STALLED, error.type)
    self.assertEqual("the server didn't tick for 15 s", error.message)
    self.assertEqual(15004, error.fields['since_tick_ms'])
    self.assertEqual('ticks.wait', error.op)
    self.assertIn('ticks.wait', str(error))
    self.assertIn("didn't tick", str(error))

  def test_each_error_type_has_its_exception(self) -> None:
    connection, fake = self.connected()
    for kind in ErrorType:
      with self.subTest(type=kind.value):
        pending = connection.send('status')
        fake.answer(fake.readRequest(), error={'type': kind.value, 'message': 'm'})
        with self.assertRaises(RequestError) as caught:
          pending.result(5)
        self.assertEqual(kind.value, type(caught.exception).__name__)
        self.assertIs(kind, caught.exception.type)

  def test_an_error_type_from_a_later_protocol_still_raises(self) -> None:
    connection, fake = self.connected()
    pending = connection.send('status')
    fake.answer(fake.readRequest(), error={'type': 'Wobbly', 'message': 'new in a later probe'})
    with self.assertRaises(RequestError) as caught:
      pending.result(5)
    self.assertIs(RequestError, type(caught.exception))
    self.assertEqual('Wobbly', caught.exception.type)

  def test_unknown_fields_in_an_answer_are_ignored(self) -> None:
    connection, fake = self.connected()
    pending = connection.send('status')
    fake.answer(fake.readRequest(), {'state': 'menu'}, extra={'warnings': ['a ref on the other side'], 'later': 1})
    self.assertEqual({'state': 'menu'}, pending.result(5))
    self.assertEqual(['a ref on the other side'], pending.warnings)

  def test_an_answer_nobody_asked_for_is_ignored(self) -> None:
    connection, fake = self.connected()
    fake.answer({'id': 9999}, {'state': 'menu'})
    pending = connection.send('status')
    fake.answer(fake.readRequest(), {'state': 'world'})
    self.assertEqual({'state': 'world'}, pending.result(5))

  def test_a_result_not_yet_there_times_out(self) -> None:
    connection, fake = self.connected()
    pending = connection.send('ticks.wait', {'n': 1000})
    with self.assertRaises(LinkTimeout):
      pending.result(0.2)
    self.assertFalse(pending.done)

  def test_cancel(self) -> None:
    connection, fake = self.connected()
    waiting = connection.send('ticks.wait', {'n': 1000})
    fake.readRequest()
    thread, box = inThread(connection.cancel, waiting)
    cancel = fake.readRequest()
    self.assertEqual('cancel', cancel['op'])
    self.assertEqual({'id': waiting.id}, cancel['args'])
    fake.answer(cancel, {'cancelled': True})
    thread.join(5)
    self.assertIs(True, box.get('value'), box)

  def test_an_oversized_request_is_never_sent(self) -> None:
    connection, fake = self.connected()
    with self.assertRaises(ValueError):
      connection.send('chat.send', {'text': 'a' * MAX_LINE})
    self.assertFalse(connection.closed)


class EventTests(_LinkTest):

  def test_events_are_kept_in_order(self) -> None:
    connection, fake = self.connected()
    mark = connection.events.mark()
    fake.event('chat', plain='one')
    fake.event('sound', id='minecraft:random.bow', known=True)
    fake.event('chat', plain='two')
    last = connection.events.waitFor(lambda event: event.get('plain') == 'two', 5, since=mark)
    self.assertEqual('two', last['plain'])
    self.assertEqual(['chat', 'sound', 'chat'], [event['event'] for event in connection.events.since(mark)])

  def test_a_mark_leaves_the_earlier_out(self) -> None:
    connection, fake = self.connected()
    fake.event('chat', plain='before')
    connection.events.waitFor(lambda event: event.get('plain') == 'before', 5)
    mark = connection.events.mark()
    fake.event('chat', plain='after')
    connection.events.waitFor(lambda event: event.get('plain') == 'after', 5, since=mark)
    self.assertEqual(['after'], [event['plain'] for event in connection.events.since(mark)])

  def test_events_between_answers(self) -> None:
    connection, fake = self.connected()
    mark = connection.events.mark()
    pending = connection.send('command.run', {'command': '/give @p wool 1 14'})
    request = fake.readRequest()
    fake.event('chat', plain='Given [Red Wool] * 1')
    fake.answer(request, {'result': 1, 'lines': ['Given [Red Wool] * 1'], 'errors': []})
    pending.result(5)
    self.assertEqual(['Given [Red Wool] * 1'], [event['plain'] for event in connection.events.since(mark)])

  def test_waiting_for_an_event_that_never_comes(self) -> None:
    connection, fake = self.connected()
    with self.assertRaises(LinkTimeout):
      connection.events.waitFor(lambda event: event['event'] == 'never', 0.2)

  def test_a_subscriber_hears_each_event(self) -> None:
    connection, fake = self.connected()
    heard = []
    connection.events.subscribe(heard.append)
    fake.event('screen', to='GuiChat')
    fake.event('screen', to=None)
    connection.events.waitFor(lambda event: event.get('to', 1) is None, 5)
    self.assertEqual(['GuiChat', None], [event['to'] for event in heard])


class EndTests(_LinkTest):

  def test_the_game_hanging_up_fails_what_waits(self) -> None:
    connection, fake = self.connected()
    pending = connection.send('ticks.wait', {'n': 100})
    fake.readRequest()
    fake.close()
    with self.assertRaises(LinkClosed) as caught:
      pending.result(5)
    self.assertIn('closed', str(caught.exception))
    self.assertTrue(connection.closed)
    with self.assertRaises(LinkClosed):
      connection.send('status')

  def test_a_line_over_the_limit_ends_the_connection(self) -> None:
    connection, fake = self.connected()
    pending = connection.send('status')
    fake.readRequest()
    fake.sendRaw(b'{"event": "log", "message": "' + b'a' * (MAX_LINE + 10) + b'"}\n')
    with self.assertRaises(LinkClosed) as caught:
      pending.result(10)
    self.assertIn('16 MiB', str(caught.exception))
    self.assertIn('16 MiB', connection.closedBecause)

  def test_a_line_that_isnt_json_ends_the_connection(self) -> None:
    connection, fake = self.connected()
    pending = connection.send('status')
    fake.readRequest()
    fake.sendRaw(b'this is not json\n')
    with self.assertRaises(LinkClosed) as caught:
      pending.result(5)
    self.assertRegex(str(caught.exception), re.compile('json', re.IGNORECASE))

  def test_closing_from_this_side(self) -> None:
    connection, fake = self.connected()
    connection.close()
    self.assertTrue(connection.closed)
    self.assertIsNone(fake.read(5), 'the game sees the connection end')


if __name__ == '__main__':
  unittest.main()

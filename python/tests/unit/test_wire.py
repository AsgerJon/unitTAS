"""
Tests of unittas.wire: the protocol's closed sets, its lines of JSON, and
the values every message carries (the hello, the ticks).

  python -m unittest discover -s python/tests/unit
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import json
import math
import unittest

from fakeprobe import HELLO
from unittas.wire import ErrorType, Hello, MAX_LINE, PROTOCOLS, Role, Side
from unittas.wire import State, Ticks, decodeLine, encodeLine


class SetsTests(unittest.TestCase):

  def test_sides_and_roles_from_the_wire(self) -> None:
    self.assertIs(Side('client'), Side.CLIENT)
    self.assertIs(Side('server'), Side.SERVER)
    self.assertIs(Role('server'), Role.SERVER)
    self.assertEqual('client', Side.CLIENT.value)

  def test_every_error_type_of_the_protocol(self) -> None:
    wire = ['BadRequest', 'Unsupported', 'NotReady', 'NotFound', 'Exists', 'GameError', 'Stalled', 'TimedOut',
            'Cancelled', 'Disconnected', 'ProbeError']
    self.assertEqual(wire, [kind.value for kind in ErrorType])

  def test_states(self) -> None:
    self.assertEqual(['loading', 'menu', 'world', 'changing', 'quitting'], [state.value for state in State])

  def test_protocol_versions(self) -> None:
    self.assertEqual((1,), PROTOCOLS)


class LineTests(unittest.TestCase):

  def test_one_line_ending_in_a_newline(self) -> None:
    line = encodeLine({'id': 1, 'op': 'chat.send', 'args': {'text': 'two\nlines'}})
    self.assertTrue(line.endswith(b'\n'))
    self.assertEqual(1, line.count(b'\n'), 'a newline inside a value must be escaped')
    self.assertEqual({'id': 1, 'op': 'chat.send', 'args': {'text': 'two\nlines'}}, decodeLine(line))

  def test_utf8_as_itself(self) -> None:
    line = encodeLine({'text': 'Æblegrød §c'})
    self.assertIn('Æblegrød §c'.encode('utf-8'), line)

  def test_non_finite_numbers_as_strings(self) -> None:
    line = encodeLine({'a': math.nan, 'b': [math.inf, -math.inf], 'c': 1.5})
    self.assertEqual({'a': 'NaN', 'b': ['Infinity', '-Infinity'], 'c': 1.5}, json.loads(line))

  def test_a_line_over_the_limit_is_refused(self) -> None:
    with self.assertRaises(ValueError) as caught:
      encodeLine({'pad': 'a' * MAX_LINE})
    self.assertIn('16 MiB', str(caught.exception))

  def test_only_objects_are_messages(self) -> None:
    for bad in (b'[1, 2]\n', b'"text"\n', b'not json\n', b'\xff\n'):
      with self.subTest(line=bad):
        with self.assertRaises(ValueError):
          decodeLine(bad)


class TicksTests(unittest.TestCase):

  def test_both_sides(self) -> None:
    ticks = Ticks.fromWire({'client': 120, 'server': 118})
    self.assertEqual((120, 118), (ticks.client, ticks.server))

  def test_a_side_with_no_ticks(self) -> None:
    ticks = Ticks.fromWire({'client': 3, 'server': None})
    self.assertEqual(3, ticks.client)
    self.assertIsNone(ticks.server)

  def test_none_at_all(self) -> None:
    ticks = Ticks.fromWire(None)
    self.assertIsNone(ticks.client)
    self.assertIsNone(ticks.server)


class HelloTests(unittest.TestCase):

  def wire(self, **changes) -> dict:
    body = dict(HELLO)
    body.update({'protocol': [1], 'token': 'ab' * 32, 'name': 'alice', 'role': 'client'})
    body.update(changes)
    return body

  def test_read_from_the_wire(self) -> None:
    hello = Hello.fromWire(self.wire())
    self.assertEqual((1,), hello.protocol)
    self.assertEqual('alice', hello.name)
    self.assertIs(Role.CLIENT, hello.role)
    self.assertEqual('1.7.10', hello.minecraft)
    self.assertEqual('forge', hello.loaderName)
    self.assertEqual('10.13.4.1614', hello.loaderVersion)
    self.assertEqual('0.2.0', hello.probeVersion)
    self.assertEqual('1.7.10-forge', hello.probePort)
    self.assertEqual('mcp', hello.names)
    self.assertTrue(hello.development)
    self.assertEqual(4242, hello.pid)
    self.assertIn('ticks.wait', hello.ops)

  def test_unknown_fields_are_ignored(self) -> None:
    hello = Hello.fromWire(self.wire(colour='green', loader={'name': 'forge', 'version': '1', 'extra': 2}))
    self.assertEqual('forge', hello.loaderName)

  def test_a_missing_field_is_named(self) -> None:
    body = self.wire()
    del body['minecraft']
    with self.assertRaises(ValueError) as caught:
      Hello.fromWire(body)
    self.assertIn('minecraft', str(caught.exception))

  def test_a_wrong_type_is_named(self) -> None:
    with self.assertRaises(ValueError) as caught:
      Hello.fromWire(self.wire(pid='many'))
    self.assertIn('pid', str(caught.exception))

  def test_the_token_never_shows(self) -> None:
    hello = Hello.fromWire(self.wire())
    self.assertNotIn('ab' * 32, repr(hello))
    self.assertNotIn('ab' * 32, str(hello))


if __name__ == '__main__':
  unittest.main()

"""
The 'snbt' module reads and writes NBT as modern SNBT text, the form the
probe sends it in on every version (PROTOCOL.md section 5.6), into a typed
tree: each value is of a class that says its NBT type, and is also the
plain Python value it holds, so a test compares 'stack.nbt["Count"] == 3'
and can still tell a byte from an int.

- Byte, Short, Int, Long: ints; Float, Double: floats; String: a str.
- TagList: a list; ByteArray, IntArray, LongArray: lists of their numbers.
- Compound: a dict of names to values.
- loads: text to a tree. dumps: a tree (or plain values) to text.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any


class Byte(int):
  """An NBT byte."""


class Short(int):
  """An NBT short."""


class Int(int):
  """An NBT int."""


class Long(int):
  """An NBT long."""


class Float(float):
  """An NBT float."""


class Double(float):
  """An NBT double."""


class String(str):
  """An NBT string."""


class TagList(list):
  """An NBT list."""


class ByteArray(list):
  """An NBT byte array."""


class IntArray(list):
  """An NBT int array."""


class LongArray(list):
  """An NBT long array (from 1.12)."""


class Compound(dict):
  """An NBT compound."""


_SUFFIX = {'b': Byte, 's': Short, 'l': Long, 'f': Float, 'd': Double}
_NUMBER = re.compile(r'^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?([bBsSlLfFdD]?)$')
_BARE_KEY = re.compile(r'^[A-Za-z0-9._+-]+$')
#  a bare value may hold a colon too ({id:minecraft:stone}); a bare key may not
_BARE_VALUE = re.compile(r'[A-Za-z0-9._+\-:]')
_ARRAYS = {'B': (ByteArray, Byte), 'I': (IntArray, Int), 'L': (LongArray, Long)}


class _Reader:
  """A recursive reader over one text; ValueError, with the place, for text that isn't SNBT."""

  def __init__(self, text: str) -> None:
    self.text = text
    self.at = 0

  def fail(self, what: str) -> ValueError:
    return ValueError('not SNBT: %s at %d in %r' % (what, self.at, self.text[:200]))

  def skip(self) -> None:
    while self.at < len(self.text) and self.text[self.at].isspace():
      self.at += 1

  def peek(self) -> str:
    self.skip()
    return self.text[self.at] if self.at < len(self.text) else ''

  def take(self, expected: str) -> None:
    if self.peek() != expected:
      raise self.fail('%r expected' % expected)
    self.at += 1

  def value(self) -> Any:
    head = self.peek()
    if head == '{':
      return self.compound()
    if head == '[':
      return self.list()
    if head in ('"', "'"):
      return String(self.quoted())
    if head == '':
      raise self.fail('a value expected')
    return self.bare()

  def compound(self) -> Compound:
    self.take('{')
    found = Compound()
    if self.peek() == '}':
      self.at += 1
      return found
    while True:
      key = self.quoted() if self.peek() in ('"', "'") else self.bareKey()
      self.take(':')
      found[key] = self.value()
      if self.peek() == ',':
        self.at += 1
        continue
      self.take('}')
      return found

  def list(self) -> list:
    self.take('[')
    rest = self.text[self.at:self.at + 2]
    if len(rest) == 2 and rest[0] in _ARRAYS and rest[1] == ';':
      kind, element = _ARRAYS[rest[0]]
      self.at += 2
      items = kind()
      if self.peek() == ']':
        self.at += 1
        return items
      while True:
        number = self.value()
        if type(number) is not element:
          raise self.fail('a %s array holds %ss only' % (rest[0], element.__name__.lower()))
        items.append(number)
        if self.peek() == ',':
          self.at += 1
          continue
        self.take(']')
        return items
    items = TagList()
    if self.peek() == ']':
      self.at += 1
      return items
    while True:
      items.append(self.value())
      if self.peek() == ',':
        self.at += 1
        continue
      self.take(']')
      return items

  def quoted(self) -> str:
    quote = self.text[self.at]
    self.at += 1
    out = []
    while self.at < len(self.text):
      char = self.text[self.at]
      self.at += 1
      if char == '\\':
        if self.at >= len(self.text):
          break
        out.append(self.text[self.at])
        self.at += 1
      elif char == quote:
        return ''.join(out)
      else:
        out.append(char)
    raise self.fail('an unclosed string')

  def bareKey(self) -> str:
    start = self.at
    while self.at < len(self.text) and _BARE_KEY.match(self.text[self.at]):
      self.at += 1
    if self.at == start:
      raise self.fail('a key expected')
    return self.text[start:self.at]

  def bare(self) -> Any:
    start = self.at
    while self.at < len(self.text) and _BARE_VALUE.match(self.text[self.at]):
      self.at += 1
    word = self.text[start:self.at]
    if not word:
      raise self.fail('a value expected')
    if word == 'true':
      return Byte(1)
    if word == 'false':
      return Byte(0)
    match = _NUMBER.match(word)
    if match is None:
      return String(word)
    suffix = match.group(1).lower()
    digits = word[:-1] if suffix else word
    if suffix in ('f', 'd'):
      return _SUFFIX[suffix](float(digits))
    if suffix:
      return _SUFFIX[suffix](int(digits))
    if '.' in digits or 'e' in digits.lower():
      return Double(float(digits))
    return Int(int(digits))


def loads(text: str) -> Any:
  """The typed tree the SNBT text describes; ValueError for text that isn't SNBT."""
  reader = _Reader(text)
  value = reader.value()
  if reader.peek() != '':
    raise reader.fail('more after the value')
  return value


def _key(name: str) -> str:
  return name if _BARE_KEY.match(name) else _string(name)


def _string(text: str) -> str:
  return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _number(value: float) -> str:
  text = repr(float(value))
  return text


def dumps(value: Any) -> str:
  """
  The value as SNBT. Typed values are written as their type; plain ones
  as the obvious one: a bool as a byte, an int as an int, a float as a
  double, a str as a string, a list as a list, a dict as a compound.
  """
  if isinstance(value, bool):
    return '1b' if value else '0b'
  if isinstance(value, Byte):
    return '%db' % value
  if isinstance(value, Short):
    return '%ds' % value
  if isinstance(value, Long):
    return '%dL' % value
  if isinstance(value, int):
    return '%d' % value
  if isinstance(value, Float):
    return _number(value) + 'f'
  if isinstance(value, float):
    return _number(value) + 'd'
  if isinstance(value, str):
    return _string(value)
  if isinstance(value, ByteArray):
    return '[B;' + ','.join('%db' % item for item in value) + ']'
  if isinstance(value, IntArray):
    return '[I;' + ','.join('%d' % item for item in value) + ']'
  if isinstance(value, LongArray):
    return '[L;' + ','.join('%dL' % item for item in value) + ']'
  if isinstance(value, (list, tuple)):
    return '[' + ','.join(dumps(item) for item in value) + ']'
  if isinstance(value, dict):
    return '{' + ','.join(_key(str(name)) + ':' + dumps(item) for name, item in value.items()) + '}'
  raise TypeError('no SNBT for a %s: %r' % (type(value).__name__, value))

"""
Things by mcdex member (SPEC.md 14.3): each id mcdex holds for a version
read into its parts, and turned into what the probe takes. Every id fits
one grammar: a name, then optionally ':meta', '[state]' and '{NBT}', or a
number as text. mcdex is imported here, so this module is imported only
where a member is used (it takes about 0.7 s).

- ThingId: an id's parts.
- parse: an id's text into its parts.
- resolve: a member's id in a version; Missing where vanilla lacks it,
  NoMcdexData where mcdex has no data for that version.
- itemOf, blockOf, entityOf, dimensionOf: a member as the probe takes it.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from mcdex import MCBlocks, MCDimensions, MCEntities, MCItems, NotInVersion
from worktoy.ezdata import EZData, EZField

from .errors import Missing, NoMcdexData
from .snbt import loads
from .values import Block, Item

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Union

  from mcdex import Version

_NUMBER = re.compile(r'-?\d+')
_PART = re.compile(r'[A-Za-z0-9_.\-]+')


class ThingId(EZData, frozen=True):
  """
  An mcdex id's parts (SPEC.md 14.3): its name, its meta when it has one,
  its block state and its NBT ('' for none), or the number it is.
  """
  name = EZField[str]('')
  meta = EZField[int](0)
  hasMeta = EZField[bool](False)
  state = EZField[str]('')
  nbt = EZField[str]('')
  number = EZField[int](0)
  isNumber = EZField[bool](False)

  def text(self) -> str:
    """The id written back as mcdex writes it."""
    if self.isNumber:
      return str(self.number)
    out = self.name
    if self.hasMeta:
      out += ':%d' % self.meta
    if self.state:
      out += '[%s]' % self.state
    return out + self.nbt


def parse(text: str) -> ThingId:
  """
  An mcdex id read into its parts.

  Raises
  ------
  ValueError
    The text fits no part of the grammar: nothing is guessed.
  """
  if not isinstance(text, str) or not text:
    raise ValueError('an mcdex id is a text, not %r' % (text,))
  if _NUMBER.fullmatch(text):
    return ThingId(number=int(text), isNumber=True)
  rest, state, nbt = text, '', ''
  brace = rest.find('{')
  if brace >= 0:
    rest, nbt = rest[:brace], rest[brace:]
    try:
      loads(nbt)
    except ValueError as error:
      raise ValueError('%r: its NBT is no SNBT (%s)' % (text, error))
  bracket = rest.find('[')
  if bracket >= 0:
    if not rest.endswith(']') or bracket == len(rest) - 2:
      raise ValueError('%r: its block state is cut short' % text)
    rest, state = rest[:bracket], rest[bracket + 1:-1]
  parts = rest.split(':')
  if len(parts) > 3 or not all(_PART.fullmatch(part) for part in parts):
    raise ValueError('%r fits no mcdex id: name[:meta][[state]][{NBT}]'
                     % text)
  if len(parts) == 3:
    if not parts[2].isdigit():
      raise ValueError('%r: a meta is a whole number' % text)
    return ThingId(parts[0] + ':' + parts[1], int(parts[2]), True, state,
                   nbt)
  return ThingId(rest, state=state, nbt=nbt)


def resolve(member: Any, version: Version) -> ThingId:
  """
  The member's id in the version, read into its parts.

  Raises
  ------
  Missing
    Vanilla lacks it in that version, by mcdex's NotInVersion: a FAIL.
  NoMcdexData
    mcdex has no data on that version for it: no result.
  """
  try:
    found = member[version]
  except NotInVersion as error:
    raise Missing(member, version, str(error)) from error
  except ValueError as error:
    #  mcdex: 'mcdex has no data on ... before 1.8'
    raise NoMcdexData(member, version, str(error)) from error
  return parse(found.minecraftId)


def _need(member: Any, catalogue: type, where: str) -> None:
  """TypeError unless 'member' is one of 'catalogue''s."""
  if not isinstance(member, catalogue):
    raise TypeError('%s takes a member of %s, not %r'
                    % (where, catalogue.__name__, member))


def _plain(thing: ThingId, member: Any, what: str, *parts: str) -> None:
  """
  NotImplementedError for a part the probe can't be given for that kind
  of thing: no probe takes a block state, the 1.13 to 1.16.5 shape.
  """
  for part in parts:
    if getattr(thing, part):
      raise NotImplementedError(
        "%s.%s is %r there: no probe takes %s's %s"
        % (type(member).__name__, member.name, thing.text(), what, part))


def itemOf(member: Any, version: Version, count: int = 1) -> Item:
  """An MCItems member as an item stack of 'count' in the version."""
  _need(member, MCItems, 'an item')
  thing = resolve(member, version)
  _plain(thing, member, 'an item', 'isNumber', 'state')
  return Item(thing.name, count, thing.meta, thing.nbt)


def blockOf(member: Any, version: Version) -> tuple:
  """
  An MCBlocks member in the version: the block, and its block entity's
  data as SNBT ('' for none), which block.set takes as 'tile'.
  """
  _need(member, MCBlocks, 'a block')
  thing = resolve(member, version)
  _plain(thing, member, 'a block', 'isNumber', 'state')
  return Block(thing.name, thing.meta), thing.nbt


def entityOf(member: Any, version: Version) -> tuple:
  """
  An MCEntities member in the version: the type entity.spawn takes, and
  the data that tells it apart as SNBT ('' for none), as 1.7.10's wither
  skeleton is a skeleton of type 1.
  """
  _need(member, MCEntities, 'an entity')
  thing = resolve(member, version)
  _plain(thing, member, 'an entity', 'isNumber', 'hasMeta', 'state')
  return thing.name, thing.nbt


def dimensionOf(member: Any, version: Version) -> Union[int, str]:
  """
  An MCDimensions member in the version: 1.7.10's number, which its probe
  takes (PROTOCOL.md 5.2), or the dimension's name.
  """
  _need(member, MCDimensions, 'a dimension')
  thing = resolve(member, version)
  _plain(thing, member, 'a dimension', 'hasMeta', 'state', 'nbt')
  return thing.number if thing.isNumber else thing.name

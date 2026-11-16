"""
Things by mcdex member (SPEC.md 14.3): each id mcdex holds for a version
read into its parts, and turned into what the probe takes. Every id fits
one grammar: a name, then optionally ':meta', '[state]' and '{NBT}', or a
number as text. mcdex is imported here, so this module is imported only
where a member is used (it takes about 0.7 s).

- ThingId: an id's parts.
- parse: an id's text into its parts.
- resolve: a member's id in a version, or the id a mod declares for it
  where vanilla lacks it; Missing where neither has it, NoMcdexData where
  mcdex has no data for that version.
- declare: the mods' declarations (hooks.things), checked.
- itemOf, blockOf, entityOf, dimensionOf: a member as the probe takes it.
- membersOf: a value the game reports, as the set of members it is.
- needsData: whether telling a value's members apart needs its data.
- describe: a value as its id's text, for messages.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING

from mcdex import (MCBlocks, MCDimensions, MCEffects, MCEntities, MCItems,
                   NotInVersion, Version)
from worktoy.ezdata import EZData, EZField

from .errors import Missing, NoMcdexData
from .snbt import loads
from .values import Block, Effect, Entity, Item

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Optional, Union

#  A mod's declaration names a member as '<catalogue>/<unique name>'
#  (TasHooks.things), in mcdex's own words
CATALOGUES = {'items': MCItems, 'blocks': MCBlocks, 'entities': MCEntities,
              'effects': MCEffects, 'dimensions': MCDimensions}
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


def resolve(member: Any, version: Version,
            declared: Optional[dict] = None) -> ThingId:
  """
  The member's id in the version, read into its parts: vanilla's, or,
  where vanilla lacks it, the id a mod declares for it ('declared', as
  declare gives it; SPEC.md 14.4, M4).

  Raises
  ------
  Missing
    Vanilla lacks it in that version, by mcdex's NotInVersion, and no mod
    declares it: a FAIL.
  NoMcdexData
    mcdex has no data on that version for it: no result.
  """
  try:
    found = member[version]
  except NotInVersion as error:
    if declared and member in declared:
      return declared[member][0]
    why = str(error)
    if declared is not None:
      why += ' (no mod declares it)'
    raise Missing(member, version, why) from error
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


def itemOf(member: Any, version: Version, count: int = 1,
           declared: Optional[dict] = None) -> Item:
  """An MCItems member as an item stack of 'count' in the version."""
  _need(member, MCItems, 'an item')
  thing = resolve(member, version, declared)
  _plain(thing, member, 'an item', 'isNumber', 'state')
  if thing.nbt and version >= Version.V1_20_5:
    raise NotImplementedError(
      "%s.%s is %r there: an item's data is its components from 1.20.5 "
      "on, and no mcdex id carries them yet"
      % (type(member).__name__, member.name, thing.text()))
  return Item(thing.name, count, _meta(thing, version), thing.nbt)


def blockOf(member: Any, version: Version,
            declared: Optional[dict] = None) -> tuple:
  """
  An MCBlocks member in the version: the block, and its block entity's
  data as SNBT ('' for none), which block.set takes as 'tile'.
  """
  _need(member, MCBlocks, 'a block')
  thing = resolve(member, version, declared)
  _plain(thing, member, 'a block', 'isNumber', 'state')
  return Block(thing.name, _meta(thing, version)), thing.nbt


def _meta(thing: ThingId, version: Version) -> int:
  """Its meta: none (-1) from 1.13 on, unless mcdex's id gives one."""
  if thing.hasMeta or version < Version.V1_13:
    return thing.meta
  return -1


def entityOf(member: Any, version: Version,
             declared: Optional[dict] = None) -> tuple:
  """
  An MCEntities member in the version: the type entity.spawn takes, and
  the data that tells it apart as SNBT ('' for none), as 1.7.10's wither
  skeleton is a skeleton of type 1.
  """
  _need(member, MCEntities, 'an entity')
  thing = resolve(member, version, declared)
  _plain(thing, member, 'an entity', 'isNumber', 'hasMeta', 'state')
  return thing.name, thing.nbt


def dimensionOf(member: Any, version: Version,
                declared: Optional[dict] = None) -> Union[int, str]:
  """
  An MCDimensions member in the version: 1.7.10's number, which its probe
  takes (PROTOCOL.md 5.2), or the dimension's name.
  """
  _need(member, MCDimensions, 'a dimension')
  thing = resolve(member, version, declared)
  _plain(thing, member, 'a dimension', 'hasMeta', 'state', 'nbt')
  return thing.number if thing.isNumber else thing.name


@lru_cache(maxsize=None)
def _index(catalogue: type, version: Version) -> dict:
  """
  The catalogue's ids in the version, by name (or number as text): each
  name's (ThingId, member) pairs. Built at first use; mcdex is settled.
  """
  out = {}
  for member in catalogue:
    try:
      found = member[version]
    except NotInVersion:
      continue
    except ValueError:
      #  mcdex has no data on that version: nothing there to find
      continue
    thing = parse(found.minecraftId)
    key = str(thing.number) if thing.isNumber else thing.name
    out.setdefault(key, []).append((thing, member))
  return {key: tuple(pairs) for key, pairs in out.items()}


def _subset(want: Any, have: Any) -> bool:
  """
  Whether mcdex's NBT 'want' is within the value's 'have': each key of a
  compound there and within, lists equal, numbers by value (mcdex's
  '{SkeletonType:1}' is the game's 'SkeletonType:1b').
  """
  if isinstance(want, dict):
    if not isinstance(have, dict):
      return False
    return all(key in have and _subset(value, have[key])
               for key, value in want.items())
  if isinstance(want, list):
    if not isinstance(have, list) or len(want) != len(have):
      return False
    return all(_subset(a, b) for a, b in zip(want, have))
  if isinstance(want, (int, float)) and not isinstance(want, bool):
    return (isinstance(have, (int, float)) and not isinstance(have, bool)
            and want == have)
  return want == have


def _reported(value: Any) -> tuple:
  """
  A value's catalogue, its keys in the index (most telling first), its
  meta (None for a kind without one), its data's SNBT, and whether its
  data was read.
  """
  if isinstance(value, Item):
    return MCItems, (value.id,), value.meta, value.snbt, True
  if isinstance(value, Block):
    return (MCBlocks, (value.id,), value.meta, value.tileSnbt,
            value.tileAsked)
  if isinstance(value, Entity):
    return MCEntities, (value.type,), None, value.snbt, value.nbtAsked
  if isinstance(value, Effect):
    keys = (value.effect, str(value.id)) if value.effect else (
      str(value.id),)
    return MCEffects, keys, None, '', True
  raise TypeError('an Item, a Block, an Entity or an Effect reads back '
                  'as mcdex members, not %r' % (value,))


def _candidates(value: Any, version: Version,
                declared: Optional[dict] = None) -> tuple:
  """
  The (ThingId, member) pairs whose name the value's id has: vanilla's,
  and the mods' declarations of what vanilla lacks.
  """
  catalogue, keys, _, _, _ = _reported(value)
  index = _index(catalogue, version)
  out = ()
  for key in keys:
    if key in index:
      out = index[key]
      break
  mods = tuple((thing, member)
               for member, (thing, _) in (declared or {}).items()
               if isinstance(member, catalogue) and thing.name in keys)
  return out + mods


def needsData(value: Any, version: Version,
              declared: Optional[dict] = None) -> bool:
  """Whether some member the value's name fits is told apart by data."""
  return any(thing.nbt for thing, _ in _candidates(value, version,
                                                   declared))


def membersOf(value: Any, version: Version,
              declared: Optional[dict] = None) -> frozenset:
  """
  The members a value the game reports is, in the version (SPEC.md
  14.3): those whose id it fits (the name; the meta where mcdex's id has
  one, so a tool's damage doesn't count; mcdex's NBT within the value's),
  the most specific of them: a member whose meta or data matched beats
  one that names neither, so a potted poppy is no empty flower pot and a
  wither skeleton no plain skeleton. Twins and an old id two things
  shared give several. Empty where mcdex has no member for it (M6).

  Raises
  ------
  ValueError
    A member it may be is told apart by data the value wasn't read with
    (a block without tile=True, an entity without nbt=True).
  """
  _, _, meta, snbt, asked = _reported(value)
  have = None
  matched = []
  for thing, member in _candidates(value, version, declared):
    if thing.hasMeta and thing.meta != meta:
      continue
    if thing.nbt:
      if not asked:
        raise ValueError('%s may be %s.%s, told apart by its data %s, '
                         'which it was read without'
                         % (describe(value), type(member).__name__,
                            member.name, thing.nbt))
      if have is None:
        have = loads(snbt) if snbt else {}
      if not _subset(loads(thing.nbt), have):
        continue
    matched.append((int(thing.hasMeta) + int(bool(thing.nbt)), member))
  if not matched:
    return frozenset()
  best = max(score for score, _ in matched)
  return frozenset(member for score, member in matched if score == best)


def describe(value: Any) -> str:
  """A value as its id's text, as mcdex writes ids: 'minecraft:wool:14'."""
  if isinstance(value, Item):
    return value.id + (':%d' % value.meta if value.meta else '') + value.snbt
  if isinstance(value, Block):
    meta = ':%d' % value.meta if value.meta else ''
    return value.id + meta + (value.tileSnbt if value.tileAsked else '')
  if isinstance(value, Entity):
    return value.type + value.snbt
  if isinstance(value, Effect):
    return value.effect or str(value.id)
  return repr(value)


@lru_cache(maxsize=None)
def _byUnique(catalogue: type) -> dict:
  """The catalogue's members by their unique names ('elytra')."""
  return {member.value: member for member in catalogue}


def declare(plugins: list, version: Version) -> dict:
  """
  The mods' declarations of things vanilla lacks (hooks.things: each
  plugin's '<catalogue>/<unique name>' to its id), checked, as
  {member: (ThingId, the plugin's class)} (SPEC.md 14.4, M4).

  Raises
  ------
  ValueError
    A plugin's things() failed; a key names no catalogue or no member; a
    plugin declares what vanilla has in that version (a mod declares only
    what vanilla lacks); an id fits no mcdex id; two plugins declare one
    member differently. Each names the plugin.
  """
  out = {}
  for plugin in plugins:
    name = plugin.get('class', '?')
    if not plugin.get('ok', False):
      error = plugin.get('error') or {}
      raise ValueError("%s's things() failed: %s"
                       % (name, error.get('message', 'no message')))
    for key, text in sorted((plugin.get('things') or {}).items()):
      catalogueName, _, unique = key.partition('/')
      catalogue = CATALOGUES.get(catalogueName)
      if catalogue is None:
        raise ValueError('%s declares %r: a key is <catalogue>/<unique '
                         'name>, the catalogue one of %s'
                         % (name, key, ', '.join(sorted(CATALOGUES))))
      member = _byUnique(catalogue).get(unique)
      if member is None:
        raise ValueError('%s declares %r, which mcdex has no member for'
                         % (name, key))
      try:
        vanilla = member[version].minecraftId
      except (NotInVersion, ValueError):
        vanilla = None
      if vanilla is not None:
        raise ValueError('%s declares %r, which vanilla %s has as %s: a '
                         'mod declares only what vanilla lacks'
                         % (name, key, version.value, vanilla))
      try:
        thing = parse(text)
      except ValueError as error:
        raise ValueError('%s declares %r as %r: %s'
                         % (name, key, text, error)) from error
      if member in out and out[member][0] != thing:
        raise ValueError('%s and %s declare %r differently: %s and %s'
                         % (out[member][1], name, key, out[member][0].text(),
                            thing.text()))
      out[member] = (thing, name)
  return out

"""
The 'codec' module is the JSON edge of the protocol's values (unittas.values):
'fromJson(Kind, data)' reads one from an answer or an event, and
'toJson(value)' writes it as a request takes it and the probe sends it,
so a value read and written again is the JSON it came from.

Reading checks each field the value needs and names what is wrong (a
ValueError: 'an entity has no "pos"', 'an item\\'s "count" is a str, not
a whole number'); fields it doesn't know are ignored, as the protocol is
additive (section 1). This is also where nested values are built, which
EZData doesn't do from a list (worktoy-notes.md, 3).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from typing import TYPE_CHECKING

from .values import (Block, BlockPos, ChatLine, Effect, Entity, Inventory, Item, LogLine, Look, Player, Screen, Sound,
                     Vec3)

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Callable

_MISSING = object()
_NAMES = {Vec3: 'a position', BlockPos: 'a block position', Look: 'a look', Item: 'an item', Block: 'a block',
          Inventory: 'an inventory', Entity: 'an entity', Effect: 'an effect', Player: 'a player',
          ChatLine: 'a chat line', Sound: 'a sound', LogLine: 'a log line', Screen: 'a screen'}


# ---------------------------------------------------------------- reading the fields

def _kindName(kind: Any) -> str:
  return {int: 'whole number', float: 'number', bool: 'true or false', str: 'string', list: 'list',
          dict: 'object'}.get(kind, getattr(kind, '__name__', str(kind)))


def _check(value: Any, kind: Any, what: str, key: str) -> Any:
  """The value if it is of the kind (a bool is never a number, an int is a float); ValueError naming it otherwise."""
  if kind is float:
    good = isinstance(value, (int, float)) and not isinstance(value, bool)
    value = float(value) if good else value
  elif kind is int:
    good = isinstance(value, int) and not isinstance(value, bool)
  else:
    good = isinstance(value, kind)
  if not good:
    raise ValueError('%s\'s "%s" is a %s, not a %s' % (what, key, type(value).__name__, _kindName(kind)))
  return value


def _need(body: dict, key: str, kind: Any, what: str) -> Any:
  if key not in body:
    raise ValueError('%s has no "%s"' % (what, key))
  return _check(body[key], kind, what, key)


def _maybe(body: dict, key: str, kind: Any, what: str, otherwise: Any) -> Any:
  """The value under the key when there and not null; otherwise the stand-in."""
  value = body.get(key)
  return otherwise if value is None else _check(value, kind, what, key)


def _object(data: Any, kind: type) -> dict:
  if not isinstance(data, dict):
    raise ValueError('%s is a JSON object, not %r' % (_NAMES[kind], data))
  return data


def _numbers(data: Any, kind: type, each: Any) -> list:
  what = _NAMES[kind]
  if not isinstance(data, list) or len(data) != 3:
    raise ValueError('%s is a list of three numbers, not %r' % (what, data))
  return [_check(number, each, what, axis) for number, axis in zip(data, 'xyz')]


# ---------------------------------------------------------------- one reader and one writer for each value

def _vec3(data: Any) -> Vec3:
  return Vec3(*_numbers(data, Vec3, float))


def _blockPos(data: Any) -> BlockPos:
  return BlockPos(*_numbers(data, BlockPos, int))


def _look(data: Any) -> Look:
  body = _object(data, Look)
  return Look(_need(body, 'yaw', float, 'a look'), _need(body, 'pitch', float, 'a look'))


def _item(data: Any) -> Item:
  if data is None:
    return Item.EMPTY
  if not isinstance(data, dict):
    raise ValueError('an item is a JSON object, or null for an empty slot; not %r' % (data,))
  what = 'an item'
  return Item(_need(data, 'id', str, what), _maybe(data, 'count', int, what, 1), _maybe(data, 'meta', int, what, 0),
              _maybe(data, 'nbt', str, what, ''))


def _itemJson(item: Item) -> Any:
  if item.empty:
    return None
  out = {'id': item.id, 'count': item.count, 'meta': item.meta}
  if item.snbt:
    out['nbt'] = item.snbt
  return out


def _block(data: Any) -> Block:
  body = _object(data, Block)
  what = 'a block'
  asked = 'tile' in body
  return Block(_need(body, 'id', str, what), _maybe(body, 'meta', int, what, 0), asked,
               _maybe(body, 'tile', str, what, ''))


def _blockJson(block: Block) -> dict:
  out = {'id': block.id, 'meta': block.meta}
  if block.tileAsked:
    out['tile'] = block.tileSnbt or None
  return out


def _inventory(data: Any) -> Inventory:
  body = _object(data, Inventory)
  what = 'an inventory'
  main = _need(body, 'main', list, what)
  armor = _need(body, 'armor', dict, what)
  return Inventory(_need(body, 'selected', int, what), tuple(_item(slot) for slot in main),
                   _item(armor.get('feet')), _item(armor.get('legs')), _item(armor.get('chest')),
                   _item(armor.get('head')), _item(body.get('cursor')))


def _inventoryJson(inventory: Inventory) -> dict:
  return {'selected': inventory.selected, 'main': [_itemJson(slot) for slot in inventory.main],
          'armor': {'feet': _itemJson(inventory.feet), 'legs': _itemJson(inventory.legs),
                    'chest': _itemJson(inventory.chest), 'head': _itemJson(inventory.head)},
          'cursor': _itemJson(inventory.cursor)}


def _ridingId(body: dict, what: str) -> int:
  riding = body.get('riding', _MISSING)
  if riding is _MISSING:
    raise ValueError('%s has no "riding"' % what)
  if riding is None:
    return -1
  return _need(_check(riding, dict, what, 'riding'), 'entity', int, what + '\'s "riding"')


def _entity(data: Any) -> Entity:
  body = _object(data, Entity)
  what = 'an entity'
  living = 'health' in body
  return Entity(
    entity=_need(body, 'entity', int, what), type=_need(body, 'type', str, what),
    className=_need(body, 'class', str, what), uuid=_need(body, 'uuid', str, what),
    pos=_vec3(_need(body, 'pos', list, what)), look=_look(_need(body, 'look', dict, what)),
    motion=_vec3(_need(body, 'motion', list, what)), dimension=_need(body, 'dimension', str, what),
    alive=_need(body, 'alive', bool, what), onGround=_need(body, 'on_ground', bool, what),
    name=_need(body, 'name', str, what), customName=_maybe(body, 'custom_name', str, what, ''),
    riding=_ridingId(body, what), fireTicks=_need(body, 'fire_ticks', int, what), living=living,
    health=_need(body, 'health', float, what) if living else 0.0,
    maxHealth=_need(body, 'max_health', float, what) if living else 0.0)


def _riding(ridingId: int) -> Any:
  return None if ridingId < 0 else {'entity': ridingId}


def _entityJson(entity: Entity) -> dict:
  out = {'entity': entity.entity, 'type': entity.type, 'class': entity.className, 'uuid': entity.uuid,
         'pos': _vec3Json(entity.pos), 'look': _lookJson(entity.look), 'motion': _vec3Json(entity.motion),
         'dimension': entity.dimension, 'alive': entity.alive, 'on_ground': entity.onGround, 'name': entity.name,
         'custom_name': entity.customName or None, 'riding': _riding(entity.riding), 'fire_ticks': entity.fireTicks}
  if entity.living:
    out['health'] = entity.health
    out['max_health'] = entity.maxHealth
  return out


def _effect(data: Any) -> Effect:
  body = _object(data, Effect)
  what = 'an effect'
  return Effect(_maybe(body, 'effect', str, what, ''), _need(body, 'id', int, what),
                _need(body, 'amplifier', int, what), _need(body, 'duration', int, what),
                _need(body, 'ambient', bool, what))


def _effectJson(effect: Effect) -> dict:
  return {'effect': effect.effect or None, 'id': effect.id, 'amplifier': effect.amplifier,
          'duration': effect.duration, 'ambient': effect.ambient}


def _player(data: Any) -> Player:
  body = _object(data, Player)
  what = 'a player'
  xp = _need(body, 'xp', dict, what)
  return Player(
    entity=_need(body, 'entity', int, what), name=_need(body, 'name', str, what), uuid=_need(body, 'uuid', str, what),
    pos=_vec3(_need(body, 'pos', list, what)), look=_look(_need(body, 'look', dict, what)),
    motion=_vec3(_need(body, 'motion', list, what)), dimension=_need(body, 'dimension', str, what),
    gameMode=_need(body, 'game_mode', str, what), health=_need(body, 'health', float, what),
    maxHealth=_need(body, 'max_health', float, what), food=_need(body, 'food', int, what),
    saturation=_need(body, 'saturation', float, what), xpLevel=_need(xp, 'level', int, 'a player\'s "xp"'),
    xpProgress=_need(xp, 'progress', float, 'a player\'s "xp"'), xpTotal=_need(xp, 'total', int, 'a player\'s "xp"'),
    onGround=_need(body, 'on_ground', bool, what), flying=_need(body, 'flying', bool, what),
    mayFly=_need(body, 'may_fly', bool, what), sneaking=_need(body, 'sneaking', bool, what),
    sprinting=_need(body, 'sprinting', bool, what), sleeping=_need(body, 'sleeping', bool, what),
    riding=_ridingId(body, what), fireTicks=_need(body, 'fire_ticks', int, what), air=_need(body, 'air', int, what),
    fallDistance=_need(body, 'fall_distance', float, what), arrows=_need(body, 'arrows', int, what),
    effects=tuple(_effect(effect) for effect in _need(body, 'effects', list, what)),
    camera=_maybe(body, 'camera', int, what, -1))


def _playerJson(player: Player) -> dict:
  out = {'entity': player.entity, 'name': player.name, 'uuid': player.uuid, 'pos': _vec3Json(player.pos),
         'look': _lookJson(player.look), 'motion': _vec3Json(player.motion), 'dimension': player.dimension,
         'game_mode': player.gameMode, 'health': player.health, 'max_health': player.maxHealth, 'food': player.food,
         'saturation': player.saturation,
         'xp': {'level': player.xpLevel, 'progress': player.xpProgress, 'total': player.xpTotal},
         'on_ground': player.onGround, 'flying': player.flying, 'may_fly': player.mayFly,
         'sneaking': player.sneaking, 'sprinting': player.sprinting, 'sleeping': player.sleeping,
         'riding': _riding(player.riding), 'fire_ticks': player.fireTicks, 'air': player.air,
         'fall_distance': player.fallDistance, 'arrows': player.arrows,
         'effects': [_effectJson(effect) for effect in player.effects]}
  if player.camera >= 0:
    out['camera'] = player.camera
  return out


def _chatLine(data: Any) -> ChatLine:
  body = _object(data, ChatLine)
  what = 'a chat line'
  return ChatLine(_need(body, 'plain', str, what), _need(body, 'formatted', str, what),
                  _need(body, 'json', str, what), _maybe(body, 'kind', str, what, ''))


def _chatLineJson(line: ChatLine) -> dict:
  out = {'plain': line.plain, 'formatted': line.formatted, 'json': line.json}
  if line.kind:
    out['kind'] = line.kind
  return out


def _sound(data: Any) -> Sound:
  body = _object(data, Sound)
  what = 'a sound'
  return Sound(_need(body, 'id', str, what), _need(body, 'known', bool, what), _maybe(body, 'from', str, what, ''),
               _need(body, 'volume', float, what), _need(body, 'pitch', float, what),
               _vec3(_need(body, 'pos', list, what)))


def _soundJson(sound: Sound) -> dict:
  return {'id': sound.id, 'known': sound.known, 'from': sound.callers or None, 'volume': sound.volume, 'pitch': sound.pitch,
          'pos': _vec3Json(sound.pos)}


def _logLine(data: Any) -> LogLine:
  body = _object(data, LogLine)
  what = 'a log line'
  return LogLine(_need(body, 'level', str, what), _need(body, 'logger', str, what), _need(body, 'thread', str, what),
                 _need(body, 'message', str, what), _maybe(body, 'thrown', str, what, ''))


def _logLineJson(line: LogLine) -> dict:
  #  'thrown' is always there, null for none, as the probe sends it
  return {'level': line.level, 'logger': line.logger, 'thread': line.thread, 'message': line.message,
          'thrown': line.thrown or None}


def _screen(data: Any) -> Any:
  if data is None:
    return None
  body = _object(data, Screen)
  what = 'a screen'
  return Screen(_need(body, 'class', str, what), _need(body, 'chat', bool, what),
                _need(body, 'container', bool, what), _need(body, 'pauses', bool, what))


def _screenJson(screen: Screen) -> dict:
  return {'class': screen.className, 'chat': screen.chat, 'container': screen.container, 'pauses': screen.pauses}


def _vec3Json(vec: Vec3) -> list:
  return [vec.x, vec.y, vec.z]


def _blockPosJson(pos: BlockPos) -> list:
  return [pos.x, pos.y, pos.z]


def _lookJson(look: Look) -> dict:
  return {'yaw': look.yaw, 'pitch': look.pitch}


_READERS = {Vec3: _vec3, BlockPos: _blockPos, Look: _look, Item: _item, Block: _block, Inventory: _inventory,
            Entity: _entity, Effect: _effect, Player: _player, ChatLine: _chatLine, Sound: _sound,
            LogLine: _logLine, Screen: _screen}
_WRITERS = {Vec3: _vec3Json, BlockPos: _blockPosJson, Look: _lookJson, Item: _itemJson, Block: _blockJson,
            Inventory: _inventoryJson, Entity: _entityJson, Effect: _effectJson, Player: _playerJson,
            ChatLine: _chatLineJson, Sound: _soundJson, LogLine: _logLineJson, Screen: _screenJson}


def fromJson(kind: type, data: Any) -> Any:
  """The value of that kind (a class of unittas.values) in the JSON; ValueError naming what is wrong."""
  reader: Callable = _READERS.get(kind)
  if reader is None:
    raise TypeError('%r is not one of the protocol\'s values' % (kind,))
  return reader(data)


def toJson(value: Any) -> Any:
  """The value as the protocol's JSON (None for Item.EMPTY, an empty slot)."""
  writer: Callable = _WRITERS.get(type(value))
  if writer is None:
    raise TypeError('%r is not one of the protocol\'s values' % (value,))
  return writer(value)

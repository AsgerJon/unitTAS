"""
The 'values' module holds the protocol's values (PROTOCOL.md section 5)
as frozen EZData: equal when their fields are, hashable, and shown by
their fields. The JSON edge, reading them from answers and writing them
into requests, is 'codec'.

No value is ever None. A text the wire leaves out is '' (an entity's
'customName' with no name tag); an id or a mode it leaves out is -1,
which no entity id and no camera mode is ('riding' for one that rides
nothing: 1.7.10 numbers its entities from 0); an entity that isn't
living has 'health' 0.0, and 'living' says which. An empty slot is
Item.EMPTY, as modern Minecraft's ItemStack.EMPTY is.

- Vec3, BlockPos, Look: places and directions (5.1).
- Item, Block: things (5.3, 5.4), their NBT as SNBT with a typed tree.
- Inventory: a player's whole inventory (8.5).
- Entity, Player, Effect: an entity's summary (5.5), a player (8.4).
- ChatLine, Sound, LogLine, Screen: what the chat, sound, log and
  screen events and screen.get carry (5.7, 7).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from worktoy.ezdata import EZData, EZField

from . import snbt


def _parsed(text: str):
  return snbt.loads(text) if text else None


class Vec3(EZData, frozen=True):
  """An entity's position (its feet), or its motion in blocks a tick."""
  x = EZField[float](0.0)
  y = EZField[float](0.0)
  z = EZField[float](0.0)


class BlockPos(EZData, frozen=True):
  """A block's position."""
  x = EZField[int](0)
  y = EZField[int](0)
  z = EZField[int](0)


class Look(EZData, frozen=True):
  """Where an entity looks, in degrees: yaw 0 is south, pitch 90 straight down."""
  yaw = EZField[float](0.0)
  pitch = EZField[float](0.0)


class Item(EZData, frozen=True):
  """
  An item stack: its registry name, count and meta, and its NBT as SNBT
  ('snbt', empty for none; 'nbt' is its typed tree, or None). An empty
  slot is Item.EMPTY.
  """
  id = EZField[str]('minecraft:air')
  count = EZField[int](1)
  meta = EZField[int](0)
  snbt = EZField[str]('')

  @property
  def empty(self) -> bool:
    """Whether this is an empty slot."""
    return self.count <= 0

  @property
  def nbt(self):
    """The NBT as a typed tree (unittas.snbt), or None."""
    return _parsed(self.snbt)


class Block(EZData, frozen=True):
  """
  A block: its registry name and meta, and its block entity's data when
  it was asked for ('tileAsked'; 'tileSnbt' empty for none; 'tile' is its
  typed tree, or None).
  """
  id = EZField[str]('minecraft:air')
  meta = EZField[int](0)
  tileAsked = EZField[bool](False)
  tileSnbt = EZField[str]('')

  @property
  def tile(self):
    """The block entity's data as a typed tree, or None."""
    return _parsed(self.tileSnbt)


class Inventory(EZData, frozen=True):
  """A player's inventory: the selected hotbar slot, the 36 main slots, the armour, the cursor's stack."""
  selected = EZField[int](0)
  main = EZField[tuple]()
  feet = EZField[Item]()
  legs = EZField[Item]()
  chest = EZField[Item]()
  head = EZField[Item]()
  cursor = EZField[Item]()

  @property
  def held(self) -> Item:
    """The stack in the selected hotbar slot."""
    return self.main[self.selected] if 0 <= self.selected < len(self.main) else Item.EMPTY


class Entity(EZData, frozen=True):
  """
  An entity's summary. 'customName' is '' for an entity with no name
  tag, 'riding' -1 for one that rides nothing, and 'health' and
  'maxHealth' 0.0 for one that isn't living.
  """
  entity = EZField[int](0)
  type = EZField[str]('')
  className = EZField[str]('')
  uuid = EZField[str]('')
  pos = EZField[Vec3]()
  look = EZField[Look]()
  motion = EZField[Vec3]()
  dimension = EZField[str]('')
  alive = EZField[bool](True)
  onGround = EZField[bool](False)
  name = EZField[str]('')
  customName = EZField[str]('')
  riding = EZField[int](-1)
  fireTicks = EZField[int](0)
  living = EZField[bool](False)
  health = EZField[float](0.0)
  maxHealth = EZField[float](0.0)


class Effect(EZData, frozen=True):
  """A potion effect on a player: its name (empty if the game has none for it), id, level, ticks left."""
  effect = EZField[str]('')
  id = EZField[int](0)
  amplifier = EZField[int](0)
  duration = EZField[int](0)
  ambient = EZField[bool](False)


class Player(EZData, frozen=True):
  """
  A player, as player.get gives it on either side. 'riding' is -1 when
  it rides nothing, and 'camera' -1 on the server side, which has none
  (0 is first person).
  """
  entity = EZField[int](0)
  name = EZField[str]('')
  uuid = EZField[str]('')
  pos = EZField[Vec3]()
  look = EZField[Look]()
  motion = EZField[Vec3]()
  dimension = EZField[str]('')
  gameMode = EZField[str]('')
  health = EZField[float](0.0)
  maxHealth = EZField[float](0.0)
  food = EZField[int](0)
  saturation = EZField[float](0.0)
  xpLevel = EZField[int](0)
  xpProgress = EZField[float](0.0)
  xpTotal = EZField[int](0)
  onGround = EZField[bool](False)
  flying = EZField[bool](False)
  mayFly = EZField[bool](False)
  sneaking = EZField[bool](False)
  sprinting = EZField[bool](False)
  sleeping = EZField[bool](False)
  riding = EZField[int](-1)
  fireTicks = EZField[int](0)
  air = EZField[int](0)
  fallDistance = EZField[float](0.0)
  arrows = EZField[int](0)
  effects = EZField[tuple]()
  camera = EZField[int](-1)


class ChatLine(EZData, frozen=True):
  """A chat line the client was shown; 'kind' is '' in 1.7.10, which has none."""
  plain = EZField[str]('')
  formatted = EZField[str]('')
  json = EZField[str]('')
  kind = EZField[str]('')


class Sound(EZData, frozen=True):
  """A sound the client was asked to play; 'callers' (who asked) only for one the game doesn't have, else ''."""
  id = EZField[str]('')
  known = EZField[bool](True)
  callers = EZField[str]('')
  volume = EZField[float](1.0)
  pitch = EZField[float](1.0)
  pos = EZField[Vec3]()


class LogLine(EZData, frozen=True):
  """A line of the game's log; 'thrown' (its exception, class and message) is '' for most."""
  level = EZField[str]('')
  logger = EZField[str]('')
  thread = EZField[str]('')
  message = EZField[str]('')
  thrown = EZField[str]('')


class Screen(EZData, frozen=True):
  """The client's open screen: its class, and whether it is the chat, a container, a screen that pauses."""
  className = EZField[str]('')
  chat = EZField[bool](False)
  container = EZField[bool](False)
  pauses = EZField[bool](False)


#  an empty slot, as modern Minecraft's ItemStack.EMPTY: made once the class is
Item.EMPTY = Item('minecraft:air', 0, 0, '')

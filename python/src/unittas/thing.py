"""
Thing: a thing at a place in a scenario (SPEC.md 15.3). Its verbs are
the agent's to carry out, as a player; its state is examined by command,
the default (SPEC.md 15.4), and each examination is noted for the test's
report line, saying which way it went.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from typing import TYPE_CHECKING

from mcdex import Version
from worktoy.desc import Field
from worktoy.mcls import BaseObject

from .errors import NeedFailed, NotFound
from .values import Block, BlockPos

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Optional

  from .blockview import BlockView
  from .container import Container
  from .perception import Perception
  from .scene import Scene

#  Before 1.13 flattened them, a block's on or off was in its meta or its
#  id: the bit of the meta that says on; the blocks whose meta above 0 is
#  on; and the blocks whose id says it, lit or not.
_ON_BIT = {'minecraft:lever': 8, 'minecraft:stone_button': 8,
           'minecraft:wooden_button': 8}
_PRESSED = frozenset({'minecraft:stone_pressure_plate',
                      'minecraft:wooden_pressure_plate',
                      'minecraft:light_weighted_pressure_plate',
                      'minecraft:heavy_weighted_pressure_plate'})
_LIT = {'minecraft:lit_redstone_lamp': True,
        'minecraft:redstone_lamp': False,
        'minecraft:redstone_torch': True,
        'minecraft:unlit_redstone_torch': False}


class Thing(BaseObject):
  """
  The thing at 'pos', which the scenario names by its mcdex 'member'.

    lever = scene.place(MCBlocks.Lever, at=(5, 0, 7))
    if not lever.isOn():
      lever.activate()
  """

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  NAMESPACE  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  #  Class Variables

  #  Fallback Variables

  #  Private Variables
  __scene__: Scene = None
  __member__: Any = None
  __pos__: BlockPos = None

  #  Public Variables
  scene = Field()
  member = Field()
  pos = Field()

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  GETTERS  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  @scene.GET
  def _getScene(self) -> Scene:
    """The scene the thing is in."""
    return self.__scene__

  @member.GET
  def _getMember(self) -> Any:
    """The mcdex member the scenario names the thing by."""
    return self.__member__

  @pos.GET
  def _getPos(self) -> BlockPos:
    """Where the thing is."""
    return self.__pos__

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  SETTERS  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  CONSTRUCTORS   # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  def __init__(self, scene: Scene, member: Any, pos: BlockPos) -> None:
    """The thing 'member' at 'pos' in 'scene'."""
    BaseObject.__init__(self)
    self.__scene__ = scene
    self.__member__ = member
    self.__pos__ = pos

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  PARENT METHODS   # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  def __str__(self) -> str:
    return self.label()

  def __bool__(self) -> bool:
    """bool(lever): whether it is on, by command."""
    return self.isOn()

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  DOMAIN SPECIFIC  # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  def label(self) -> str:
    """'MCBlocks.Lever at (5, 4, 7)'."""
    pos = self.__pos__
    return '%s.%s at (%d, %d, %d)' % (type(self.__member__).__name__,
                                      self.__member__.name, pos.x, pos.y,
                                      pos.z)

  # ---------------------------------------------------- verbs: the agent's

  def activate(self) -> Perception:
    """Uses it (a right click), as the agent does: SPEC.md 15.6 step 3."""
    return self.__scene__.agent.use(self.__pos__)

  def breakIt(self) -> Perception:
    """Breaks it, as the agent does."""
    return self.__scene__.agent.breakBlock(self.__pos__)

  def open(self) -> Container:
    """Opens it, as the agent does: its screen, as it shows it."""
    return self.__scene__.agent.open(self.__pos__)

  def examine(self, side: Optional[str] = None) -> BlockView:
    """
    Looks at it, as the agent does: its view, observed (SPEC.md 15.4),
    for the test's own computation on the pixels.
    """
    return self.__scene__.agent.examine(self.__pos__, side)

  def identify(self, among: Optional[Any] = None) -> Any:
    """
    What it is by its looks alone, as the agent tells (SPEC.md 15.4).
    Naming a few candidates in 'among' gives a significant advantage:
    among every full cube, red terracotta, red wool and a block of
    redstone can be difficult to tell apart in dim light, from a steep
    angle or from far off (Agent.identify).
    """
    return self.__scene__.agent.identify(self.__pos__, among)

  # ------------------------------------------- examinations, by command

  def isThere(self) -> bool:
    """Whether the block at its place is it."""
    game = self.__scene__.game
    block = game.block(self.__pos__, tile=True)
    there = self.__member__ in game.membersOf(block)
    return self._examined('isThere', there)

  def isOn(self) -> bool:
    """
    Whether it is on (a lever, a button, a pressure plate, a redstone
    lamp or torch), as the game holds it: before 1.13 by its id and meta,
    from 1.13 on by its block state (powered, lit, or a power above 0).

    Raises
    ------
    NeedFailed
      Nothing is at its place: the test's FAIL.
    TypeError
      The block there has no on or off.
    """
    game = self.__scene__.game
    block = game.block(self.__pos__)
    if block.id == 'minecraft:air':
      raise NeedFailed("%s isn't there: minecraft:air is" % self.label())
    if game.version >= Version.V1_13:
      return self._examined('isOn', self._onByState(block))
    if block.id in _ON_BIT:
      on = bool(block.meta & _ON_BIT[block.id])
    elif block.id in _PRESSED:
      on = block.meta > 0
    elif block.id in _LIT:
      on = _LIT[block.id]
    else:
      raise TypeError('%s: %s has no on or off' % (self.label(), block.id))
    return self._examined('isOn', on)

  def _onByState(self, block: Block) -> bool:
    """On or off by its block state; TypeError for one with neither."""
    properties = block.properties
    if 'powered' in properties:
      return properties['powered'] == 'true'
    if 'lit' in properties:
      return properties['lit'] == 'true'
    if 'power' in properties:
      return int(properties['power']) > 0
    raise TypeError('%s: %s has no on or off' % (self.label(), block.id))

  def contents(self) -> frozenset:
    """The mcdex members it holds (a chest), as the game holds them."""
    game = self.__scene__.game
    held = frozenset()
    for stack in self._stacks():
      if not stack.empty:
        held |= game.membersOf(stack)
    names = sorted('%s.%s' % (type(each).__name__, each.name)
                   for each in held)
    return self._examined('contents', held, ', '.join(names) or 'nothing')

  def stacks(self) -> tuple:
    """Its slots, an Item each (Item.EMPTY for an empty one)."""
    stacks = self._stacks()
    said = ', '.join('%d %s%s' % (each.count, each.id,
                                  ':%d' % each.meta if each.meta else '')
                     for each in stacks if not each.empty)
    return self._examined('stacks', stacks, said or 'nothing')

  def _stacks(self) -> tuple:
    try:
      return self.__scene__.game.items(self.__pos__)
    except NotFound as error:
      raise NeedFailed('%s holds nothing: %s' % (self.label(),
                                                 error.message)) from error

  def _examined(self, what: str, value: Any,
                said: Optional[str] = None) -> Any:
    """The value, noted as examined by command."""
    said = str(value) if said is None else said
    self.__scene__.note('examined by command: %s, %s: %s' % (
      self.label(), what, said))
    return value

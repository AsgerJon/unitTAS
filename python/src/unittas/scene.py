"""
Scene: a scenario's place in the world (SPEC.md 15.3): its origin, the
things in it, the agent that plays it, and what its tests examined.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from typing import TYPE_CHECKING

from worktoy.desc import Field
from worktoy.mcls import BaseObject

from .thing import Thing
from .values import Block, BlockPos

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Optional, Union

  from .agent import Agent
  from .api import Game


class Scene(BaseObject):
  """
  A scenario's scene. Places are given relative to its origin, so a
  scenario written for one version's world runs in another's (SPEC.md
  15.2). Its setup (place) is by command and isn't the agent; its things'
  verbs are the agent's; their examinations are noted here and, in a run,
  under the test's report line.

    lever = scene.place(MCBlocks.Lever, at=(5, 0, 7))
    chest = scene.thing(MCBlocks.Chest, at=(3, 0, 5))
  """

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  NAMESPACE  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  #  Class Variables

  #  Fallback Variables

  #  Private Variables
  __agent__: Agent = None
  __origin__: BlockPos = None
  #  every examination noted, in order
  __notes__: list = None

  #  Public Variables
  agent = Field()
  game = Field()
  origin = Field()
  notes = Field()

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  GETTERS  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  @agent.GET
  def _getAgent(self) -> Agent:
    """The agent that plays the scenario."""
    return self.__agent__

  @game.GET
  def _getGame(self) -> Game:
    """The game, the agent's."""
    return self.__agent__.game

  @origin.GET
  def _getOrigin(self) -> BlockPos:
    """The block the scene's places are given from."""
    return self.__origin__

  @notes.GET
  def _getNotes(self) -> tuple:
    """Every examination noted, in order."""
    return tuple(self.__notes__)

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  SETTERS  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  CONSTRUCTORS   # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  def __init__(self, agent: Agent, origin: BlockPos) -> None:
    """The scene the agent plays, its places given from 'origin'."""
    BaseObject.__init__(self)
    if not isinstance(origin, BlockPos):
      raise TypeError('a scene\'s origin is a BlockPos, not %r' % (origin,))
    self.__agent__ = agent
    self.__origin__ = origin
    self.__notes__ = []

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  DOMAIN SPECIFIC  # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  def at(self, offset: Union[BlockPos, tuple]) -> BlockPos:
    """The place 'offset' from the origin: a BlockPos or (dx, dy, dz)."""
    if isinstance(offset, BlockPos):
      offset = (offset.x, offset.y, offset.z)
    if len(offset) != 3 or not all(isinstance(each, int) and
                                   not isinstance(each, bool)
                                   for each in offset):
      raise TypeError('a place is a BlockPos or three whole numbers, not '
                      '%r' % (offset,))
    return self.__origin__.offset(*offset)

  def place(self, block: Any, at: Union[BlockPos, tuple],
            member: Any = None) -> Thing:
    """
    Puts 'block' (an MCBlocks member, or a Block value as the game's
    version has it) at the place 'at', by command: the scenario's setup,
    not the agent; done when the game shows it on both sides
    (Game.setBlock verifies). The thing there; a Block's member is
    mcdex's reading of it, unless 'member' says.
    """
    pos = self.at(at)
    if isinstance(block, Block):
      if member is None:
        found = self.game.membersOf(block)
        if len(found) != 1:
          infoSpec = """place reads %s:%d as %s in mcdex; say which with
          member="""
          info = infoSpec % (block.id, block.meta, sorted(
            '%s.%s' % (type(each).__name__, each.name) for each in found)
            or 'no member')
          raise TypeError(' '.join(info.split()))
        member = next(iter(found))
    elif member is None:
      member = block
    #  done when verified: on the client too, where the agent perceives
    self.game.setBlock(pos, block)
    return Thing(self, member, pos)

  def thing(self, member: Any, at: Union[BlockPos, tuple]) -> Thing:
    """The thing 'member' at the place 'at', already there."""
    return Thing(self, member, self.at(at))

  def note(self, text: str) -> None:
    """An examination, noted here and under the running test's line."""
    from .run import Run
    self.__notes__.append(text)
    if Run.current is not None:
      Run.current.note(text)

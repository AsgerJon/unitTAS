"""
Target: what the player's crosshair targets, by the game's own pick
(player.perceive, SPEC.md 15.6 step 1). A block, with the face hit; an
entity; or nothing within reach, Target.NOTHING.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from worktoy.ezdata import EZData, EZField

from .values import BlockPos, Vec3

#  a block's faces, by the names every version's probe gives them
FACES = ('down', 'up', 'north', 'south', 'west', 'east')


class Target(EZData, frozen=True):
  """
  The crosshair's target. 'kind' is 'block' or 'entity', or '' for
  nothing within reach. A block's are 'pos', 'face', 'id', 'meta' (-1
  where the version has none: 1.13 on) and 'state' ((name, value) pairs,
  empty before 1.13); an entity's 'entity' (its id) and 'type'. 'hit' is
  where the ray met it.
  """

  kind = EZField[str]('')
  pos = EZField[BlockPos]()
  face = EZField[str]('')
  id = EZField[str]('')
  meta = EZField[int](0)
  entity = EZField[int](-1)
  type = EZField[str]('')
  hit = EZField[Vec3]()
  state = EZField[tuple]()

  @property
  def nothing(self) -> bool:
    """Whether nothing is within reach."""
    return not self.kind

  @property
  def properties(self) -> dict:
    """A block's state's properties by name."""
    return dict(self.state)


#  nothing within reach: made once the class is
Target.NOTHING = Target()

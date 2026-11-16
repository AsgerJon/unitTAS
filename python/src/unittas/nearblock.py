"""
NearBlock: a block near the player as the game collides with it
(player.perceive, SPEC.md 15.6 step 1).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from worktoy.ezdata import EZData, EZField

from .values import BlockPos


class NearBlock(EZData, frozen=True):
  """
  A block that isn't air: where it is, its registry name and meta, its
  collision boxes (a tuple of Box: none for a flower, several for
  stairs), whether it is a liquid, whether the player can climb it, and
  whether a hand's click opens and shuts it (a wooden door, a gate).
  """

  pos = EZField[BlockPos]()
  id = EZField[str]('minecraft:air')
  meta = EZField[int](0)
  boxes = EZField[tuple]()
  liquid = EZField[bool](False)
  climbable = EZField[bool](False)
  opens = EZField[bool](False)

  @property
  def solid(self) -> bool:
    """Whether anything in it stops the player."""
    return bool(self.boxes)

  @property
  def top(self) -> float:
    """The height of its highest box's top; its own floor with none."""
    if not self.boxes:
      return float(self.pos.y)
    return max(box.maxY for box in self.boxes)

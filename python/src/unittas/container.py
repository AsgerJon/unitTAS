"""
Container: an open container as its screen shows it (container.get,
PROTOCOL.md 8.5; SPEC.md 15.6 step 4).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from worktoy.ezdata import EZData, EZField


class Container(EZData, frozen=True):
  """
  The open container: its class, its window's number, whether it is the
  player's own inventory rather than one opened, and its slots, an Item
  for each by its number (Item.EMPTY for an empty one). The player's own
  slots among them run from 'playerFirst' to 'playerLast', or none (-1).
  """

  className = EZField[str]('')
  window = EZField[int](0)
  playerOwn = EZField[bool](False)
  slots = EZField[tuple]()
  playerFirst = EZField[int](-1)
  playerLast = EZField[int](-1)

  @property
  def own(self) -> tuple:
    """The numbers of the player's own slots."""
    if self.playerFirst < 0:
      return ()
    return tuple(range(self.playerFirst, self.playerLast + 1))

  @property
  def theirs(self) -> tuple:
    """The numbers of the container's slots, the player's left out."""
    own = set(self.own)
    return tuple(i for i in range(len(self.slots)) if i not in own)

  @property
  def contents(self) -> tuple:
    """What the container's own slots hold, an Item for each."""
    return tuple(self.slots[i] for i in self.theirs)

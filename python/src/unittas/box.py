"""
Box: a collision box as the game gives it (player.perceive, SPEC.md
15.6 step 1), its least corner and its greatest, in blocks.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from worktoy.ezdata import EZData, EZField


class Box(EZData, frozen=True):
  """A box from (minX, minY, minZ) to (maxX, maxY, maxZ)."""

  minX = EZField[float](0.0)
  minY = EZField[float](0.0)
  minZ = EZField[float](0.0)
  maxX = EZField[float](0.0)
  maxY = EZField[float](0.0)
  maxZ = EZField[float](0.0)

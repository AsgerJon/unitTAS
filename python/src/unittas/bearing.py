"""
Bearing: where the client's player is, which way it looks and how it
moves, at one client tick: mouse.rate's answer (SPEC.md 19.7 step 12),
what a controller steering every tick needs from it.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from worktoy.ezdata import EZData, EZField

from .values import Look, Vec3


class Bearing(EZData, frozen=True):
  """
  The client's tick ('tick'), where the feet are ('pos'), the look, and
  the motion, as the client's player has them.
  """

  tick = EZField[int](0)
  pos = EZField[Vec3]()
  look = EZField[Look]()
  motion = EZField[Vec3]()

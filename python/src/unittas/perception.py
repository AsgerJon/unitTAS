"""
Perception: what the client's player perceives at one tick
(player.perceive, SPEC.md 15.6 step 1), for the agent's brain. The probe
says what is there; deciding anything from it is the agent's.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from worktoy.ezdata import EZData, EZField

from .box import Box
from .mouserate import MouseRate
from .target import Target
from .values import Look, Vec3


class Perception(EZData, frozen=True):
  """
  The client's tick ('tick'); where the feet are ('pos') and the eye
  the crosshair's ray starts from ('eye'); the player's own collision
  box; its look and motion; whether it stands on the ground, ran into
  something across or up and down ('collidedHorizontally',
  'collidedVertically'), is in water or lava, on a ladder, sneaking,
  sprinting or flying; how far it reaches blocks and entities; the rate
  its look turns at ('mouseRate', mouse.rate's: 0 and 0 for none); what
  its crosshair targets; and the blocks around it that aren't air (a
  tuple of NearBlock).
  """

  tick = EZField[int](0)
  pos = EZField[Vec3]()
  eye = EZField[Vec3]()
  box = EZField[Box]()
  look = EZField[Look]()
  motion = EZField[Vec3]()
  onGround = EZField[bool](False)
  collidedHorizontally = EZField[bool](False)
  collidedVertically = EZField[bool](False)
  inWater = EZField[bool](False)
  inLava = EZField[bool](False)
  onLadder = EZField[bool](False)
  sneaking = EZField[bool](False)
  sprinting = EZField[bool](False)
  flying = EZField[bool](False)
  blockReach = EZField[float](0.0)
  entityReach = EZField[float](0.0)
  mouseRate = EZField[MouseRate]()
  target = EZField[Target]()
  blocks = EZField[tuple]()

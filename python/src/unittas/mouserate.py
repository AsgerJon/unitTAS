"""
MouseRate: the rate the client's player's look turns at, as mouse.rate
set it (SPEC.md 19.7 step 12), as player.perceive says it. The probe
turns the look by it every frame, by the frame's share of a tick.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from worktoy.ezdata import EZData, EZField


class MouseRate(EZData, frozen=True):
  """
  'yaw' and 'pitch' in degrees a tick, their signs player.look's (the
  yaw growing as it grows there, a pitch above 0 turning down); 0 and 0
  for none. 'frames' is how many frames it has turned the look in since
  it was set (0 for none).
  """

  yaw = EZField[float](0.0)
  pitch = EZField[float](0.0)
  frames = EZField[int](0)

  @property
  def none(self) -> bool:
    """Whether no rate is in force: 0 and 0."""
    return self.yaw == 0.0 and self.pitch == 0.0

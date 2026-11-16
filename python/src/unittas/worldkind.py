"""
WorldKind: a world's kind (SPEC.md 17.4), carrying the name world.create
takes for it; each probe makes it as its version's own (1.7.10's world
types, 26.3's presets).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from worktoy.keenum import Kee, KeeNum


class WorldKind(KeeNum, strictCase=False):
  """A world's kind; its value is world.create's 'type'."""

  Default = Kee[str]('default')
  Flat = Kee[str]('flat')
  LargeBiomes = Kee[str]('large_biomes')
  Amplified = Kee[str]('amplified')

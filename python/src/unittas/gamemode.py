"""
GameMode: the game mode a world is made in (SPEC.md 17.4), carrying the
name world.create takes for it.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from worktoy.keenum import Kee, KeeNum


class GameMode(KeeNum, strictCase=False):
  """A game mode; its value is world.create's 'game_mode'."""

  Survival = Kee[str]('survival')
  Creative = Kee[str]('creative')
  Adventure = Kee[str]('adventure')

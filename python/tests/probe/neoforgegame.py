"""
A real client with NeoForge for the probe's game tests (SPEC.md 19.7 step
7): FabricGame's, with NeoForge on top instead (the loader a NeoForge mod
under test would bring), installed by NeoForge's own installer into the
download cache as the launcher first needs it, and unitTAS's probe beside
it as a Java agent, mods/ empty; no table of names (NeoForge runs the game
under Mojang's), in run/neoforge-VERSION. test_neoforge's own and every
test class on a NeoForge port (ports.py) start it.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from fabricgame import FabricGame

LOADER = 'neoforge'
#  each version's one NeoForge (SPEC.md 19.7 V12), as unittas.spec's
NEOFORGE = {'1.21.1': '21.1.267'}


class NeoForgeGame(FabricGame):
  """
  One launch of a real NeoForge client of the version, as FabricGame's of
  a Fabric one.
  """

  def loader(self) -> tuple:
    return LOADER, NEOFORGE[self.__minecraft__]

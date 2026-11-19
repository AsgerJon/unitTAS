"""
A real client with Forge on a modern version for the probe's game tests
(SPEC.md 19.7 step 8): FabricGame's, with Forge on top instead (the loader
a Forge mod under test would bring), installed by Forge's own installer
into the download cache as the launcher first needs it, and unitTAS's
probe beside it as a Java agent, mods/ empty, renamed to Forge's names as
it loads (Mojang's classes, SRG's members: the launcher's table), in
run/forge-VERSION. test_forge's own and every test class on a Forge port
(ports.py) start it.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from fabricgame import FabricGame

LOADER = 'forge'
#  each version's one Forge (SPEC.md 19.7 V14), as unittas.spec's
FORGE = {'1.20.1': '47.4.28', '1.16.1': '32.0.108'}


class ForgeGame(FabricGame):
  """
  One launch of a real Forge client of a modern version, as FabricGame's
  of a Fabric one.
  """

  def loader(self) -> tuple:
    return LOADER, FORGE[self.__minecraft__]

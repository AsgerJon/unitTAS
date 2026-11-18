"""
The probe beside Forge on a modern version (SPEC.md 19.7 step 8c): as beside
NeoForge (test_neoforge's game checks, by their loader's own), in one game:
a real 1.20.1 Forge 47.4.28 client from unitTAS's own launcher
(bin/launch_client.py --minecraft 1.20.1 --loader forge --loader-version
47.4.28), Forge installed by its own installer into the download cache as
the launcher first needs it. Its hello says the game runs under SRG's names
(Mojang's classes, SRG's members: the launcher's table), on Java 17; its
ready names Forge's mods (minecraft and forge, not unitTAS).

  python -m unittas.selftest test_forge.
  (through the watcher: "probe test_forge.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import unittest

import test_neoforge
from forgegame import FORGE, ForgeGame
from ports import forgeVersion


class ForgeGameTests(test_neoforge.NeoForgeGameTests):
  """
  The probe beside Forge, on the Forge port's version (1.20.1 on any other
  port).
  """
  GAME = ForgeGame
  LOADER = 'forge'
  LOADERS = FORGE
  NAMES = 'srg'
  JAVAS = {'1.20.1': '17'}

  @staticmethod
  def gameVersion() -> str:
    return forgeVersion()


if __name__ == '__main__':
  unittest.main()

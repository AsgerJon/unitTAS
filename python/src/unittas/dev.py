"""
The 'dev' module starts unitTAS's own development client for the probe's
tests: './gradlew runClient', through './unittas.sh probe' so that the
script's checks still hold (no game already open in run/client, the test
display, the project's Gradle cache). What every launch shares (the start
file, the game folder's own files kept aside, the hello, the stop) is
LaunchedGame's (unittas.game).

- DevGame: one launch of the development client.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os

from .game import HELLO_SECONDS, LOADED, LOADED_GRACE, LaunchedGame

__all__ = ['DevGame', 'HELLO_SECONDS', 'LOADED', 'LOADED_GRACE']


class DevGame(LaunchedGame):
  """
  One launch of the development client in 'run/client': its output, the
  Gradle run's, in '<results>/<name>/gradle.log'. './unittas.sh probe'
  stops the game when it is told to stop.
  """

  def gameFolder(self) -> str:
    return os.path.join(self.root(), 'run', 'client')

  def command(self) -> list:
    return ['./unittas.sh', 'probe']

  def outputName(self) -> str:
    return 'gradle.log'

  def launchName(self) -> str:
    #  ./unittas.sh writes the game's output to gradle.log itself (UNITTAS_RESULTS); its own lines go here
    return 'launch.log'

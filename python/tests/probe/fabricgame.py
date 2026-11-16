"""
A real 26.3 Fabric client for the probe's game tests (SPEC.md 12, 19.7): fabric/'s jar built (once a run), and one
launch of the game by unitTAS's own launcher in run/fabric-26.3, the jar in its mods/. test_fabric's own and every
test class on the 26.3-fabric port (ports.py) start it.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import signal
import subprocess
import sys

from probegame import ROOT
from unittas.cache import defaultRoot
from unittas.game import LaunchedGame
from unittas.release import gameJvms, putMods

FABRIC = os.path.join(ROOT, 'fabric')
MINECRAFT, LOADER, LOADER_VERSION = '26.3', 'fabric', '0.20.1'
TITLE = 'net.minecraft.client.gui.screens.TitleScreen'
JAR = os.path.join(FABRIC, 'build', 'libs', 'unittas-probe-26.3-fabric.jar')
JAVA_25 = os.environ.get('UNITTAS_JAVA_25', '/usr/lib/jvm/java-25-openjdk')
#  the test world (step 4): the run's seed; a flat world's layers as 26.3's Customize box writes them, bedrock, two
#  dirt and grass on plains, no structures (1.7.10's are '2;7,2x3,2;1;')
SEED = 20261029
LAYERS_26 = 'minecraft:bedrock,2*minecraft:dirt,minecraft:grass_block;minecraft:plains'
COPY, TERRAIN = 'unittas-probe-copy', 'unittas-terrain'
#  where the reset puts the player in 26.3's flat test world: on its grass (the surface y -61), at the spawn
START_26 = (0.5, -60.0, 0.5)
#  the core: compiled into both probes from one place (D5); the world operations' bodies too (step 4a), their game
#  calls the port's GameWorlds
CORE = ('io/github/asgerjon/unittas/probe/link/Json.class', 'io/github/asgerjon/unittas/probe/link/Link.class',
        'io/github/asgerjon/unittas/probe/link/StartFile.class', 'io/github/asgerjon/unittas/probe/Probe.class',
        'io/github/asgerjon/unittas/probe/Ops.class', 'io/github/asgerjon/unittas/probe/Call.class',
        'io/github/asgerjon/unittas/probe/WorldOps.class', 'io/github/asgerjon/unittas/probe/GameWorlds.class')


#  the jar this run built: fabric/ is built once a run, whichever class asks first
_BUILT = []


def buildFabric(log: str) -> str:
  """
  fabric/'s jar, built (its own wrapper, Java 25, the project's own Gradle home, no daemon), its output into 'log';
  once a run: asked again, the jar the first build made.
  """
  if _BUILT:
    return _BUILT[0]
  environ = dict(os.environ, JAVA_HOME=JAVA_25, GRADLE_USER_HOME=os.path.join(ROOT, '.gradle-home'))
  os.makedirs(os.path.dirname(log), exist_ok=True)
  with open(log, 'ab') as output:
    code = subprocess.call(['./gradlew', '--no-daemon', '--console=plain', 'build'], cwd=FABRIC, env=environ,
                           stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT)
  if code != 0:
    raise RuntimeError("fabric/'s build failed (exit %d); its log: %s" % (code, log))
  _BUILT.append(JAR)
  return JAR


class FabricGame(LaunchedGame):
  """
  One launch of a real 26.3 Fabric client in run/fabric-26.3, its output in '<results>/<name>/client.log': the
  probe's jar in mods/, the game started by unitTAS's own launcher (any version with a loader on top) in the test
  display, the download cache filled as it needs.
  """

  def __init__(self, results: str, jar: str, name: str = 'fabric', cache: str = None) -> None:
    LaunchedGame.__init__(self, ROOT, results, name)
    self.__jar__ = jar
    self.__cache__ = cache or defaultRoot()

  def gameFolder(self) -> str:
    return os.path.join(ROOT, 'run', 'fabric-' + MINECRAFT)

  def command(self) -> list:
    return [os.path.join(ROOT, 'unittas-display.sh'), sys.executable, '-I', os.path.join(ROOT, 'bin', 'launch_client.py'),
            '--game', self.gameFolder(), '--cache', self.__cache__, '--minecraft', MINECRAFT, '--loader', LOADER,
            '--loader-version', LOADER_VERSION]

  def outputName(self) -> str:
    return 'client.log'

  def prepare(self) -> None:
    putMods(self.gameFolder(), [self.__jar__], os.path.join(self.results, 'mods-before-this-run'))
    # a returning player's options: 26.3's first launch opens on its accessibility onboarding, and a world's first
    # minutes show the movement tutorial's hints
    with open(os.path.join(self.gameFolder(), 'options.txt'), 'w', encoding='utf-8') as file:
      file.write('onboardAccessibility:false\ntutorialStep:none\n')

  def terminate(self) -> None:
    """The display's process group (the display, the game in it); and the game's JVM, found by its folder."""
    try:
      os.killpg(self.process().pid, signal.SIGTERM)
    except ProcessLookupError:
      pass
    for pid in gameJvms(self.gameFolder()):
      try:
        os.kill(pid, signal.SIGTERM)
      except ProcessLookupError:
        pass

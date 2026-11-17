"""
A real vanilla client with the loader-free probe (SPEC.md 19.7 steps 5, 6c and 6e), of 26.3, 1.21.1 or 1.20.1: the version's
agent's jar built (once a run, by bin/build_agent.py --minecraft VERSION), and one launch of the game as Mojang ships
it, no loader at all, by unitTAS's own launcher in run/vanilla-VERSION, the probe a Java agent on its command line
(-javaagent:JAR=GAME; before 26.1 also the table of its names, which the launcher gives), nothing in mods/.
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
from unittas.release import gameJvms

MINECRAFT = '26.3'
JAR = os.path.join(ROOT, 'agent', 'build', 'unittas-probe-%s.jar')
#  the game's classes each version's agent hooks (its hooks file), by their Mojang internal names, as ready names
#  them rewritten
HOOKED = {
  '26.3': ['net/minecraft/client/KeyboardHandler', 'net/minecraft/client/Minecraft',
           'net/minecraft/client/MouseHandler', 'net/minecraft/client/gui/Gui',
           'net/minecraft/client/gui/components/ChatComponent', 'net/minecraft/client/sounds/SoundManager',
           'net/minecraft/server/MinecraftServer'],
  '1.21.1': ['net/minecraft/client/KeyboardHandler', 'net/minecraft/client/Minecraft',
             'net/minecraft/client/MouseHandler', 'net/minecraft/client/gui/components/ChatComponent',
             'net/minecraft/client/renderer/LevelRenderer', 'net/minecraft/client/sounds/SoundManager',
             'net/minecraft/server/MinecraftServer'],
}
#  1.20.1 hooks 1.21.1's classes (three of their methods by its own descriptors or names)
HOOKED['1.20.1'] = HOOKED['1.21.1']

#  the jars this run built, by version: each built once a run, whichever class asks first
_BUILT = {}


def buildAgent(log: str, minecraft: str = MINECRAFT) -> str:
  """The version's agent's jar, built by bin/build_agent.py, its output into 'log'; once a run."""
  if minecraft in _BUILT:
    return _BUILT[minecraft]
  jar = JAR % minecraft
  os.makedirs(os.path.dirname(log), exist_ok=True)
  with open(log, 'ab') as output:
    code = subprocess.call([sys.executable, '-I', os.path.join(ROOT, 'bin', 'build_agent.py'), '--minecraft',
                            minecraft, '--out', jar],
                           cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT)
  if code != 0:
    raise RuntimeError("the agent's build failed (exit %d); its log: %s" % (code, log))
  _BUILT[minecraft] = jar
  return jar


class AgentGame(LaunchedGame):
  """
  One launch of a vanilla client of the version in run/vanilla-VERSION with the probe as a Java agent, its output in
  '<results>/<name>/client.log', in the test display, the download cache filled as it needs.
  """

  def __init__(self, results: str, jar: str, name: str = 'agent', cache: str = None,
               minecraft: str = MINECRAFT) -> None:
    LaunchedGame.__init__(self, ROOT, results, name)
    self.__jar__ = jar
    self.__cache__ = cache or defaultRoot()
    self.__minecraft__ = minecraft

  def gameFolder(self) -> str:
    return os.path.join(ROOT, 'run', 'vanilla-' + self.__minecraft__)

  def command(self) -> list:
    return [os.path.join(ROOT, 'unittas-display.sh'), sys.executable, '-I', os.path.join(ROOT, 'bin', 'launch_client.py'),
            '--game', self.gameFolder(), '--cache', self.__cache__, '--minecraft', self.__minecraft__, '--agent',
            self.__jar__]

  def outputName(self) -> str:
    return 'client.log'

  def prepare(self) -> None:
    os.makedirs(self.gameFolder(), exist_ok=True)
    # a returning player's options: a first launch opens on the accessibility onboarding, and a world's first
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

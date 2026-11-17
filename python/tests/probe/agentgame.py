"""
A real vanilla 26.3 client with the loader-free probe (SPEC.md 19.7 step 5): the agent's jar built (once a run, by
bin/build_agent.py), and one launch of the game as Mojang ships it, no loader at all, by unitTAS's own launcher in
run/vanilla-26.3, the probe a Java agent on its command line (-javaagent:JAR=GAME), nothing in mods/.
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
JAR = os.path.join(ROOT, 'agent', 'build', 'unittas-probe-26.3.jar')
#  the game's classes the agent hooks (its Hooks), by their internal names, as ready names them rewritten
HOOKED = ['net/minecraft/client/KeyboardHandler', 'net/minecraft/client/Minecraft',
          'net/minecraft/client/MouseHandler', 'net/minecraft/client/gui/Gui',
          'net/minecraft/client/gui/components/ChatComponent', 'net/minecraft/client/sounds/SoundManager',
          'net/minecraft/server/MinecraftServer']

#  the jar this run built: built once a run, whichever class asks first
_BUILT = []


def buildAgent(log: str) -> str:
  """The agent's jar, built by bin/build_agent.py, its output into 'log'; once a run."""
  if _BUILT:
    return _BUILT[0]
  os.makedirs(os.path.dirname(log), exist_ok=True)
  with open(log, 'ab') as output:
    code = subprocess.call([sys.executable, '-I', os.path.join(ROOT, 'bin', 'build_agent.py'), '--out', JAR],
                           cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT)
  if code != 0:
    raise RuntimeError("the agent's build failed (exit %d); its log: %s" % (code, log))
  _BUILT.append(JAR)
  return JAR


class AgentGame(LaunchedGame):
  """
  One launch of a vanilla 26.3 client in run/vanilla-26.3 with the probe as a Java agent, its output in
  '<results>/<name>/client.log', in the test display, the download cache filled as it needs.
  """

  def __init__(self, results: str, jar: str, name: str = 'agent', cache: str = None) -> None:
    LaunchedGame.__init__(self, ROOT, results, name)
    self.__jar__ = jar
    self.__cache__ = cache or defaultRoot()

  def gameFolder(self) -> str:
    return os.path.join(ROOT, 'run', 'vanilla-' + MINECRAFT)

  def command(self) -> list:
    return [os.path.join(ROOT, 'unittas-display.sh'), sys.executable, '-I', os.path.join(ROOT, 'bin', 'launch_client.py'),
            '--game', self.gameFolder(), '--cache', self.__cache__, '--minecraft', MINECRAFT, '--agent', self.__jar__]

  def outputName(self) -> str:
    return 'client.log'

  def prepare(self) -> None:
    os.makedirs(self.gameFolder(), exist_ok=True)
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

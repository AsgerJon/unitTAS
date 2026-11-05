"""
The 'release' module starts the real 1.7.10 client for the probe's tests:
the release jar as a player has it, beside UniMixins, in 'run/release',
started by unitTAS's own launcher (bin/launch_client.py: Forge from the
Gradle cache, Java 8) on the test display, as './unittas.sh oldsaves'
starts it for the Java runner.

- releaseJarIn: the release jar a build made, checked to be that build's.
- releaseJar: builds the release jar and finds it.
- putMods: a game folder's mods/ made exactly the given jars.
- ReleaseGame: one launch of the real client.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import glob
import os
import shutil
import signal
import subprocess
import sys

from .game import LaunchedGame

def releaseJarIn(libs: str, version: str) -> str:
  """
  The release jar of that version in a build's jars: remapJar's,
  unittas-<version>.jar. Not one older than the dev jar it is remapped
  from: a build that remade only the dev jar (./gradlew assemble does)
  left an earlier build's beside it.
  """
  release = os.path.join(libs, 'unittas-%s.jar' % version)
  dev = os.path.join(libs, 'unittas-%s-dev.jar' % version)
  if not os.path.isfile(release):
    raise FileNotFoundError('no release jar %s' % release)
  if os.path.isfile(dev) and os.path.getmtime(release) < os.path.getmtime(dev):
    raise RuntimeError('%s is older than %s, the dev jar it is remapped from: an earlier build\'s' % (release, dev))
  return release


def modVersion(root: str) -> str:
  """unitTAS's version, as gradle.properties says it (the release tooling stamps it there)."""
  with open(os.path.join(root, 'gradle.properties'), encoding='utf-8') as properties:
    for line in properties:
      if line.startswith('mod_version='):
        return line.split('=', 1)[1].strip()
  raise ValueError('no mod_version in %s' % os.path.join(root, 'gradle.properties'))


def releaseJar(root: str, log: str) -> str:
  """
  Builds the release jar ('./gradlew remapJar', which makes the dev jar
  first; its output into 'log') and returns it, checked to be this build's.
  """
  with open(log, 'ab') as output:
    code = subprocess.call(['./gradlew', '--console=plain', 'remapJar'], cwd=root, stdin=subprocess.DEVNULL,
                           stdout=output, stderr=subprocess.STDOUT)
  if code != 0:
    raise RuntimeError('the release build failed (exit %d); its log: %s' % (code, log))
  return releaseJarIn(os.path.join(root, 'build', 'libs'), modVersion(root))


def putMods(gameDir: str, jars: list, aside: str) -> list:
  """
  The game folder's mods/ made to hold exactly these jars. What it held
  goes into 'aside' (made only when there is something to keep), as
  unittas-oldsaves.sh keeps it. The names now in mods/.
  """
  mods = os.path.join(gameDir, 'mods')
  os.makedirs(mods, exist_ok=True)
  there = sorted(os.listdir(mods))
  if there:
    os.makedirs(aside, exist_ok=True)
    for name in there:
      shutil.move(os.path.join(mods, name), os.path.join(aside, name))
  for jar in jars:
    shutil.copy2(jar, os.path.join(mods, os.path.basename(jar)))
  return sorted(os.listdir(mods))


class ReleaseGame(LaunchedGame):
  """
  One launch of the real client in 'run/release', its output in
  '<results>/<name>/client.log'. Before it starts, the release jar is
  built (or the one given is used) and mods/ holds it and
  run/oldsaves/mods/*.jar.
  """

  def __init__(self, root: str, results: str, name: str = 'release', jar: str = None) -> None:
    LaunchedGame.__init__(self, root, results, name)
    self.__jar__ = jar
    self.__mods__ = []

  def gameFolder(self) -> str:
    return os.path.join(self.root(), 'run', 'release')

  def command(self) -> list:
    return [os.path.join(self.root(), 'unittas-display.sh'), sys.executable, '-I',
            os.path.join(self.root(), 'bin', 'launch_client.py'), '--game', self.gameFolder()]

  def outputName(self) -> str:
    return 'client.log'

  def mods(self) -> list:
    """The jars in mods/ for this launch."""
    return list(self.__mods__)

  def prepare(self) -> None:
    jar = self.__jar__ or releaseJar(self.root(), os.path.join(self.results, 'build.log'))
    libraries = sorted(glob.glob(os.path.join(self.root(), 'run', 'oldsaves', 'mods', '*.jar')))
    self.__mods__ = putMods(self.gameFolder(), [jar] + libraries, os.path.join(self.results, 'mods-before-this-run'))

  def terminate(self) -> None:
    """The display's process group (the display, the game in it); and the game's JVM, found by its folder."""
    process = self.process()
    try:
      os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
      pass
    for pid in gameJvms(self.gameFolder()):
      try:
        os.kill(pid, signal.SIGTERM)
      except ProcessLookupError:
        pass


def gameJvms(gameDir: str) -> list:
  """
  The java processes whose working folder is the game's: its JVM (the
  launcher moves there before it becomes java), as ./unittas.sh finds the
  development client's. Only java: nothing else working there is touched.
  """
  found = []
  want = os.path.realpath(gameDir)
  for entry in os.listdir('/proc'):
    if not entry.isdigit():
      continue
    try:
      with open('/proc/%s/comm' % entry, encoding='utf-8') as comm:
        if comm.read().strip() != 'java':
          continue
      if os.path.realpath(os.readlink('/proc/%s/cwd' % entry)) == want:
        found.append(int(entry))
    except OSError:
      continue
  return found

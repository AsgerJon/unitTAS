"""
The 'specgame' module starts the game an instance spec names (SPEC.md 9.3,
step 6b), as a LaunchedGame:

- RealGame (client = "real"): a real client in the spec's game folder, its
  mods/ made of the probe, the spec's mod jars and its libraries (files, and
  maven: ones fetched from the spec's repositories, each held to the
  repository's sha1), started by unittas.launcher from the Gradle cache
  (UNITTAS_GRADLE_HOME) and the download cache;
- GradleGame (client = "gradle"): the mod's own Gradle run (its task in its
  project), the start file in the spec's game folder.

Both: the spec's build first, when it names one (run without a shell); a mod
jar of the spec's own project older than the newest file under its src/
refused, as not built from these sources (an up-to-date build is fine, its
jar is newer than they are); the spec's config copied into the game's
config/ and its options set in options.txt, both undone when the game has
gone (LaunchedGame keeps the folder's own aside first); the test display
(unittas.display) in front of the command.

- gameFor: the right kind of game for a spec.
- RealGame, GradleGame: the two kinds.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import fnmatch
import glob
import os
import shutil
import signal
import subprocess
import sys
import time
from typing import TYPE_CHECKING

from .cache import Cache, CacheError
from .display import environment, prefix
from .launcher import PLAYER_NAME
from .game import LaunchedGame
from .release import gameJvms, putMods
from .spec import MavenLibrary, SpecError

if TYPE_CHECKING:  # pragma: no cover
  from typing import Callable, Optional

  from .spec import InstanceSpec

#  Where a built package keeps the probe jars it carries (SPEC.md 9.6, decision 1); none in a development install.
BUNDLED = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'probes')


def gameFor(spec: InstanceSpec, results: str, name: str = 'game', cache: Optional[Cache] = None) -> LaunchedGame:
  """The game the spec names: a real client, or the mod's Gradle run."""
  if spec.client == 'gradle':
    return GradleGame(spec, results, name)
  return RealGame(spec, results, name, cache=cache)


# ---------------------------------------------------------------- what both kinds do first


def _build(spec: InstanceSpec, log: str) -> None:
  """The spec's build, without a shell, from the spec's folder; SpecError when it fails."""
  if not spec.build:
    return
  os.makedirs(os.path.dirname(log), exist_ok=True)
  with open(log, 'ab') as output:
    code = subprocess.call(list(spec.build), cwd=spec.folder, stdin=subprocess.DEVNULL, stdout=output,
                           stderr=subprocess.STDOUT)
  if code != 0:
    raise SpecError('%s: "build" failed (exit %d); its output: %s' % (spec.path, code, log))


def _newestSource(folder: str) -> float:
  newest = 0.0
  for where, _, names in os.walk(os.path.join(folder, 'src')):
    for name in names:
      newest = max(newest, os.path.getmtime(os.path.join(where, name)))
  return newest


def _checkedJars(spec: InstanceSpec) -> tuple:
  """The spec's mod jars, each its one file; one of the spec's own project older than its sources refused."""
  jars = spec.modJars()
  sources = _newestSource(spec.folder)
  for jar in jars:
    inside = os.path.commonpath([os.path.abspath(jar), spec.folder]) == spec.folder
    if inside and sources and os.path.getmtime(jar) < sources:
      raise SpecError('%s: "mods": %s is older than the newest file under %s: not built from these sources (build it,'
                      ' or give the spec a "build")' % (spec.path, jar, os.path.join(spec.folder, 'src')))
  return jars


def _copyConfig(spec: InstanceSpec, gameDir: str) -> None:
  """The spec's config files over the game's config/ (the rest of it left as it is)."""
  if not spec.config:
    return
  for where, _, names in os.walk(spec.config):
    target = os.path.join(gameDir, 'config', os.path.relpath(where, spec.config))
    os.makedirs(target, exist_ok=True)
    for name in names:
      shutil.copy2(os.path.join(where, name), os.path.join(target, name))


def _optionText(value) -> str:
  if isinstance(value, bool):
    return 'true' if value else 'false'
  return str(value)


def _writeOptions(spec: InstanceSpec, gameDir: str) -> None:
  """The spec's options set in the game's options.txt (key:value lines), the rest of it kept."""
  options = spec.options
  if not options:
    return
  path = os.path.join(gameDir, 'options.txt')
  lines = []
  if os.path.isfile(path):
    with open(path, encoding='utf-8') as file:
      lines = file.read().splitlines()
  seen = set()
  out = []
  for line in lines:
    key = line.split(':', 1)[0]
    if key in options:
      out.append('%s:%s' % (key, _optionText(options[key])))
      seen.add(key)
    else:
      out.append(line)
  out.extend('%s:%s' % (key, _optionText(value)) for key, value in options.items() if key not in seen)
  with open(path, 'w', encoding='utf-8') as file:
    file.write('\n'.join(out) + '\n')


def _terminate(process, gameDir: str) -> None:
  """The command's process group, and the game's JVM found by its folder (java only)."""
  try:
    os.killpg(process.pid, signal.SIGTERM)
  except ProcessLookupError:
    pass
  for pid in gameJvms(gameDir):
    try:
      os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
      pass


# ---------------------------------------------------------------- the two kinds


class RealGame(LaunchedGame):
  """A real client from a spec (client = "real"); 'cache' is the download cache, 'bundled' where the probes are."""

  def __init__(self, spec: InstanceSpec, results: str, name: str = 'game', cache: Optional[Cache] = None,
               bundled: str = BUNDLED, which: Optional[Callable] = None, folder: Optional[str] = None,
               username: Optional[str] = None, built: bool = False) -> None:
    if username is not None and not PLAYER_NAME.match(username):
      raise ValueError('%r is no player name 1.7.10 takes (letters, digits and _, 1 to 16 of them)' % (username,))
    LaunchedGame.__init__(self, spec.folder, results, name)
    self.spec = spec
    self.cache = cache or Cache()
    self.bundled = bundled
    self.which = which or shutil.which
    #  a folder and a player of its own, for a multiplayer run's further clients (SPEC.md 11.3, step 5)
    self.folder = folder
    self.username = username
    #  the spec's build done already, by the run's own client (a further client's): not run again
    self.built = built

  def gameFolder(self) -> str:
    return self.folder or self.spec.game

  def outputName(self) -> str:
    return 'client.log'

  def probeJar(self) -> str:
    probe = self.spec.probe
    if probe != 'bundled':
      if not os.path.isfile(probe):
        raise SpecError('%s: "probe": %s is no file' % (self.spec.path, probe))
      return probe
    found = sorted(glob.glob(os.path.join(self.bundled, '*.jar')))
    if not found:
      raise SpecError('%s: "probe" is "bundled", but this unittas carries no probe (a development install): name one, '
                      'probe = "path/to/the probe jar"' % self.spec.path)
    return found[-1]

  def library(self, library) -> str:
    """A library's jar: a file as it is, a maven: one from the first of the spec's repositories that has it."""
    if not isinstance(library, MavenLibrary):
      return library
    name = '%s-%s%s.jar' % (library.artifact, library.version, '-' + library.classifier if library.classifier else '')
    path = '%s/%s/%s/%s' % (library.group.replace('.', '/'), library.artifact, library.version, name)
    problems = []
    for repository in self.spec.repositories:
      base = repository if repository.endswith('/') else repository + '/'
      try:
        return self.cache.get('libraries/' + path, base + path, sha1Url=base + path + '.sha1',
                              what='%s:%s:%s' % (library.group, library.artifact, library.version))
      except CacheError as error:
        problems.append(str(error))
    raise SpecError('%s: "libraries": %s:%s:%s from none of the repositories: %s' % (
      self.spec.path, library.group, library.artifact, library.version, '; '.join(problems)))

  def modJars(self) -> list:
    """The jars its mods/ holds: the probe, the spec's mods (checked as built from their sources), its libraries."""
    jars = [self.probeJar()]
    for jar in list(_checkedJars(self.spec)) + [self.library(each) for each in self.spec.libraries]:
      if os.path.abspath(jar) not in [os.path.abspath(each) for each in jars]:
        jars.append(jar)
    return jars

  def serverMods(self) -> list:
    """A multiplayer run's server's mods: the clients', but those the spec's [server] exclude names."""
    return [jar for jar in self.modJars()
            if not any(fnmatch.fnmatch(os.path.basename(jar), pattern) for pattern in self.spec.serverExclude)]

  def prepare(self) -> None:
    if not self.built:
      _build(self.spec, os.path.join(self.results, 'build.log'))
    putMods(self.gameDir, self.modJars(), os.path.join(self.results, 'mods-before-this-run'))
    _copyConfig(self.spec, self.gameDir)
    _writeOptions(self.spec, self.gameDir)

  def command(self) -> list:
    words, why = prefix(self.spec.display, self.spec.width, self.spec.height, which=self.which)
    self.displayNote = why
    launch = [sys.executable, '-I', '-m', 'unittas.launcher', '--game', self.gameDir, '--cache', self.cache.root]
    if self.spec.java:
      launch += ['--java', self.spec.java]
    if self.username:
      launch += ['--username', self.username]
    return words + launch

  def environment(self) -> dict:
    return environment()

  def terminate(self) -> None:
    _terminate(self.process(), self.gameDir)


class GradleGame(LaunchedGame):
  """The mod's own Gradle run from a spec (client = "gradle"): its task in its project, the start file in its game."""

  def __init__(self, spec: InstanceSpec, results: str, name: str = 'game', which: Optional[Callable] = None) -> None:
    LaunchedGame.__init__(self, spec.folder, results, name)
    self.spec = spec
    self.which = which or shutil.which

  def gameFolder(self) -> str:
    return self.spec.game

  def workingDir(self) -> str:
    return self.spec.gradleProject

  def outputName(self) -> str:
    return 'gradle.log'

  def gradlew(self) -> str:
    return os.path.join(self.spec.gradleProject, 'gradlew')

  def daemonOptions(self) -> str:
    """
    The project's own JVM options for the daemon, and one more: a daemon a
    sandboxed session started can't open a game's window, and Gradle reuses
    any daemon with the same options (unittas.sh's guard, 2026-11-05).
    """
    jvmargs = ''
    path = os.path.join(self.spec.gradleProject, 'gradle.properties')
    if os.path.isfile(path):
      with open(path, encoding='utf-8') as file:
        for line in file:
          if line.startswith('org.gradle.jvmargs='):
            jvmargs = line.split('=', 1)[1].strip()
    return ('-Dorg.gradle.jvmargs=%s -Dunittas.daemon=desktop' % jvmargs).replace('= ', '=')

  def prepare(self) -> None:
    if not os.path.isfile(self.gradlew()):
      raise SpecError('%s: client = "gradle", but %s has no gradlew' % (self.spec.path, self.spec.gradleProject))
    _build(self.spec, os.path.join(self.results, 'build.log'))
    _copyConfig(self.spec, self.gameDir)
    _writeOptions(self.spec, self.gameDir)

  def command(self) -> list:
    words, why = prefix(self.spec.display, self.spec.width, self.spec.height, which=self.which)
    self.displayNote = why
    return words + [self.gradlew(), '--console=plain', self.daemonOptions(), self.spec.gradleTask]

  def environment(self) -> dict:
    return environment()

  def terminate(self) -> None:
    _terminate(self.process(), self.gameDir)

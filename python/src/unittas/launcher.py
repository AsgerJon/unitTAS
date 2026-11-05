"""
The 'launcher' module starts a real (not development) Minecraft 1.7.10
client with Forge 10.13.4.1614: unitTAS's own launcher, no other needed
(SPEC.md 9.3, step 3). It was bin/launch_client.py, which now calls it.

Each file comes from the first place that has it:

- the project's Gradle cache (Unimined's version JSON, client jar and
  assets; modules-2's libraries), used where it lies;
- the download cache (unittas.cache), when the caller gives one: Mojang's
  version manifest, 1.7.10's version JSON, its libraries, natives, client
  jar, asset index and objects, and Forge's universal jar and libraries
  from Forge's maven, each held to its sha1.

Forge's 1.7.10 JSON names its maven by plain HTTP on an old name; it is
fetched from https://maven.minecraftforge.net/ instead. Java is never
fetched. The class path follows the two version JSONs as a launcher does:
vanilla's rules for Linux, a library both name kept once (Forge's), natives
off it (extracted into the game's natives/), the client jar last. The game
runs offline as unitTAS, in its game folder.

The standard library only: bin/launch_client.py runs this from the system's
own Python.

- Sources: where files come from.
- command: the java command for a game folder, and what to extract first.
- extract: the natives into a folder.
- main: bin/launch_client.py's command line.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import glob
import hashlib
import json
import os
import shlex
import sys
import uuid
import zipfile
from typing import TYPE_CHECKING

from .cache import Cache, CacheError

if TYPE_CHECKING:  # pragma: no cover
  from typing import Optional

MINECRAFT = '1.7.10'
FORGE = '1.7.10-10.13.4.1614-1.7.10'
USERNAME = 'unitTAS'
OS_NAME = 'linux'
MANIFEST = 'https://piston-meta.mojang.com/mc/game/version_manifest_v2.json'
MOJANG_LIBRARIES = 'https://libraries.minecraft.net/'
FORGE_MAVEN = 'https://maven.minecraftforge.net/'
#  Forge's own JSONs name its maven so; it is reached through FORGE_MAVEN, by HTTPS
OLD_FORGE_MAVENS = ('http://files.minecraftforge.net/maven/', 'https://files.minecraftforge.net/maven/')
ASSETS = 'https://resources.download.minecraft.net/'
#  Forge 10.13.4.1614's JSON pins these two Scala jars at sha1s its maven no longer serves. Found by the live
#  download (2026-11-05): what the maven serves, its own .sha1 file, and the copy Gradle fetched months before (which
#  every game here runs on) all agree on these. They are pinned here exactly, beside the JSON's; nothing else is taken
#  on the server's word.
FORGE_SHA1_PINS = {
  'org.scala-lang.plugins:scala-continuations-library_2.11:1.0.2': '0e517c53a7e9acd6b1668c5a35eccbaa3bab9aac',
  'org.scala-lang.plugins:scala-continuations-plugin_2.11.1:1.0.2': 'f361a3283452c57fa30c1ee69448995de23c60f7',
}


class Missing(Exception):
  """Something the launcher needs is in neither source, or couldn't be fetched (its message says which)."""


class Sources:
  """The Gradle cache ('gradleHome', a GRADLE_USER_HOME; None for none) and the download cache ('cache'; None: no downloads)."""

  def __init__(self, gradleHome: Optional[str] = None, cache: Optional[Cache] = None) -> None:
    self.gradleHome = gradleHome if gradleHome and os.path.isdir(gradleHome) else None
    self.cache = cache


class Launch:
  """What a launch needs: the java command, the natives jars to extract (with what not to), the assets' root."""

  def __init__(self, java: list, natives: list, assets: str) -> None:
    self.java = java
    self.natives = natives
    self.assets = assets


# ---------------------------------------------------------------- the Gradle cache


def _unimined(home: str) -> str:
  return os.path.join(home, 'caches', 'unimined', 'net', 'minecraft', 'minecraft', MINECRAFT)


def _module(home: Optional[str], coordinates: str, classifier: str = '') -> Optional[str]:
  """The jar of 'group:artifact:version' in the Gradle cache's modules-2, or None."""
  if home is None:
    return None
  group, artifact, version = coordinates.split(':')[:3]
  name = '%s-%s%s.jar' % (artifact, version, '-' + classifier if classifier else '')
  found = sorted(glob.glob(os.path.join(home, 'caches', 'modules-2', 'files-2.1', group, artifact, version, '*', name)))
  return found[0] if found else None


def _mavenPath(coordinates: str, classifier: str = '') -> str:
  group, artifact, version = coordinates.split(':')[:3]
  return '%s/%s/%s/%s-%s%s.jar' % (group.replace('.', '/'), artifact, version, artifact, version,
                                   '-' + classifier if classifier else '')


def _named(coordinates: str, classifier: str = '') -> str:
  return coordinates + (':' + classifier if classifier else '')


# ---------------------------------------------------------------- each file, from the first source that has it


def _fetched(sources: Sources, relative: str, url: str, what: str, sha1s=(), sha1Url: Optional[str] = None) -> str:
  if sources.cache is None:
    raise Missing('%s is not in the Gradle cache%s' % (
      what, '' if sources.gradleHome else ' (there is none: build unitTAS once, ./gradlew build, to fill it)'))
  try:
    return sources.cache.get(relative, url, sha1s, sha1Url, what)
  except CacheError as error:
    raise Missing(str(error)) from None


def _vanillaJson(sources: Sources) -> dict:
  if sources.gradleHome is not None:
    path = os.path.join(_unimined(sources.gradleHome), 'version.json')
    if os.path.isfile(path):
      with open(path, encoding='utf-8') as file:
        return json.load(file)
  if sources.cache is None:
    raise Missing('no %s version JSON: build unitTAS once (./gradlew build) to fill the Gradle cache' % MINECRAFT)
  relative = 'versions/%s/%s.json' % (MINECRAFT, MINECRAFT)
  if not os.path.isfile(sources.cache.path(relative)):
    try:
      manifest = json.loads(sources.cache.fetch(MANIFEST).decode('utf-8'))
    except (OSError, ValueError) as error:
      raise Missing('Mojang\'s version manifest couldn\'t be fetched from %s: %s' % (MANIFEST, error)) from None
    entry = next((each for each in manifest.get('versions', []) if each.get('id') == MINECRAFT), None)
    if entry is None:
      raise Missing('Mojang\'s version manifest has no %s' % MINECRAFT)
    _fetched(sources, relative, entry['url'], 'the %s version JSON' % MINECRAFT, [entry['sha1']])
  with open(sources.cache.path(relative), encoding='utf-8') as file:
    return json.load(file)


def _universal(sources: Sources) -> str:
  found = _module(sources.gradleHome, 'net.minecraftforge:forge:' + FORGE, 'universal')
  if found:
    return found
  path = _mavenPath('net.minecraftforge:forge:' + FORGE, 'universal')
  return _fetched(sources, 'libraries/' + path, FORGE_MAVEN + path, _named('net.minecraftforge:forge:' + FORGE,
                                                                             'universal'),
                  sha1Url=FORGE_MAVEN + path + '.sha1')


def _forgeLibrary(sources: Sources, library: dict) -> str:
  name = library['name']
  found = _module(sources.gradleHome, name)
  if found:
    return found
  base = library.get('url') or MOJANG_LIBRARIES
  if base in OLD_FORGE_MAVENS:
    base = FORGE_MAVEN
  if not base.endswith('/'):
    base += '/'
  path = _mavenPath(name)
  checksums = list(library.get('checksums') or ())
  if checksums and name in FORGE_SHA1_PINS:
    checksums.append(FORGE_SHA1_PINS[name])
  return _fetched(sources, 'libraries/' + path, base + path, name, checksums,
                  None if checksums else base + path + '.sha1')


def _vanillaLibrary(sources: Sources, library: dict, classifier: str = '') -> str:
  name = library['name']
  found = _module(sources.gradleHome, name, classifier)
  if found:
    return found
  downloads = library.get('downloads', {})
  entry = downloads.get('classifiers', {}).get(classifier) if classifier else downloads.get('artifact')
  if not entry:
    raise Missing('%s has no download in the version JSON' % _named(name, classifier))
  return _fetched(sources, 'libraries/' + entry.get('path', _mavenPath(name, classifier)), entry['url'],
                  _named(name, classifier), [entry['sha1']])


def _client(sources: Sources, vanilla: dict) -> str:
  if sources.gradleHome is not None:
    path = os.path.join(_unimined(sources.gradleHome), 'minecraft-%s-client.jar' % MINECRAFT)
    if os.path.isfile(path):
      return path
  entry = vanilla.get('downloads', {}).get('client')
  if sources.cache is None or not entry:
    raise Missing('no %s client jar: build unitTAS once (./gradlew build) to fill the Gradle cache' % MINECRAFT)
  return _fetched(sources, 'versions/%s/%s.jar' % (MINECRAFT, MINECRAFT), entry['url'],
                  'the %s client jar' % MINECRAFT, [entry['sha1']])


def _assets(sources: Sources, vanilla: dict) -> str:
  """The assets' root: the Gradle cache's when it has the index and every object, else the download cache's."""
  name = vanilla['assets']
  if sources.gradleHome is not None:
    root = os.path.join(sources.gradleHome, 'caches', 'unimined', 'assets')
    index = os.path.join(root, 'indexes', name + '.json')
    if os.path.isfile(index) and _complete(root, index):
      return root
    if sources.cache is None:
      raise Missing('no asset index %s in %s: run ./gradlew runClient once to fetch the assets' % (name, root))
  if sources.cache is None:
    raise Missing('no assets: build unitTAS once (./gradlew runClient) to fill the Gradle cache')
  entry = vanilla.get('assetIndex')
  if not entry:
    raise Missing('the %s version JSON names no asset index' % MINECRAFT)
  index = _fetched(sources, 'assets/indexes/%s.json' % name, entry['url'], 'the asset index ' + name, [entry['sha1']])
  with open(index, encoding='utf-8') as file:
    objects = json.load(file).get('objects', {})
  gradleObjects = os.path.join(sources.gradleHome, 'caches', 'unimined', 'assets', 'objects') if sources.gradleHome else None
  for objectName, entry in sorted(objects.items()):
    digest = entry['hash']
    relative = 'assets/objects/%s/%s' % (digest[:2], digest)
    there = os.path.join(gradleObjects, digest[:2], digest) if gradleObjects else None
    if there and os.path.isfile(there):
      try:
        sources.cache.store(relative, there, digest)
        continue
      except CacheError:
        pass
    _fetched(sources, relative, '%s%s/%s' % (ASSETS, digest[:2], digest), 'the asset ' + objectName, [digest])
  return os.path.join(sources.cache.root, 'assets')


def _complete(root: str, index: str) -> bool:
  try:
    with open(index, encoding='utf-8') as file:
      objects = json.load(file).get('objects', {})
  except (OSError, ValueError):
    return False
  return all(os.path.isfile(os.path.join(root, 'objects', entry['hash'][:2], entry['hash'])) for entry in objects.values())


# ---------------------------------------------------------------- the command


def _allowed(library: dict) -> bool:
  """Vanilla's rules for this system: no rules allow; otherwise the last rule that applies decides."""
  rules = library.get('rules')
  if not rules:
    return True
  verdict = False
  for rule in rules:
    system = rule.get('os', {}).get('name')
    if system is None or system == OS_NAME:
      verdict = rule.get('action') == 'allow'
  return verdict


def _key(coordinates: str) -> str:
  group, artifact = coordinates.split(':')[:2]
  return '%s:%s' % (group, artifact)


def offlineId(name: str) -> str:
  """The UUID an offline player of that name has, as Java's UUID.nameUUIDFromBytes makes it, without dashes."""
  return uuid.UUID(bytes=hashlib.md5(('OfflinePlayer:' + name).encode('utf-8')).digest(), version=3).hex


def command(game: str, java: str, sources: Sources) -> Launch:
  """The launch of a real 1.7.10 Forge client in the game folder, on that Java; Missing naming what can't be had."""
  vanilla = _vanillaJson(sources)
  universal = _universal(sources)
  with zipfile.ZipFile(universal) as jar:
    forge = json.loads(jar.read('version.json').decode('utf-8'))
  path = []
  natives = []
  seen = set()
  for library in forge['libraries']:
    name = library['name']
    if library.get('clientreq') is False:
      continue
    seen.add(_key(name))
    path.append(universal if _key(name) == 'net.minecraftforge:forge' else _forgeLibrary(sources, library))
  for library in vanilla['libraries']:
    name = library['name']
    if not _allowed(library):
      continue
    classifier = library.get('natives', {}).get(OS_NAME)
    if classifier:
      classifier = classifier.replace('${arch}', '64')
      natives.append((_vanillaLibrary(sources, library, classifier), library.get('extract', {}).get('exclude', [])))
      continue
    if _key(name) in seen:
      continue
    seen.add(_key(name))
    path.append(_vanillaLibrary(sources, library))
  path.append(_client(sources, vanilla))
  assets = _assets(sources, vanilla)
  values = {
    'auth_player_name': USERNAME, 'version_name': forge['id'], 'game_directory': game, 'assets_root': assets,
    'assets_index_name': vanilla['assets'], 'auth_uuid': offlineId(USERNAME), 'auth_access_token': '0',
    'user_properties': '{}', 'user_type': 'legacy',
  }
  arguments = []
  for word in forge['minecraftArguments'].split():
    for name, value in values.items():
      word = word.replace('${%s}' % name, value)
    arguments.append(word)
  javaCommand = [java, '-Xms512M', '-Xmx2G', '-Djava.library.path=' + os.path.join(game, 'natives'),
                 '-cp', os.pathsep.join(path), forge['mainClass']]
  return Launch(javaCommand + arguments, natives, assets)


def extract(natives: list, into: str) -> None:
  """The natives jars' files into the folder, but what each says not to extract (META-INF/)."""
  os.makedirs(into, exist_ok=True)
  for jarPath, excluded in natives:
    with zipfile.ZipFile(jarPath) as jar:
      for entry in jar.namelist():
        if entry.endswith('/') or any(entry.startswith(prefix) for prefix in excluded):
          continue
        with open(os.path.join(into, os.path.basename(entry)), 'wb') as out:
          out.write(jar.read(entry))


#  Where Java 8 usually is on Linux: Arch, Debian and Ubuntu, Fedora.
JAVA8_CANDIDATES = ('/usr/lib/jvm/java-8-openjdk/bin/java', '/usr/lib/jvm/java-8-openjdk-amd64/bin/java',
                    '/usr/lib/jvm/jre-1.8.0/bin/java', '/usr/lib/jvm/java-1.8.0/bin/java')


def findJava(named: Optional[str] = None, candidates: tuple = JAVA8_CANDIDATES) -> str:
  """
  The java to run 1.7.10 on: the one named (a JDK's folder, or its java),
  else UNITTAS_JAVA8, else the first of the usual places that has one.
  Never downloaded: Missing names every place looked at.
  """
  if named:
    binary = os.path.join(named, 'bin', 'java') if os.path.isdir(named) else named
    if os.path.isfile(binary) and os.access(binary, os.X_OK):
      return binary
    raise Missing('no java at %s (the spec\'s "java": a JDK\'s folder, or its bin/java)' % named)
  looked = ([os.environ['UNITTAS_JAVA8']] if os.environ.get('UNITTAS_JAVA8') else []) + list(candidates)
  for binary in looked:
    if os.path.isfile(binary) and os.access(binary, os.X_OK):
      return binary
  raise Missing('no Java 8 found (looked at %s). Java is never downloaded: install a Java 8 JDK, or name it as the '
                'spec\'s "java"' % ', '.join(looked))


def java8() -> str:
  """bin/launch_client.py's java: UNITTAS_JAVA8, else Arch's Java 8, as it always was (the scripts' own check)."""
  return os.environ.get('UNITTAS_JAVA8') or JAVA8_CANDIDATES[0]


def main(*args: str, gradleHome: Optional[str] = None) -> int:
  """
  bin/launch_client.py's command line:
  --game DIR [--dry-run] [--cache DIR] [--no-gradle-cache].

  The Gradle cache is UNITTAS_GRADLE_HOME's, else the one given, unless
  --no-gradle-cache. Nothing is downloaded but with --cache, which names
  the download cache to fill (the scripts' launches use the project's
  cache only). Exits 2 when something it needs is missing, naming it. The
  java process replaces this one, so its command line holds the game's
  folder.
  """
  usage = ('Usage: python3 bin/launch_client.py --game DIR [--dry-run] [--cache DIR] [--no-gradle-cache] [--java PATH]'
           '  (or: python -m unittas.launcher ...)')
  args = list(args)
  dry = '--dry-run' in args
  if dry:
    args.remove('--dry-run')
  noGradle = '--no-gradle-cache' in args
  if noGradle:
    args.remove('--no-gradle-cache')
  taken = {}
  for option in ('--cache', '--java'):
    if option in args:
      at = args.index(option)
      if at + 1 >= len(args):
        print(usage)
        return 2
      taken[option] = args[at + 1]
      del args[at:at + 2]
  cacheRoot = taken.get('--cache')
  if len(args) != 2 or args[0] != '--game':
    print(usage)
    return 2
  game = os.path.abspath(args[1])
  sources = Sources(gradleHome=None if noGradle else os.environ.get('UNITTAS_GRADLE_HOME') or gradleHome,
                    cache=Cache(cacheRoot) if cacheRoot else None)
  try:
    launch = command(game, findJava(taken['--java']) if '--java' in taken else java8(), sources)
  except (Missing, OSError, KeyError, ValueError) as problem:
    print('unitTAS launcher: %s' % problem)
    return 2
  if dry:
    print(' '.join(shlex.quote(word) for word in launch.java))
    return 0
  os.makedirs(game, exist_ok=True)
  extract(launch.natives, os.path.join(game, 'natives'))
  sys.stdout.flush()
  os.chdir(game)
  os.execv(launch.java[0], launch.java)
  return 0


if __name__ == '__main__':
  sys.exit(main(*sys.argv[1:]))

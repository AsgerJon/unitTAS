"""
The 'launcher' module starts a real (not development) Minecraft 1.7.10
client with Forge 10.13.4.1614: unitTAS's own launcher, no other needed
(SPEC.md 9.3, step 3). It was bin/launch_client.py, which now calls it.
It also makes the dedicated server's command (SPEC.md 11.3, step 1):
Forge's universal jar, the libraries Forge's JSON marks a server's, and
Mojang's server jar, launched as FML launches a server, with no window.

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
- serverCommand: the java command for a dedicated server's folder.
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
import re
import shlex
import sys
import uuid
import zipfile
from typing import TYPE_CHECKING

from . import versions
from .cache import Cache, CacheError

if TYPE_CHECKING:  # pragma: no cover
  from typing import Optional

MINECRAFT = '1.7.10'
FORGE = '1.7.10-10.13.4.1614-1.7.10'
#  How FML starts a dedicated server: the Main-Class of Forge's universal jar's manifest.
SERVER_MAIN = 'cpw.mods.fml.relauncher.ServerLaunchWrapper'
#  A player name as 1.7.10 takes one: letters, digits and the underscore, 1 to 16 of them.
PLAYER_NAME = re.compile(r'^[A-Za-z0-9_]{1,16}$')
#  A JVM's memory as -Xmx takes it: '2G', '1536M'.
MEMORY = re.compile(r'^[1-9][0-9]*[MG]$')
USERNAME = 'unitTAS'
OS_NAME = 'linux'
MANIFEST = 'https://piston-meta.mojang.com/mc/game/version_manifest_v2.json'
MOJANG_LIBRARIES = 'https://libraries.minecraft.net/'
FORGE_MAVEN = 'https://maven.minecraftforge.net/'
#  Forge's own JSONs name its maven so; it is reached through FORGE_MAVEN, by HTTPS
OLD_FORGE_MAVENS = ('http://files.minecraftforge.net/maven/', 'https://files.minecraftforge.net/maven/')
ASSETS = 'https://resources.download.minecraft.net/'
#  Fabric's meta server (fabric-meta's v2 API): the launcher profile for a game version and a loader version
FABRIC_META = 'https://meta.fabricmc.net/v2/versions/loader/%s/%s/profile/json'
#  NeoForge's maven: each NeoForge version's installer, which makes NeoForge's game (SPEC.md 19.7 step 7)
NEOFORGE_MAVEN = 'https://maven.neoforged.net/releases/net/neoforged/neoforge/'
#  The loaders versionCommand puts on a version (1.7.10 Forge is command's, below)
LOADERS = ('fabric', 'neoforge')
#  What a version's default-user-jvm says of memory, which a run gives itself instead
_MEMORY_FLAG = re.compile(r'^-Xm[sx]')
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
  """
  What a launch needs: the java command, the natives jars to extract (with
  what not to), the assets' root, and the major version of the Java it
  needs.
  """

  def __init__(self, java: list, natives: list, assets: str, javaMajor: int = 8) -> None:
    self.java = java
    self.natives = natives
    self.assets = assets
    self.javaMajor = javaMajor


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


def _server(sources: Sources, vanilla: dict) -> str:
  """Mojang's server jar: the Gradle cache's (Unimined's, as its runServer keeps it), else the download cache's."""
  if sources.gradleHome is not None:
    path = os.path.join(_unimined(sources.gradleHome), 'minecraft-%s-server.jar' % MINECRAFT)
    if os.path.isfile(path):
      return path
  entry = vanilla.get('downloads', {}).get('server')
  if sources.cache is None or not entry:
    raise Missing('no %s server jar: build unitTAS once (./gradlew build) to fill the Gradle cache' % MINECRAFT)
  return _fetched(sources, 'versions/%s/%s-server.jar' % (MINECRAFT, MINECRAFT), entry['url'],
                  'the %s server jar' % MINECRAFT, [entry['sha1']])


def _assets(sources: Sources, vanilla: dict) -> str:
  """The assets' root: the Gradle cache's when it has the index and every object, else the download cache's."""
  return _assetsOf(sources, vanilla['assets'], vanilla.get('assetIndex'), MINECRAFT)


def _assetsOf(sources: Sources, name: str, entry: Optional[dict], minecraft: str) -> str:
  """The assets of the index 'name' ('entry' its version JSON's assetIndex), from the Gradle cache or downloaded."""
  if sources.gradleHome is not None:
    root = os.path.join(sources.gradleHome, 'caches', 'unimined', 'assets')
    index = os.path.join(root, 'indexes', name + '.json')
    if os.path.isfile(index) and _complete(root, index):
      return root
    if sources.cache is None:
      raise Missing('no asset index %s in %s: run ./gradlew runClient once to fetch the assets' % (name, root))
  if sources.cache is None:
    raise Missing('no assets: build unitTAS once (./gradlew runClient) to fill the Gradle cache')
  if not entry:
    raise Missing('the %s version JSON names no asset index' % minecraft)
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


def command(game: str, java: str, sources: Sources, username: str = USERNAME) -> Launch:
  """
  The launch of a real 1.7.10 Forge client in the game folder, on that
  Java, its player 'username' (offline, so its id follows from the name);
  Missing naming what can't be had, ValueError for a name 1.7.10 wouldn't
  take.
  """
  if not isinstance(username, str) or not PLAYER_NAME.match(username):
    raise ValueError('%r is no player name 1.7.10 takes (letters, digits and _, 1 to 16 of them)' % (username,))
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
    'auth_player_name': username, 'version_name': forge['id'], 'game_directory': game, 'assets_root': assets,
    'assets_index_name': vanilla['assets'], 'auth_uuid': offlineId(username), 'auth_access_token': '0',
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


def serverCommand(folder: str, java: str, sources: Sources, memory: str = '2G') -> Launch:
  """
  The launch of a 1.7.10 Forge dedicated server in its folder, on that
  Java, with that much memory: as Forge's universal jar's manifest has it,
  the universal jar first, then the libraries Forge's JSON marks a
  server's (serverreq) in its order, then Mojang's server jar, which
  carries vanilla's own. No window, so no natives and no assets. Missing
  naming what can't be had; ValueError for memory -Xmx wouldn't take.
  """
  if not MEMORY.match(memory or ''):
    raise ValueError("a server's memory is as -Xmx takes it, '2G' or '1536M', not %r" % (memory,))
  vanilla = _vanillaJson(sources)
  universal = _universal(sources)
  with zipfile.ZipFile(universal) as jar:
    forge = json.loads(jar.read('version.json').decode('utf-8'))
  path = [universal]
  for library in forge['libraries']:
    if _key(library['name']) == 'net.minecraftforge:forge' or library.get('serverreq') is not True:
      continue
    path.append(_forgeLibrary(sources, library))
  path.append(_server(sources, vanilla))
  javaCommand = [java, '-Xmx' + memory, '-cp', os.pathsep.join(path), SERVER_MAIN, 'nogui']
  return Launch(javaCommand, [], '')


# ---------------------------------------------------------------- any version, with a loader on top (SPEC.md 12)


def _versionJson(sources: Sources, minecraft: str) -> dict:
  """Mojang's version JSON for 'minecraft': the download cache's, else by the version manifest, held to its sha1."""
  if sources.cache is None:
    raise Missing('no %s version JSON: there is no download cache to fetch it into' % minecraft)
  relative = 'versions/%s/%s.json' % (minecraft, minecraft)
  if not os.path.isfile(sources.cache.path(relative)):
    try:
      manifest = json.loads(sources.cache.fetch(MANIFEST).decode('utf-8'))
    except (OSError, ValueError) as error:
      raise Missing('Mojang\'s version manifest couldn\'t be fetched from %s: %s' % (MANIFEST, error)) from None
    entry = next((each for each in manifest.get('versions', []) if each.get('id') == minecraft), None)
    if entry is None:
      raise Missing('Mojang\'s version manifest has no %s' % minecraft)
    _fetched(sources, relative, entry['url'], 'the %s version JSON' % minecraft, [entry['sha1']])
  with open(sources.cache.path(relative), encoding='utf-8') as file:
    return json.load(file)


def _kept(sources: Sources, relative: str, url: str, what: str) -> str:
  """
  A file that is itself where trust starts, as Mojang's version manifest
  is: a loader's profile from its meta server, which has no checksum of
  its own. Fetched over HTTPS once, read as JSON, and kept whole (written
  apart, then renamed into place); what it names is held to its sha1s.
  """
  if sources.cache is None:
    raise Missing('no %s: there is no download cache to fetch it into' % what)
  target = sources.cache.path(relative)
  if os.path.isfile(target):
    return target
  try:
    data = sources.cache.fetch(url)
    json.loads(data.decode('utf-8'))
  except (OSError, ValueError) as error:
    raise Missing('%s couldn\'t be had from %s: %s' % (what, url, error)) from None
  os.makedirs(os.path.dirname(target), exist_ok=True)
  part = '%s.part-%d' % (target, os.getpid())
  try:
    with open(part, 'wb') as file:
      file.write(data)
    os.replace(part, target)
  finally:
    if os.path.exists(part):
      os.remove(part)
  return target


def _profile(sources: Sources, minecraft: str, loader: str, loaderVersion: str) -> dict:
  """The loader's launcher profile for that game version: Fabric's from its meta server."""
  from urllib.parse import quote
  url = FABRIC_META % (quote(minecraft, safe=''), quote(loaderVersion, safe=''))
  path = _kept(sources, 'versions/fabric-loader-%s-%s/profile.json' % (loaderVersion, minecraft), url,
               "Fabric Loader %s's profile for %s" % (loaderVersion, minecraft))
  with open(path, encoding='utf-8') as file:
    return json.load(file)


def _mavenFile(coordinates: str) -> str:
  """A maven artifact's path in a library folder, from '[group:artifact:version(:classifier)(@extension)]'."""
  name, _, extension = coordinates.strip('[]').partition('@')
  parts = name.split(':')
  if len(parts) not in (3, 4):
    raise ValueError('%r is no maven artifact' % coordinates)
  group, artifact, version = parts[:3]
  classifier = '-' + parts[3] if len(parts) == 4 else ''
  return '%s/%s/%s/%s-%s%s.%s' % (group.replace('.', '/'), artifact, version, artifact, version, classifier,
                                  extension or 'jar')


def _neoForgeProfile(sources: Sources, minecraft: str, loaderVersion: str, java: str) -> dict:
  """
  NeoForge's version JSON for that version (SPEC.md 19.7 step 7): what NeoForge's own installer writes, run headless
  once into the download cache (--install-client), which is laid out as a launcher's folder (versions/, libraries/).
  Its processors make the game NeoForge runs (for 1.21.1 the client jar split, renamed by Mojang's names, patched; for
  26.x patched): they are NeoForge's own, run by its installer, on the version's Java. The installer is fetched from
  NeoForge's maven and held to its .sha1; the folder's launcher_profiles.json, which the installer asks for, written
  first. Installed when its version JSON and the patched client its install profile names (PATCHED) are both there.
  Missing, naming the installer's output, when it fails, or when the profile is for another version.
  """
  import subprocess
  if sources.cache is None:
    raise Missing('no NeoForge %s: there is no download cache to install it into' % loaderVersion)
  name = 'neoforge-%s' % loaderVersion
  url = NEOFORGE_MAVEN + '%s/%s-installer.jar' % (loaderVersion, name)
  installer = _fetched(sources, 'libraries/net/neoforged/neoforge/%s/%s-installer.jar' % (loaderVersion, name), url,
                       "NeoForge %s's installer" % loaderVersion, sha1Url=url + '.sha1')
  try:
    with zipfile.ZipFile(installer) as jar:
      patchedName = json.loads(jar.read('install_profile.json').decode('utf-8'))['data']['PATCHED']['client']
    patched = sources.cache.path('libraries/' + _mavenFile(patchedName))
  except (zipfile.BadZipFile, KeyError, TypeError, ValueError) as error:
    raise Missing("NeoForge %s's installer (%s) names no patched client in its install profile: %s" % (
      loaderVersion, installer, error)) from None
  profilePath = sources.cache.path('versions/%s/%s.json' % (name, name))
  if not (os.path.isfile(profilePath) and os.path.isfile(patched)):
    root = sources.cache.path('')
    profiles = os.path.join(root, 'launcher_profiles.json')
    if not os.path.isfile(profiles):
      with open(profiles, 'w', encoding='utf-8') as file:
        file.write('{"profiles": {}}\n')
    log = sources.cache.path('versions/%s/install.log' % name)
    os.makedirs(os.path.dirname(log), exist_ok=True)
    # its output kept, and each line said as it comes (the launch's sign of life while it installs)
    with open(log, 'w', encoding='utf-8') as output:
      installing = subprocess.Popen([java, '-jar', installer, '--install-client', root], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=os.path.dirname(installer),
                                    text=True, errors='replace')
      for line in installing.stdout:
        output.write(line)
        if sources.cache.said is not None:
          sources.cache.said('NeoForge %s installer: %s' % (loaderVersion, line.rstrip('\n')))
      returncode = installing.wait()
    if returncode != 0 or not (os.path.isfile(profilePath) and os.path.isfile(patched)):
      raise Missing("NeoForge %s's installer didn't install it (exit %d): its output is in %s" % (
        loaderVersion, returncode, log))
  with open(profilePath, encoding='utf-8') as file:
    profile = json.load(file)
  if profile.get('inheritsFrom') != minecraft:
    raise Missing('NeoForge %s is for %s, not %s' % (loaderVersion, profile.get('inheritsFrom'), minecraft))
  return profile


def _jar(sources: Sources, library: versions.Library, gradle: bool = True) -> str:
  """
  One library's jar: the Gradle cache's where it has it ('gradle' False:
  never), else downloaded, held to the sha1 its JSON gives, or else to its
  maven's .sha1. Forge's old maven by plain HTTP is reached by HTTPS.
  """
  parts = library.name.split(':')
  found = _module(sources.gradleHome, ':'.join(parts[:3]), parts[3] if len(parts) > 3 else '') if gradle else None
  if found:
    return found
  url = library.url
  for old in OLD_FORGE_MAVENS:
    if url.startswith(old):
      url = FORGE_MAVEN + url[len(old):]
  return _fetched(sources, 'libraries/' + library.path, url, library.name, library.sha1s,
                  None if library.sha1s else url + '.sha1')


def versionCommand(game: str, java: Optional[str], sources: Sources, minecraft: str, loader: Optional[str],
                   loaderVersion: Optional[str], username: str = USERNAME, memory: str = '4G', width: int = 854,
                   height: int = 480, javaCandidates: Optional[dict] = None, agents: tuple = ()) -> Launch:
  """
  The launch of a real client of any version, as Mojang ships it (loader
  None) or with a loader on top (SPEC.md 12.3, step 2; LOADERS names
  them: Fabric's profile from its meta server, NeoForge's from its own
  installer, run once into the download cache, SPEC.md 19.7 step 7), in
  the game folder, on that Java: the version JSON and the
  loader's profile resolved for this system (unittas.versions), every
  file from the Gradle cache or the download cache and held to its sha1.
  Its player 'username' (offline), its memory the run's ('-Xmx'), the
  version's own collector flags kept, its window 'width' by 'height'.
  Each of 'agents' (a jar) a Java agent, given the game folder
  (-javaagent:JAR=GAME): the loader-free probe (SPEC.md 19.7 step 5),
  and for a version under other names than Mojang's its table of names
  (_names: -Dunittas.names).
  'java' None: the Java the version's JSON asks for (findJavaFor).
  Missing naming what can't be had; ValueError for a loader it doesn't
  put on, a name, or a memory it can't take.
  """
  if loader is not None and loader not in LOADERS:
    raise ValueError('unitTAS puts %s on a version, not %r (1.7.10 Forge is command\'s)' % (
      ', '.join(LOADERS), loader))
  if not isinstance(username, str) or not PLAYER_NAME.match(username):
    raise ValueError('%r is no player name the game takes (letters, digits and _, 1 to 16 of them)' % (username,))
  if not MEMORY.match(memory or ''):
    raise ValueError("memory is as -Xmx takes it, '4G' or '3072M', not %r" % (memory,))
  vanilla = _versionJson(sources, minecraft)
  if loader == 'neoforge':
    installing = java or findJavaFor(versions.resolve(vanilla).javaMajor, javaCandidates)
    profile = _neoForgeProfile(sources, minecraft, loaderVersion, installing)
  else:
    profile = None if loader is None else _profile(sources, minecraft, loader, loaderVersion)
  version = versions.resolve(vanilla, profile, features={'has_custom_resolution': True})
  if java is None:
    java = findJavaFor(version.javaMajor, javaCandidates)
  # a profile that names its libraries by their place in the library folder (NeoForge's module path) gets every one
  # from there: its BootstrapLauncher refuses a module on the class path from another file (SPEC.md 19.7 step 7)
  gradle = not any('${library_directory}' in argument for argument in version.jvm)
  path = [_jar(sources, library, gradle) for library in version.libraries]
  natives = [(_jar(sources, library, gradle), list(exclude)) for library, exclude in version.natives]
  client = version.client
  if not client:
    raise Missing('the %s version JSON names no client jar' % minecraft)
  jar = _fetched(sources, 'versions/%s/%s.jar' % (minecraft, minecraft), client['url'],
                 'the %s client jar' % minecraft, [client['sha1']])
  if loader == 'neoforge':
    # as a launcher lays a profile out: the client jar by the version's own name, which NeoForge's BootstrapLauncher
    # leaves alone (its -DignoreList names it); the game it runs is the installer's patched one
    jar = sources.cache.store('versions/%s/%s.jar' % (version.id, version.id), jar)
  path.append(jar)
  assets = _assetsOf(sources, version.assets, version.assetIndex, minecraft)
  values = {
    'auth_player_name': username, 'version_name': version.id, 'game_directory': game, 'assets_root': assets,
    'assets_index_name': version.assets, 'auth_uuid': offlineId(username), 'auth_access_token': '0',
    'clientid': '', 'auth_xuid': '0', 'user_type': 'legacy', 'user_properties': '{}',
    'version_type': vanilla.get('type', 'release'), 'natives_directory': os.path.join(game, 'natives'),
    'launcher_name': 'unitTAS', 'launcher_version': 'unittas', 'classpath': os.pathsep.join(path),
    'classpath_separator': os.pathsep, 'library_directory': sources.cache.path('libraries') if sources.cache else '',
    'resolution_width': str(width), 'resolution_height': str(height),
  }
  jvm = ['-Xms512M', '-Xmx' + memory] + [flag for flag in version.defaultJvm if not _MEMORY_FLAG.match(flag)]
  if version.logging.get('file'):
    config = version.logging['file']
    configPath = _fetched(sources, 'assets/log_configs/' + config['id'], config['url'],
                          'the logging config ' + config['id'], [config['sha1']])
    jvm += versions.fill([version.logging['argument']], {'path': configPath})
  jvm += versions.fill(version.jvm, values)
  if agents:
    jvm += _names(sources, vanilla, minecraft, loader, version, path[-1])
  jvm += ['-javaagent:%s=%s' % (agent, game) for agent in agents]
  return Launch([java] + jvm + [version.mainClass] + versions.fill(version.game, values), natives, assets,
                version.javaMajor)


def _names(sources: Sources, vanilla: dict, minecraft: str, loader: Optional[str], version: versions.Version,
           client: str) -> list:
  """
  The agent's table of names, for a version the game runs under names
  other than Mojang's (before 26.1: SPEC.md 19.7 steps 6b and 6d):
  written once into the download cache, and named to the agent by
  -Dunittas.names. In vanilla such a version runs obfuscated; beside
  Fabric under intermediary's names, from the intermediary jar its
  profile names (Missing if it names none); beside NeoForge under
  Mojang's own, its installer having renamed the game so (step 7). None
  for a version under Mojang's own names (no client_mappings in its JSON).
  """
  if not vanilla.get('downloads', {}).get('client_mappings'):
    return []
  if loader == 'neoforge':
    # NeoForge's installer renames the game by Mojang's names (SPEC.md 19.7 step 7): the probe's own
    return []
  if loader is None:
    return ['-Dunittas.names=' + namesTable(sources, minecraft)]
  intermediary = next((library for library in version.libraries
                       if library.name.startswith('net.fabricmc:intermediary:')), None)
  if loader != 'fabric' or intermediary is None:
    raise Missing('%s beside %s runs under names its profile doesn\'t give: Fabric\'s names its intermediary jar '
                  '(net.fabricmc:intermediary), and no other loader is known to the agent yet' % (minecraft, loader))
  return ['-Dunittas.names=' + namesTable(sources, minecraft, _jar(sources, intermediary), client)]


def namesTable(sources: Sources, minecraft: str, intermediary: Optional[str] = None,
               client: Optional[str] = None) -> str:
  """
  The version's table of names (SPEC.md 19.7 steps 6b and 6d), Mojang's
  to the ones the game runs under: the obfuscated ones in vanilla, or
  with an intermediary jar on to intermediary's (beside Fabric), along
  the client jar's classes for the overrides. Written once into the
  download cache from the version's obfuscation log, which is fetched
  there once and held to its sha1. Missing for a version with no log, or
  when it can't be had.
  """
  from .mojangnames import TABLE_FORMAT, MojangNames
  if sources.cache is None:
    raise Missing('no %s table of names: there is no download cache to write it into' % minecraft)
  kind = 'obfuscated' if intermediary is None else 'intermediary'
  table = sources.cache.path('names/%s-%s-%s.txt' % (minecraft, kind, TABLE_FORMAT))
  if not os.path.isfile(table):
    names = MojangNames.load(sources, minecraft)
    if intermediary is not None:
      from .classheaders import supertypes
      from .intermediary import Intermediary
      names = names.through(Intermediary.fromJar(intermediary), supertypes(client))
    names.write(table, minecraft)
  return table


def classPath(sources: Sources, minecraft: str) -> list:
  """
  What code built against the game compiles with (the loader-free probe,
  SPEC.md 19.7 step 5): the version's own libraries for this system and
  its client jar last, from the Gradle cache or the download cache, each
  held to its sha1. Missing naming what can't be had.
  """
  vanilla = _versionJson(sources, minecraft)
  version = versions.resolve(vanilla, None)
  path = [_jar(sources, library) for library in version.libraries]
  client = version.client
  if not client:
    raise Missing('the %s version JSON names no client jar' % minecraft)
  path.append(_fetched(sources, 'versions/%s/%s.jar' % (minecraft, minecraft), client['url'],
                       'the %s client jar' % minecraft, [client['sha1']]))
  return path


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


#  Where a Java of each major version usually is on Linux (Arch, Debian and Ubuntu, Fedora), for findJavaFor
JAVA_CANDIDATES = {
  8: JAVA8_CANDIDATES,
  17: ('/usr/lib/jvm/java-17-openjdk/bin/java', '/usr/lib/jvm/java-17-openjdk-amd64/bin/java',
       '/usr/lib/jvm/jre-17/bin/java'),
  21: ('/usr/lib/jvm/java-21-openjdk/bin/java', '/usr/lib/jvm/java-21-openjdk-amd64/bin/java',
       '/usr/lib/jvm/jre-21/bin/java'),
  25: ('/usr/lib/jvm/java-25-openjdk/bin/java', '/usr/lib/jvm/java-25-openjdk-amd64/bin/java',
       '/usr/lib/jvm/jre-25/bin/java'),
}


def findJavaFor(major: int, candidates: Optional[dict] = None) -> str:
  """
  A java of that major version, as a version's JSON asks for one
  (javaVersion): UNITTAS_JAVA<major> (UNITTAS_JAVA8, UNITTAS_JAVA25), else
  the first of the usual places that has one. Never downloaded: Missing
  names every place looked at.
  """
  variable = 'UNITTAS_JAVA%d' % major
  looked = ([os.environ[variable]] if os.environ.get(variable) else []) + list(
    (candidates if candidates is not None else JAVA_CANDIDATES).get(major, ()))
  for binary in looked:
    if os.path.isfile(binary) and os.access(binary, os.X_OK):
      return binary
  raise Missing('no Java %d found (looked at %s). Java is never downloaded: install a Java %d JDK, or name it with '
                '%s or the spec\'s "java"' % (major, ', '.join(looked) or 'nowhere', major, variable))


def java8() -> str:
  """bin/launch_client.py's java: UNITTAS_JAVA8, else Arch's Java 8, as it always was (the scripts' own check)."""
  return os.environ.get('UNITTAS_JAVA8') or JAVA8_CANDIDATES[0]


def _said(line: str) -> None:
  """What the launcher does as it goes (each fetch, the installer's lines): the launch's sign of life, said at once."""
  print('unitTAS launcher: ' + line, flush=True)


def main(*args: str, gradleHome: Optional[str] = None) -> int:
  """
  bin/launch_client.py's command line:
  --game DIR [--dry-run] [--cache DIR] [--no-gradle-cache] [--java PATH]
  [--username NAME] [--minecraft VERSION [--loader NAME --loader-version
  VERSION] [--agent JAR] [--memory 4G] [--width N] [--height N]].

  Without --minecraft it is 1.7.10 Forge (command); with it, that version
  as Mojang ships it, or with the loader on top (versionCommand), with
  the Java agent if one is named, its Java the one its JSON asks for
  unless --java names one.

  The Gradle cache is UNITTAS_GRADLE_HOME's, else the one given, unless
  --no-gradle-cache. Nothing is downloaded but with --cache, which names
  the download cache to fill (the scripts' launches use the project's
  cache only). Exits 2 when something it needs is missing, naming it. The
  java process replaces this one, so its command line holds the game's
  folder.
  """
  usage = ('Usage: python3 bin/launch_client.py --game DIR [--dry-run] [--cache DIR] [--no-gradle-cache] [--java PATH]'
           ' [--username NAME] [--minecraft VERSION [--loader NAME --loader-version VERSION] [--agent JAR]'
           ' [--memory 4G] [--width N] [--height N]]  (or: python -m unittas.launcher ...)')
  args = list(args)
  dry = '--dry-run' in args
  if dry:
    args.remove('--dry-run')
  noGradle = '--no-gradle-cache' in args
  if noGradle:
    args.remove('--no-gradle-cache')
  taken = {}
  for option in ('--cache', '--java', '--username', '--minecraft', '--loader', '--loader-version', '--agent',
                 '--memory', '--width', '--height'):
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
                    cache=Cache(cacheRoot, said=_said) if cacheRoot else None)
  try:
    if '--minecraft' in taken:
      if ('--loader' in taken) != ('--loader-version' in taken):
        print(usage)
        return 2
      agents = (os.path.abspath(taken['--agent']),) if '--agent' in taken else ()
      launch = versionCommand(game, findJava(taken['--java']) if '--java' in taken else None, sources,
                              taken['--minecraft'], taken.get('--loader'), taken.get('--loader-version'),
                              taken.get('--username', USERNAME), taken.get('--memory', '4G'),
                              int(taken.get('--width', 854)), int(taken.get('--height', 480)), agents=agents)
    else:
      launch = command(game, findJava(taken['--java']) if '--java' in taken else java8(), sources,
                       taken.get('--username', USERNAME))
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

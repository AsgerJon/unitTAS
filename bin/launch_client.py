"""
unitTAS's own launcher: a real (not development) Minecraft 1.7.10 Forge 10.13.4.1614 client, started from what the
project's Gradle cache already holds, so nothing is downloaded and no other launcher is needed.

  python3 bin/launch_client.py --game DIR [--dry-run]

From the cache (.gradle-home, or UNITTAS_GRADLE_HOME): Unimined's official client jar and vanilla's version.json,
Forge's universal jar and the version.json inside it, every library they name from modules-2, the LWJGL and JInput
natives, and Unimined's assets. The class path follows the two version.json files as a launcher does: vanilla's
rules for Linux, a library both name kept once (Forge's: guava 17, commons-lang3 3.3.2), natives off it (extracted
into DIR/natives instead), the client jar last. The game runs on Java 8 (UNITTAS_JAVA8, else
/usr/lib/jvm/java-8-openjdk), offline as unitTAS, in DIR (its mods/, config/, saves/, unittas/request.properties).
The java process replaces this one, so its command line holds DIR. --dry-run only prints the command.

Exits 2 when something it needs is missing, naming it.
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MINECRAFT = '1.7.10'
FORGE = '1.7.10-10.13.4.1614-1.7.10'
USERNAME = 'unitTAS'
OS_NAME = 'linux'


class Missing(Exception):
  """Something the launcher needs isn't in the cache."""


def cacheRoot() -> str:
  return os.environ.get('UNITTAS_GRADLE_HOME') or os.path.join(ROOT, '.gradle-home')


def java8() -> str:
  return os.environ.get('UNITTAS_JAVA8') or '/usr/lib/jvm/java-8-openjdk/bin/java'


def unimined(cache: str) -> str:
  return os.path.join(cache, 'caches', 'unimined', 'net', 'minecraft', 'minecraft', MINECRAFT)


def module(cache: str, coordinates: str, classifier: str = '') -> str:
  """The jar of 'group:artifact:version' in Gradle's modules-2, by its classifier."""
  group, artifact, version = coordinates.split(':')[:3]
  name = '%s-%s%s.jar' % (artifact, version, '-' + classifier if classifier else '')
  found = sorted(glob.glob(os.path.join(cache, 'caches', 'modules-2', 'files-2.1', group, artifact, version, '*', name)))
  if not found:
    raise Missing('%s%s (%s) is not in the Gradle cache' % (coordinates, ':' + classifier if classifier else '', name))
  return found[0]


def allowed(library: dict) -> bool:
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


def key(coordinates: str) -> str:
  group, artifact = coordinates.split(':')[:2]
  return '%s:%s' % (group, artifact)


def versions(cache: str) -> tuple:
  """Vanilla's version.json and Forge's (from inside its universal jar), and the universal jar."""
  vanillaPath = os.path.join(unimined(cache), 'version.json')
  if not os.path.isfile(vanillaPath):
    raise Missing('no %s: build unitTAS once (./gradlew build) to fill the cache' % vanillaPath)
  with open(vanillaPath, encoding='utf-8') as f:
    vanilla = json.load(f)
  universal = module(cache, 'net.minecraftforge:forge:' + FORGE, 'universal')
  with zipfile.ZipFile(universal) as jar:
    forge = json.loads(jar.read('version.json').decode('utf-8'))
  return vanilla, forge, universal


def parts(cache: str) -> tuple:
  """The class path, in order, and the natives jars with what not to extract from each."""
  vanilla, forge, universal = versions(cache)
  path = []
  natives = []
  seen = set()
  for library in forge['libraries']:
    name = library['name']
    if library.get('clientreq') is False:
      continue
    seen.add(key(name))
    path.append(universal if key(name) == 'net.minecraftforge:forge' else module(cache, name))
  for library in vanilla['libraries']:
    name = library['name']
    if not allowed(library):
      continue
    classifier = library.get('natives', {}).get(OS_NAME)
    if classifier:
      natives.append((module(cache, name, classifier.replace('${arch}', '64')),
                      library.get('extract', {}).get('exclude', [])))
      continue
    if key(name) in seen:
      continue
    seen.add(key(name))
    path.append(module(cache, name))
  client = os.path.join(unimined(cache), 'minecraft-%s-client.jar' % MINECRAFT)
  if not os.path.isfile(client):
    raise Missing('no %s: build unitTAS once (./gradlew build) to fill the cache' % client)
  path.append(client)
  return path, natives, vanilla, forge


def offlineId(name: str) -> str:
  """The UUID an offline player of that name has, as Java's UUID.nameUUIDFromBytes makes it, without dashes."""
  return uuid.UUID(bytes=hashlib.md5(('OfflinePlayer:' + name).encode('utf-8')).digest(), version=3).hex


def command(cache: str, game: str) -> tuple:
  """The java command, and the natives to extract first."""
  path, natives, vanilla, forge = parts(cache)
  assets = os.path.join(cache, 'caches', 'unimined', 'assets')
  if not os.path.isfile(os.path.join(assets, 'indexes', vanilla['assets'] + '.json')):
    raise Missing('no asset index %s in %s: run ./gradlew runClient once to fetch the assets' % (vanilla['assets'], assets))
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
  java = [java8(), '-Xms512M', '-Xmx2G', '-Djava.library.path=' + os.path.join(game, 'natives'),
          '-cp', os.pathsep.join(path), forge['mainClass']]
  return java + arguments, natives


def extract(natives: list, into: str) -> None:
  """The natives jars' files into the folder, but what each says not to extract (META-INF/)."""
  os.makedirs(into, exist_ok=True)
  for jarPath, excluded in natives:
    with zipfile.ZipFile(jarPath) as jar:
      for entry in jar.namelist():
        if entry.endswith('/') or any(entry.startswith(prefix) for prefix in excluded):
          continue
        target = os.path.join(into, os.path.basename(entry))
        with open(target, 'wb') as out:
          out.write(jar.read(entry))


def main(*args: str) -> int:
  usage = 'Usage: python3 bin/launch_client.py --game DIR [--dry-run]'
  args = list(args)
  dry = '--dry-run' in args
  if dry:
    args.remove('--dry-run')
  if len(args) != 2 or args[0] != '--game':
    print(usage)
    return 2
  game = os.path.abspath(args[1])
  try:
    java, natives = command(cacheRoot(), game)
  except (Missing, OSError, KeyError, ValueError) as problem:
    print('unitTAS launcher: %s' % problem)
    return 2
  if dry:
    print(' '.join(shlex.quote(word) for word in java))
    return 0
  os.makedirs(game, exist_ok=True)
  extract(natives, os.path.join(game, 'natives'))
  sys.stdout.flush()
  os.chdir(game)
  os.execv(java[0], java)
  return 0


if __name__ == '__main__':
  sys.exit(main(*sys.argv[1:]))

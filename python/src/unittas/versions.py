"""
The 'versions' module resolves a Minecraft version for a launch, for any
version and loader (SPEC.md 12.3, step 2): Mojang's version JSON, with a
loader's profile on top, read for this system into what a launch needs.
Nothing here fetches a file or knows one version from another; that is
the launcher's, which takes what this module gives.

A loader's profile is a version JSON of its own that names the version it
inheritsFrom: Fabric's from its meta server, Forge 1.7.10's version.json
in its universal jar. Both forms of the JSON are read:

- the old one (to 1.12): the game's arguments as one 'minecraftArguments'
  string, natives as a 'natives' map of jars to extract;
- the new one: 'arguments' as lists whose items may carry rules (by the
  system's name and arch, and by features such as has_custom_resolution),
  natives as plain jars on the class path, named by a classifier.

The profile's main class and id name the launch. Its libraries come
first, then vanilla's; a library both name (by group, artifact and
classifier) is kept once, the profile's. The profile's arguments follow
vanilla's, or replace them where it has 'minecraftArguments' of its own.
Rules are Mojang's: no rules allow, otherwise the last rule that applies
decides; an os rule's versionRange (Windows only) isn't checked.

Nothing in what this gives is None: an unknown size is -1, no checksum is
an empty tuple, no logging config is an empty dict. The standard library
only: the launcher runs from the system's own Python too.

- Library: one jar, where it lies in a maven tree and where it comes from.
- Version: a version resolved for this system.
- allowed: whether rules allow, for a system and features.
- resolve: a version JSON (and a profile on top) for this system.
- fill: arguments with their placeholders filled; ValueError for one
  without a value.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import platform
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
  from typing import Iterable, Optional

#  Mojang's names for this system and its arch ('x86' is 32-bit x86 in its rules)
OS_NAMES = {'Linux': 'linux', 'Darwin': 'osx', 'Windows': 'windows'}
OS_NAME = OS_NAMES.get(platform.system(), platform.system().lower())
ARCH = platform.machine().lower()
#  Where a library with no URL of its own comes from
MOJANG_LIBRARIES = 'https://libraries.minecraft.net/'
#  An old JSON names no JVM arguments: these are what every launcher gives it
LEGACY_JVM = ('-Djava.library.path=${natives_directory}', '-cp', '${classpath}')
_PLACEHOLDER = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}')


@dataclass(frozen=True)
class Library:
  """
  One jar: its maven name ('group:artifact:version[:classifier]'), its
  path in a maven tree, the URL it comes from, the sha1s it may have (one,
  or Forge's several; empty where the JSON gives none) and its size (-1
  where unknown).
  """
  name: str
  path: str
  url: str
  sha1s: tuple
  size: int


@dataclass(frozen=True)
class Version:
  """
  A version resolved for this system. 'jvm' and 'game' are the arguments
  with their ${placeholders} still in them (fill); 'defaultJvm' is the
  version's own suggested memory and collector flags (empty for an old
  JSON); 'natives' are (Library, the paths not to extract) for an old
  JSON's natives, empty for a new one's; 'assetIndex', 'client' and
  'logging' are the JSON's own entries ('logging' empty where it has none).
  """
  id: str
  mainClass: str
  javaMajor: int
  libraries: tuple
  natives: tuple
  jvm: tuple
  defaultJvm: tuple
  game: tuple
  assets: str
  assetIndex: dict
  client: dict
  logging: dict


# ---------------------------------------------------------------- rules


def _applies(rule: dict, system: str, arch: str, features: dict) -> bool:
  os = rule.get('os', {})
  if 'name' in os and os['name'] != system:
    return False
  if 'arch' in os and os['arch'] != arch:
    return False
  for feature, wanted in rule.get('features', {}).items():
    if bool(features.get(feature, False)) != bool(wanted):
      return False
  return True


def allowed(rules: Iterable[dict], system: str = OS_NAME, arch: str = ARCH,
            features: Optional[dict] = None) -> bool:
  """Whether the rules allow, here: no rules allow; otherwise the last rule that applies decides."""
  rules = list(rules or ())
  if not rules:
    return True
  verdict = False
  for rule in rules:
    if _applies(rule, system, arch, features or {}):
      verdict = rule.get('action') == 'allow'
  return verdict


# ---------------------------------------------------------------- libraries


def _coordinates(name: str) -> tuple:
  parts = name.split(':')
  if len(parts) < 3:
    raise ValueError('%r is no maven name (group:artifact:version)' % (name,))
  return parts[0], parts[1], parts[2], parts[3] if len(parts) > 3 else ''


def _key(name: str) -> str:
  group, artifact, _, classifier = _coordinates(name)
  return ':'.join(part for part in (group, artifact, classifier) if part)


def mavenPath(name: str, classifier: str = '') -> str:
  """Where a maven name's jar lies in a maven tree (its own classifier, or the one given)."""
  group, artifact, version, named = _coordinates(name)
  classifier = classifier or named
  return '%s/%s/%s/%s-%s%s.jar' % (group.replace('.', '/'), artifact, version, artifact, version,
                                   '-' + classifier if classifier else '')


def _sha1s(*candidates) -> tuple:
  out = []
  for candidate in candidates:
    for sha1 in ([candidate] if isinstance(candidate, str) else list(candidate or ())):
      if sha1 and sha1 not in out:
        out.append(sha1)
  return tuple(out)


def _library(entry: dict, classifier: str = '') -> Library:
  """A library entry as one jar: from its downloads where it has them, else from its maven (Mojang's by default)."""
  name = entry['name']
  downloads = entry.get('downloads', {})
  artifact = downloads.get('classifiers', {}).get(classifier) if classifier else downloads.get('artifact')
  if artifact:
    path = artifact.get('path') or mavenPath(name, classifier)
    url = artifact.get('url') or MOJANG_LIBRARIES + path
    return Library(name, path, url, _sha1s(artifact.get('sha1', '')), int(artifact.get('size', -1)))
  path = mavenPath(name, classifier)
  base = entry.get('url') or MOJANG_LIBRARIES
  return Library(name, path, base.rstrip('/') + '/' + path, _sha1s(entry.get('sha1', ''), entry.get('checksums')),
                 int(entry.get('size', -1)))


def _native(entry: dict, system: str, arch: str) -> Optional[tuple]:
  """An old JSON's natives entry for this system: (its jar, what not to extract), or None if it has none here."""
  classifier = entry.get('natives', {}).get(system)
  if not classifier:
    return None
  classifier = classifier.replace('${arch}', '32' if arch in ('x86', 'i386', 'i686') else '64')
  return _library(entry, classifier), tuple(entry.get('extract', {}).get('exclude', ()))


# ---------------------------------------------------------------- arguments


def _arguments(items: Iterable, system: str, arch: str, features: dict) -> tuple:
  out = []
  for item in items or ():
    if isinstance(item, str):
      out.append(item)
      continue
    if allowed(item.get('rules', ()), system, arch, features):
      value = item.get('value', ())
      out.extend([value] if isinstance(value, str) else value)
  return tuple(out)


def fill(arguments: Iterable[str], values: dict) -> list:
  """The arguments with each ${name} replaced by values[name]; ValueError naming every placeholder with no value."""
  missing = sorted({name for argument in arguments for name in _PLACEHOLDER.findall(argument)} - set(values))
  if missing:
    raise ValueError('no value for %s in the launch arguments' % ', '.join('${%s}' % name for name in missing))
  return [_PLACEHOLDER.sub(lambda found: str(values[found.group(1)]), argument) for argument in arguments]


# ---------------------------------------------------------------- the whole


def resolve(vanilla: dict, profile: Optional[dict] = None, system: str = OS_NAME, arch: str = ARCH,
            features: Optional[dict] = None) -> Version:
  """
  The version for this system: vanilla's JSON, with the profile on top
  when there is one (it must name vanilla's id as its inheritsFrom).
  'features' are the launch's (has_custom_resolution and the like), all
  off by default.
  """
  features = dict(features or {})
  profile = dict(profile or {})
  if profile and profile.get('inheritsFrom', vanilla.get('id')) != vanilla.get('id'):
    raise ValueError('the profile %s inherits from %s, not from %s' % (
      profile.get('id'), profile.get('inheritsFrom'), vanilla.get('id')))
  libraries, natives, seen = [], [], set()
  for entry in list(profile.get('libraries', ())) + list(vanilla.get('libraries', ())):
    if entry.get('clientreq') is False or not allowed(entry.get('rules', ()), system, arch, features):
      continue
    if 'natives' in entry:
      native = _native(entry, system, arch)
      if native is not None:
        natives.append(native)
      continue
    key = _key(entry['name'])
    if key in seen:
      continue
    seen.add(key)
    libraries.append(_library(entry))
  legacy = profile.get('minecraftArguments') or vanilla.get('minecraftArguments')
  if 'minecraftArguments' in profile or 'arguments' not in vanilla:
    jvm, game = LEGACY_JVM, tuple((legacy or '').split())
  else:
    modern, extra = vanilla['arguments'], profile.get('arguments', {})
    jvm = _arguments(modern.get('jvm', ()), system, arch, features) + _arguments(extra.get('jvm', ()), system, arch,
                                                                                  features)
    game = _arguments(modern.get('game', ()), system, arch, features) + _arguments(extra.get('game', ()), system,
                                                                                    arch, features)
  defaultJvm = _arguments(vanilla.get('arguments', {}).get('default-user-jvm', ()), system, arch, features)
  return Version(
    id=profile.get('id', vanilla['id']), mainClass=profile.get('mainClass', vanilla['mainClass']),
    javaMajor=int(vanilla.get('javaVersion', {}).get('majorVersion', 8)), libraries=tuple(libraries),
    natives=tuple(natives), jvm=tuple(jvm), defaultJvm=defaultJvm, game=game,
    assets=vanilla.get('assets', vanilla.get('assetIndex', {}).get('id', '')),
    assetIndex=dict(vanilla.get('assetIndex', {})), client=dict(vanilla.get('downloads', {}).get('client', {})),
    logging=dict(vanilla.get('logging', {}).get('client', {})))

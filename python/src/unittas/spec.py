"""
The 'spec' module reads an instance spec: a small TOML file in a mod's
repository that says which game a run needs (SPEC.md 9.3, step 2).

  minecraft = "1.7.10"
  loader = { forge = "10.13.4.1614" }
  client = "real"                        # or "gradle": said, never assumed
  mods = ["build/libs/mod-*.jar"]        # each matching exactly one file
  build = "./gradlew reobfJar"           # run first, without a shell
  libraries = ["maven:group:artifact:version", "libs/a-library.jar"]
  repositories = ["https://example.com/maven/"]
  config = "test-config"                 # copied into the game's config/
  options = { autoJump = false }         # options.txt for the run
  probe = "bundled"                      # or a probe jar of one's own
  game = "run/unittas"                   # the real client's game folder
  window = { width = 854, height = 480, display = "nested" }

  [gradle]                               # for client = "gradle"
  project = "."
  task = "runClient"
  game = "run/client"

Paths are taken from the spec's own folder. Every mistake is a SpecError
that names the file and the key, an unknown key too (with the key it
likely meant): it is a file people write by hand. Phase 3 runs 1.7.10
with Forge 10.13.4.1614 only (SPEC.md 9.6, decision 5).

- SpecError: what is wrong with a spec, and where.
- MavenLibrary: a library by its Maven coordinates.
- InstanceSpec: a spec as read; InstanceSpec.read(path) reads one.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import difflib
import glob
import os
import shlex
import tomllib
from typing import TYPE_CHECKING

from worktoy.ezdata import EZData, EZField

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Optional

#  What phase 3 runs (SPEC.md 9.6, decision 5).
MINECRAFT = '1.7.10'
FORGE = '10.13.4.1614'
CLIENTS = ('real', 'gradle')
DISPLAYS = ('nested', 'headless', 'plain')
KEYS = ('minecraft', 'loader', 'java', 'client', 'mods', 'build', 'libraries', 'repositories', 'config', 'options',
        'probe', 'game', 'window', 'gradle')
GRADLE_KEYS = ('project', 'task', 'game')
WINDOW_KEYS = ('width', 'height', 'display')
#  A build is a command and its arguments, run without a shell: these would mean something only to a shell.
SHELL_WORDS = ('&&', '||', '|', ';', '&', '>', '>>', '<')


class SpecError(ValueError):
  """What is wrong with an instance spec; the message starts with the file."""


class MavenLibrary(EZData, frozen=True):
  """A library by its Maven coordinates (group:artifact:version[:classifier])."""
  group = EZField[str]('')
  artifact = EZField[str]('')
  version = EZField[str]('')
  classifier = EZField[str]('')


class InstanceSpec(EZData, frozen=True):
  """
  An instance spec as read. Paths are absolute; 'java', 'build' and
  'config' are None when the spec doesn't say (the fields beside them
  hold an empty stand-in until worktoy 1.1 has nullable fields).
  """
  path = EZField[str]('')
  folder = EZField[str]('')
  minecraft = EZField[str]('')
  loaderName = EZField[str]('')
  loaderVersion = EZField[str]('')
  javaText = EZField[str]('')
  client = EZField[str]('')
  mods = EZField[tuple]()
  buildArgs = EZField[tuple]()
  libraries = EZField[tuple]()
  repositories = EZField[tuple]()
  configPath = EZField[str]('')
  optionPairs = EZField[tuple]()
  probe = EZField[str]('bundled')
  game = EZField[str]('')
  width = EZField[int](854)
  height = EZField[int](480)
  display = EZField[str]('nested')
  gradleProject = EZField[str]('')
  gradleTask = EZField[str]('')


# ---------------------------------------------------------------- reading


class _Reader:
  """One spec being read: its file, its folder, and the refusals, each naming the file and the key."""

  def __init__(self, path: str) -> None:
    self.path = os.path.abspath(path)
    self.folder = os.path.dirname(self.path)

  def fail(self, message: str) -> SpecError:
    return SpecError('%s: %s' % (self.path, message))

  def local(self, relative: str) -> str:
    return os.path.normpath(os.path.join(self.folder, os.path.expanduser(relative)))

  def string(self, table: dict, key: str, where: str = '', otherwise: Any = None) -> Any:
    name = where + key
    if key not in table:
      if otherwise is None:
        raise self.fail('"%s" is needed' % name)
      return otherwise
    value = table[key]
    if not isinstance(value, str) or not value:
      raise self.fail('"%s" is a string that isn\'t empty, not %r' % (name, value))
    return value

  def strings(self, table: dict, key: str) -> tuple:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(each, str) and each for each in value):
      raise self.fail('"%s" is a list of strings, not %r' % (key, value))
    return tuple(value)

  def table(self, table: dict, key: str) -> dict:
    value = table.get(key, {})
    if not isinstance(value, dict):
      raise self.fail('"%s" is a table ({ ... }), not %r' % (key, value))
    return value

  def known(self, table: dict, keys: tuple, where: str = '') -> None:
    for key in table:
      if key not in keys:
        close = difflib.get_close_matches(key, keys, 1)
        hint = '; did you mean "%s%s"?' % (where, close[0]) if close else ' (the keys: %s)' % ', '.join(keys)
        raise self.fail('unknown key "%s%s"%s' % (where, key, hint))


def _read(cls: type, path: str) -> InstanceSpec:
  """The spec in the file; SpecError naming the file and the key for anything wrong."""
  reader = _Reader(path)
  try:
    with open(reader.path, 'rb') as file:
      body = tomllib.load(file)
  except FileNotFoundError:
    raise reader.fail('no such file') from None
  except tomllib.TOMLDecodeError as error:
    raise reader.fail('not TOML: %s' % error) from None
  reader.known(body, KEYS)
  minecraft = reader.string(body, 'minecraft')
  if minecraft != MINECRAFT:
    raise reader.fail('"minecraft" is %s: this unitTAS runs %s only' % (minecraft, MINECRAFT))
  loaderName, loaderVersion = _loader(reader, body)
  if 'client' not in body:
    raise reader.fail('"client" is needed: "real" (the release jars in a real client) or "gradle" (the mod\'s own'
                      ' Gradle run), said, never assumed')
  client = reader.string(body, 'client')
  if client not in CLIENTS:
    raise reader.fail('"client" is "real" or "gradle", not "%s"' % client)
  libraries = tuple(_library(reader, entry) for entry in reader.strings(body, 'libraries'))
  repositories = reader.strings(body, 'repositories')
  if any(isinstance(library, MavenLibrary) for library in libraries) and not repositories:
    raise reader.fail('"repositories" is needed: a maven: library comes from a repository the spec names')
  for repository in repositories:
    if not repository.startswith('https://'):
      raise reader.fail('"repositories" are https:// addresses only, not %s' % repository)
  config = ''
  if 'config' in body:
    config = reader.local(reader.string(body, 'config'))
    if not os.path.isdir(config):
      raise reader.fail('"config" is a folder, and %s is none' % config)
  probe = reader.string(body, 'probe', otherwise='bundled')
  width, height, display = _window(reader, body)
  gradleProject = gradleTask = ''
  if client == 'gradle':
    if 'game' in body:
      raise reader.fail('"game" is the real client\'s; for client = "gradle" it is "gradle.game"')
    gradle = reader.table(body, 'gradle')
    reader.known(gradle, GRADLE_KEYS, 'gradle.')
    gradleProject = reader.local(reader.string(gradle, 'project', 'gradle.', '.'))
    gradleTask = reader.string(gradle, 'task', 'gradle.', 'runClient')
    game = reader.local(reader.string(gradle, 'game', 'gradle.'))
  else:
    if 'gradle' in body:
      raise reader.fail('"gradle" is only for client = "gradle"; this spec says client = "%s"' % client)
    game = reader.local(reader.string(body, 'game', otherwise='run/unittas'))
  return cls(
    path=reader.path, folder=reader.folder, minecraft=minecraft, loaderName=loaderName, loaderVersion=loaderVersion,
    javaText=reader.string(body, 'java', otherwise=''), client=client, mods=reader.strings(body, 'mods'),
    buildArgs=_build(reader, body), libraries=libraries, repositories=repositories, configPath=config,
    optionPairs=_options(reader, body), probe=probe if probe == 'bundled' else reader.local(probe), game=game,
    width=width, height=height, display=display, gradleProject=gradleProject, gradleTask=gradleTask)


def _loader(reader: _Reader, body: dict) -> tuple:
  if 'loader' not in body:
    raise reader.fail('"loader" is needed: { forge = "%s" }' % FORGE)
  loader = reader.table(body, 'loader')
  if list(loader) != ['forge']:
    raise reader.fail('"loader" is { forge = "%s" }: this unitTAS runs Forge only, not %s' % (FORGE, loader))
  version = reader.string(loader, 'forge', 'loader.')
  if version != FORGE:
    raise reader.fail('"loader" is Forge %s: this unitTAS runs Forge %s only' % (version, FORGE))
  return 'forge', version


def _library(reader: _Reader, entry: str) -> Any:
  if entry.startswith('maven:'):
    parts = entry[len('maven:'):].split(':')
    if len(parts) not in (3, 4) or not all(parts):
      raise reader.fail('"libraries": %s is maven:group:artifact:version[:classifier]' % entry)
    return MavenLibrary(*parts) if len(parts) == 4 else MavenLibrary(parts[0], parts[1], parts[2], '')
  path = reader.local(entry)
  if not os.path.isfile(path):
    raise reader.fail('"libraries": %s is no file (%s)' % (entry, path))
  return path


def _build(reader: _Reader, body: dict) -> tuple:
  if 'build' not in body:
    return ()
  text = reader.string(body, 'build')
  try:
    words = tuple(shlex.split(text))
  except ValueError as error:
    raise reader.fail('"build" can\'t be split into words: %s' % error) from None
  if not words:
    raise reader.fail('"build" is a command, not an empty string')
  if any(word in SHELL_WORDS or '`' in word or '$(' in word for word in words):
    raise reader.fail('"build" is a command and its arguments, run without a shell: %r means something only to a'
                      ' shell' % text)
  return words


def _options(reader: _Reader, body: dict) -> tuple:
  options = reader.table(body, 'options')
  for key, value in options.items():
    if not isinstance(value, (bool, int, float, str)):
      raise reader.fail('"options": %s is a number, true or false, or a string, not %r' % (key, value))
  return tuple(options.items())


def _window(reader: _Reader, body: dict) -> tuple:
  window = reader.table(body, 'window')
  reader.known(window, WINDOW_KEYS, 'window.')
  sizes = []
  for key, otherwise in (('width', 854), ('height', 480)):
    value = window.get(key, otherwise)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
      raise reader.fail('"window": %s is a whole number of pixels, not %r' % (key, value))
    sizes.append(value)
  display = window.get('display', 'nested')
  if display not in DISPLAYS:
    raise reader.fail('"window": display is one of %s, not %r' % (', '.join(DISPLAYS), display))
  return sizes[0], sizes[1], display


# ---------------------------------------------------------------- the mods' jars


def _modJars(self: InstanceSpec) -> tuple:
  """Each of 'mods' as the one file it matches; SpecError for one that matches none, or more than one."""
  found = []
  for pattern in self.mods:
    matches = sorted(glob.glob(os.path.join(self.folder, pattern)))
    if not matches:
      raise SpecError('%s: "mods": %s matches no file' % (self.path, pattern))
    if len(matches) > 1:
      raise SpecError('%s: "mods": %s matches %d files, one is wanted: %s' % (
        self.path, pattern, len(matches), ', '.join(os.path.basename(match) for match in matches)))
    found.append(matches[0])
  return tuple(found)


# set on the class after it is made: on Python 3.14+ a function in an EZData body becomes a field (worktoy-notes.md, 7)
InstanceSpec.read = classmethod(_read)
InstanceSpec.modJars = _modJars
InstanceSpec.java = property(lambda self: self.javaText or None, doc='The Java the spec names, or None.')
InstanceSpec.build = property(lambda self: self.buildArgs or None, doc='The build command and its arguments, or None.')
InstanceSpec.config = property(lambda self: self.configPath or None, doc="The config folder to copy in, or None.")
InstanceSpec.options = property(lambda self: dict(self.optionPairs), doc='The options for options.txt.')

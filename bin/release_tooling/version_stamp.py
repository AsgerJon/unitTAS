"""
This script stamps a resolved version string into every file that shows
unitTAS's version to the outside world:
- 'gradle.properties': the 'mod_version=...' line the build reads, which
  names both jars and goes into 'mcmod.info'.
- 'src/main/java/io/github/asgerjon/unittas/UnitTasMod.java': the
  'VERSION' constant the '@Mod' annotation names.
- 'README.md': every unitTAS version it names, as in
  'unittas-X.jar', 'unittas-X-dev.jar' and 'io.github.asgerjon:unittas:X'.

The version string is read from the environment variable named by the
first argument, defaulting to 'VERSION_INFO'. The release workflows call
'version_get.py' to export the resolved version under that name, then
call this script to write it into the three files before building.

Before writing anything the script checks that the three files agree on
the version they carry now, and it refuses a version string outside the
release scheme: 'X.Y.Z', 'X.Y.Z-rcN' or 'X.Y.Z-devN'. Given the sole
argument '--check' instead, it only checks that the three files agree,
and names the version they carry.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import sys
import os
import re

PROPERTIES_PREFIX = 'mod_version='
CONSTANT_PREFIX = 'public static final String VERSION ='
MOD_PATH = (
  'src', 'main', 'java', 'io', 'github', 'asgerjon', 'unittas',
  'UnitTasMod.java',
)
#  The versions the release workflows publish.
SCHEME = re.compile(r'\d+\.\d+\.\d+(?:-(?:rc|dev)\d+)?')
#  A unitTAS version named in README.md: after 'unittas-' (a jar's name)
#  or 'unittas:' (a module's coordinates), in any case ('unitTAS:' is
#  JitPack's 'com.github.AsgerJon:unitTAS:X'). The '-dev' of
#  'unittas-X-dev.jar' is the dev jar's classifier, not a part of the
#  version. Any suffix is read, not only the scheme's, so a version from
#  before the scheme (such as '0.1.0-beta') is found and stamped over too.
MENTION = re.compile(
  r'(?<=unittas[-:])\d+\.\d+\.\d+(?:-(?!dev\.jar)[A-Za-z]+\d*)?',
  re.IGNORECASE,
)
CONSTANT_VALUE = re.compile(r'"([^"]*)"')


class VersionDrift(RuntimeError):
  """
  The stamped files disagree on the version they carry, or one of them
  carries none.
  """


def _here() -> str:
  """
  This function resolves the path to the present directory containing this
  script.

  Returns
  -------
  str
    The absolute path to the present directory containing this script.
  """
  filePath: str = os.path.abspath(__file__)
  return os.path.dirname(filePath)


def _root() -> str:
  """
  This function resolves the repository root by walking up from this
  script's directory until it finds the directory holding 'settings.gradle',
  so the script works regardless of how deeply it is nested under the root.

  Returns
  -------
  str
    The absolute path to the repository root.

  Raises
  ------
  RuntimeError
    If no ancestor directory holds 'settings.gradle'.
  """
  current = _here()
  while current != os.path.dirname(current):
    if os.path.isfile(os.path.join(current, 'settings.gradle')):
      return current
    current = os.path.dirname(current)
  raise RuntimeError("Could not locate the repository root!")


def _badLocation() -> int:
  """
  This function validates that the repository root can be resolved and
  carries the expected project layout.

  Returns
  -------
  int
    0 if the script is correctly located, 1 otherwise.
  """
  requiredItems = ['src', 'gradle.properties', 'settings.gradle', 'README.md']
  try:
    presentItems = os.listdir(_root())
  except RuntimeError:
    return 1
  for item in requiredItems:
    if item not in presentItems:
      break
  else:
    return 0
  return 1


def _paths() -> dict[str, str]:
  """
  This function resolves the absolute paths of the three stamped files.

  Returns
  -------
  dict[str, str]
    The paths under the keys 'properties', 'constant' and 'manual'.
  """
  root = _root()
  return dict(
      properties=os.path.join(root, 'gradle.properties'),
      constant=os.path.join(root, *MOD_PATH),
      manual=os.path.join(root, 'README.md'),
  )


def _readText(path: str) -> str:
  """
  This function reads and returns the full text of the file at 'path'.

  Parameters
  ----------
  path : str
    The absolute path to the file to read.

  Returns
  -------
  str
    The file contents.
  """
  f = None
  try:
    f = open(path, 'r', encoding='utf-8')
  except Exception as exception:
    raise exception
  else:
    return f.read()
  finally:
    try:
      f.close()  # noqa: F821
    except AttributeError:
      pass


def _writeText(path: str, text: str) -> None:
  """
  This function writes 'text' to the file at 'path', replacing it.

  Parameters
  ----------
  path : str
    The absolute path to the file to write.
  text : str
    The text to write.
  """
  f = None
  try:
    f = open(path, 'w', encoding='utf-8')
  except Exception as exception:
    raise exception
  else:
    f.write(text)
  finally:
    try:
      f.close()  # noqa: F821
    except AttributeError:
      pass


def _lineIndex(lines: list[str], prefix: str, path: str) -> int:
  """
  This function finds the first line whose stripped form starts with
  'prefix'. A file without such a line is an error: every stamped file is
  expected to already carry the line being replaced.

  Parameters
  ----------
  lines : list[str]
    The lines of the file.
  prefix : str
    The prefix identifying the line.
  path : str
    The path of the file, for the error message.

  Returns
  -------
  int
    The index of the line.
  """
  for i, line in enumerate(lines):
    if str.startswith(str.strip(line), prefix):
      return i
  infoSpec = """Found no line starting with '%s' in file: '%s'!"""
  raise VersionDrift(infoSpec % (prefix, path))


def _carried() -> dict[str, list[str]]:
  """
  This function reads the version each stamped file carries now.

  Returns
  -------
  dict[str, list[str]]
    Under 'properties' and 'constant' the one version of that file, and
    under 'manual' every unitTAS version README.md names, in order.
  """
  paths = _paths()
  out = dict()
  lines = str.split(_readText(paths['properties']), '\n')
  line = lines[_lineIndex(lines, PROPERTIES_PREFIX, paths['properties'])]
  out['properties'] = [str.strip(str.split(line, '=', 1)[1])]
  lines = str.split(_readText(paths['constant']), '\n')
  line = lines[_lineIndex(lines, CONSTANT_PREFIX, paths['constant'])]
  match = CONSTANT_VALUE.search(line)
  if match is None:
    infoSpec = """Found no quoted version in line: '%s' of file: '%s'!"""
    raise VersionDrift(infoSpec % (str.strip(line), paths['constant']))
  out['constant'] = [match.group(1)]
  out['manual'] = MENTION.findall(_readText(paths['manual']))
  return out


def check() -> str:
  """
  This function checks that the three stamped files carry one and the
  same version, README.md naming it at least once.

  Returns
  -------
  str
    The version the three files carry.

  Raises
  ------
  VersionDrift
    If they disagree, or README.md names no unitTAS version.
  """
  carried = _carried()
  version = carried['properties'][0]
  if not carried['manual']:
    infoSpec = """README.md names no unitTAS version (as in
    'unittas-%s.jar'), so a release would not stamp its recipes!"""
    raise VersionDrift(str.join(' ', str.split(infoSpec % version)))
  others = [*carried['constant'], *carried['manual']]
  if any(other != version for other in others):
    infoSpec = """The stamped files disagree on the version:
    gradle.properties says '%s', UnitTasMod.VERSION says '%s' and
    README.md names %s. Make them agree before releasing!"""
    named = ', '.join(["'%s'" % item for item in carried['manual']])
    info = infoSpec % (version, carried['constant'][0], named)
    raise VersionDrift(str.join(' ', str.split(info)))
  return version


def _stampAll(versionStr: str) -> str:
  """
  This function stamps the given version string into 'gradle.properties',
  'UnitTasMod.java' and 'README.md', having first checked that they agree
  on the version they carry. All three are rewritten only once all three
  have been prepared, so a file that disagrees, or lacks its line, leaves
  none of them changed.

  Parameters
  ----------
  versionStr : str
    The version string to stamp, in the format 'X.Y.Z', 'X.Y.Z-rcN' or
    'X.Y.Z-devN', where X, Y, Z and N are integers.

  Returns
  -------
  str
    The version the files carried before.
  """
  before = check()
  paths = _paths()
  out = dict()
  lines = str.split(_readText(paths['properties']), '\n')
  i = _lineIndex(lines, PROPERTIES_PREFIX, paths['properties'])
  lines[i] = '%s%s' % (PROPERTIES_PREFIX, versionStr)
  out['properties'] = str.join('\n', lines)
  lines = str.split(_readText(paths['constant']), '\n')
  i = _lineIndex(lines, CONSTANT_PREFIX, paths['constant'])
  indent = lines[i][:len(lines[i]) - len(str.lstrip(lines[i]))]
  lines[i] = '%s%s "%s";' % (indent, CONSTANT_PREFIX, versionStr)
  out['constant'] = str.join('\n', lines)
  out['manual'] = MENTION.sub(versionStr, _readText(paths['manual']))
  for key in ('properties', 'constant', 'manual'):
    _writeText(paths[key], out[key])
  return before


def main(*args: str, ) -> int:
  """
  This is the main function of the script. The optional first argument
  names the environment variable holding the version string to stamp,
  defaulting to 'VERSION_INFO'; the argument '--check' instead only checks
  that the stamped files agree. It returns 0 on success, and a non-zero
  integer on failure.

  Parameters
  ----------
  *args : str
    The command-line arguments passed to the script, excluding the script
    name: the optional environment variable name, or '--check'.

  Returns
  -------
  int
    0 on success, and a non-zero integer on failure. Possible failure
    codes:
    - 1: More than one argument provided.
    - 2: The named environment variable is not set or is empty.
    - 3: Could not resolve the repository root.
    - 4: Exception raised while stamping a file.
    - 5: The stamped files disagree on the version they carry now.
    - 6: The version string is not one the release scheme makes.
  """
  if len(args) > 1:
    infoSpec = """Usage: python bin/release_tooling/version_stamp.py """
    infoSpec += """[ENV_VAR_NAME | --check]"""
    print(infoSpec)
    return 1
  if _badLocation():
    print('Could not validate location of this script!')
    return 3
  if args and args[0] == '--check':
    try:
      version = check()
    except VersionDrift as exception:
      print(exception)
      return 5
    print('The stamped files agree on version: %s' % version)
    return 0
  envKey = args[0] if args else 'VERSION_INFO'
  versionStr = str.strip(os.environ.get(envKey, ''))
  if not versionStr:
    infoSpec = """Expected the environment variable '%s' to hold the
    version string to stamp, but found it unset or empty!"""
    print(str.join(' ', str.split(infoSpec % envKey)))
    return 2
  if SCHEME.fullmatch(versionStr) is None:
    infoSpec = """Refusing to stamp '%s': the release scheme makes only
    'X.Y.Z', 'X.Y.Z-rcN' and 'X.Y.Z-devN'."""
    print(str.join(' ', str.split(infoSpec % versionStr)))
    return 6
  try:
    before = _stampAll(versionStr)
  except VersionDrift as exception:
    print(exception)
    return 5
  except Exception as exception:
    print(exception)
    return 4
  else:
    print('Stamped version: %s (was %s)' % (versionStr, before))
    return 0


if __name__ == '__main__':
  sys.exit(main(*sys.argv[1:]))

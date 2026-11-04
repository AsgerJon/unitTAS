"""
This script updates the 'VERSION' file to advance the version counters
after a successful release. It requires one argument specifying the
workflow that just published, one of either:
- 'dev'
- 'rc'
- 'lts'
- 'minor'
- 'major'

For 'dev' and 'rc' workflows, only the corresponding counter is
incremented. For 'lts', 'minor' and 'major' workflows, the relevant
counter is incremented and lower-order counters are reset, with 'micro'
set to 1 after 'minor' or 'major' so that the next default 'lts' release
is the patch-level above the one just published.

A 'dev' bump is refused while a release candidate cycle is already
underway, that is while the 'rc' counter is non-zero, mirroring the same
guard in version_get.py: dev releases belong before the first rc within a
version line, since a dev version sorts below an rc.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import sys
import os


def _here() -> str:
  """
  This function resolves the path to the present directory containing
  this script.

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
  This function validates that the script is correctly located in the
  root.

  Returns
  -------
  int
    0 if the script is correctly located, 1 otherwise.
  """
  requiredItems = ['src', 'gradle.properties', 'settings.gradle']
  presentItems = os.listdir(_root())
  for item in requiredItems:
    if item not in presentItems:
      break
  else:
    return 0
  return 1


def _badData(**kwargs: int) -> int:
  """
  This function validates that all required data is present.

  Parameters
  ----------
  kwargs
    Expected to contain the following keys, with integer values:
    - 'major': The next major version number.
    - 'minor': The next minor version number.
    - 'micro': The next micro version number.
    - 'dev': The next dev version number, starting from 0.
    - 'rc': The next release candidate version number, starting from 0.

  Returns
  -------
  int
    0 if all required data is present and valid, 1 otherwise.
  """
  requiredKeys = ['major', 'minor', 'micro', 'dev', 'rc', ]
  for key in requiredKeys:
    if key not in kwargs:
      break
    value = kwargs[key]
    if not isinstance(value, int):
      break
  else:
    return 0
  return 1


def _readVersion() -> dict[str, int]:
  """
  This function locates the 'VERSION' file beside this script and
  parses it.

  Returns
  -------
  dict[str, int]
    A dictionary containing the version information, with keys 'major',
    'minor', 'micro', 'dev' and 'rc', and integer values for each.
  """
  if _badLocation():
    infoSpec = """Could not validate location of this script!"""
    raise RuntimeError(infoSpec)
  versionPath = os.path.join(_here(), 'VERSION')
  f = None
  out = dict()
  try:
    f = open(versionPath, 'r', encoding='utf-8')
  except Exception as exception:
    raise exception
  else:
    lines = str.split(f.read(), '\n')
    for line in lines:
      line = str.strip(line)
      if not line or str.startswith(line, '#') or '=' not in line:
        continue
      key, value, *remainder = str.split(line, '=')
      if remainder:
        infoSpec = """Received multiple '=' in line: '%s'!"""
        raise RuntimeError(infoSpec % line)
      key = str.lower(str.strip(key))
      value = int(str.strip(value))
      out[key] = value
    if _badData(**out):
      infoSpec = """Received invalid data in 'VERSION' file! Expected 
      keys: 'major', 'minor', 'micro', 'dev' and 'rc', with integer 
      values for each."""
      raise RuntimeError(str.join(' ', str.split(infoSpec)))
    return out
  finally:
    try:
      f.close()  # noqa: F821
    except AttributeError:
      pass


def _readComments() -> list[str]:
  """
  This function reads the comments from the 'VERSION' file, which are
  expected to be lines starting with '#' and located at the top of the
  file.

  Returns
  -------
  list[str]
    A list of comment lines, including the leading '#' character.
  """
  if _badLocation():
    infoSpec = """Could not validate location of this script!"""
    raise RuntimeError(infoSpec)
  versionPath = os.path.join(_here(), 'VERSION')
  f = None
  out = []
  try:
    f = open(versionPath, 'r', encoding='utf-8')
  except Exception as exception:
    raise exception
  else:
    lines = str.split(f.read(), '\n')
    for line in lines:
      line = str.strip(line)
      if not line or not str.startswith(line, '#'):
        continue
      out.append(line)
    return out
  finally:
    try:
      f.close()  # noqa: F821
    except AttributeError:
      pass


def _writeVersion(versionInfo: dict[str, int]) -> None:
  """
  Overwrite the 'VERSION' file with the given version data.

  Parameters
  ----------
  versionInfo : dict[str, int]
    Dictionary with keys 'major', 'minor', 'micro', 'rc' and 'dev', with
    integer values for each.
  """
  if _badLocation():
    infoSpec = """Could not validate location of this script!"""
    raise RuntimeError(infoSpec)
  if _badData(**versionInfo):
    infoSpec = """Received invalid data! Expected keys: 'major', 
    'minor', 'micro', 'dev' and 'rc', with integer values for each."""
    raise RuntimeError(str.join(' ', str.split(infoSpec)))
  comments = _readComments()
  versionPath = os.path.join(_here(), 'VERSION')
  content: str = str.join(
      '\n',
      [
        *comments,
        'MAJOR=%d' % versionInfo['major'],
        'MINOR=%d' % versionInfo['minor'],
        'MICRO=%d' % versionInfo['micro'],
        'RC=%d' % versionInfo['rc'],
        'DEV=%d' % versionInfo['dev'],
        ''
      ]
  )
  f = None
  try:
    f = open(versionPath, 'w', encoding='utf-8', newline='')
  except Exception as exception:
    raise exception
  else:
    f.write(content)
  finally:
    try:
      f.close()  # noqa: F821
    except AttributeError:
      pass


def _bumpDEV(versionInfo: dict[str, int]) -> dict[str, int]:
  """
  Increment 'dev', leaving all other counters unchanged.

  Parameters
  ----------
  versionInfo : dict[str, int]
    The current version data.

  Returns
  -------
  dict[str, int]
    The updated version data.
  """
  versionInfo['dev'] += 1
  return versionInfo


def _bumpRC(versionInfo: dict[str, int]) -> dict[str, int]:
  """
  Increment 'rc', leaving all other counters unchanged.

  Parameters
  ----------
  versionInfo : dict[str, int]
    The current version data.

  Returns
  -------
  dict[str, int]
    The updated version data.
  """
  versionInfo['rc'] += 1
  return versionInfo


def _bumpLTS(versionInfo: dict[str, int]) -> dict[str, int]:
  """
  Increment 'micro' and reset 'dev' and 'rc' to zero.

  Parameters
  ----------
  versionInfo : dict[str, int]
    The current version data.

  Returns
  -------
  dict[str, int]
    The updated version data.
  """
  versionInfo['micro'] += 1
  versionInfo['dev'] = 0
  versionInfo['rc'] = 0
  return versionInfo


def _bumpMINOR(versionInfo: dict[str, int]) -> dict[str, int]:
  """
  Increment 'minor', set 'micro' to 1, and reset 'dev' and 'rc' to zero.
  After a minor release of 'X.Y.0' the next 'lts' release will be
  'X.Y.1'.

  Parameters
  ----------
  versionInfo : dict[str, int]
    The current version data.

  Returns
  -------
  dict[str, int]
    The updated version data.
  """
  versionInfo['minor'] += 1
  versionInfo['micro'] = 1
  versionInfo['dev'] = 0
  versionInfo['rc'] = 0
  return versionInfo


def _bumpMAJOR(versionInfo: dict[str, int]) -> dict[str, int]:
  """
  Increment 'major', set 'minor' to 0 and 'micro' to 1, and reset 'dev'
  and 'rc' to zero. After a major release of 'X.0.0' the next 'lts'
  release will be 'X.0.1'.

  Parameters
  ----------
  versionInfo : dict[str, int]
    The current version data.

  Returns
  -------
  dict[str, int]
    The updated version data.
  """
  versionInfo['major'] += 1
  versionInfo['minor'] = 0
  versionInfo['micro'] = 1
  versionInfo['dev'] = 0
  versionInfo['rc'] = 0
  return versionInfo


def main(*args: str, ) -> int:
  """
  This is the main function of the script. It requires exactly one
  argument specifying the workflow that just published, one of either:
  'dev', 'rc', 'lts', 'minor' or 'major'. It reads the 'VERSION' file,
  applies the corresponding bump rule, and writes the updated 'VERSION'
  file. It returns 0 on success, and a non-zero integer on failure.

  Parameters
  ----------
  *args : str
    The command-line arguments passed to the script, excluding the
    script name. Expected to contain exactly one argument specifying
    the workflow that just published.

  Returns
  -------
  int
    0 on success, and a non-zero integer on failure. Possible failure
    codes:
    - 1: No arguments provided.
    - 2: More than one argument provided.
    - 3: Unrecognized workflow argument.
    - 4: Exception raised while reading, bumping or writing the VERSION
      file.
    - 5: A dev bump was requested while a release candidate cycle is
      already underway for the current version.
  """
  if not args:
    infoSpec = """Usage: python bin/release_tooling/version_bump.py 
    [dev|rc|lts|minor|major]"""
    print(str.join(' ', str.split(infoSpec)))
    return 1
  funcDict = dict(
      dev=_bumpDEV,
      rc=_bumpRC,
      lts=_bumpLTS,
      minor=_bumpMINOR,
      major=_bumpMAJOR,
  )
  workflow, *remainder = args
  if remainder:
    infoSpec = """Received unexpected extra arguments: %s! Expected 
    exactly one argument specifying the workflow."""
    argStr = ', '.join(["'%s'" % arg for arg in remainder])
    info = infoSpec % argStr
    print(str.join(' ', str.split(info)))
    return 2
  workflow = str.lower(str.strip(workflow))
  if workflow not in funcDict:
    infoSpec = """Unrecognized workflow: '%s'! Expected one of: %s"""
    expected = """dev, rc, lts, minor or major"""
    print(infoSpec % (workflow, expected))
    return 3
  if workflow == 'dev':
    versionInfo = _readVersion()
    if versionInfo['rc']:
      infoSpec = """Refusing to bump the dev counter while a release
      candidate cycle is already underway (rc=%d) for %d.%d.%d: a dev
      release sorts below the release candidates already published, which
      would break version ordering. Publish dev releases before the first
      rc, or cut the lts release first."""
      info = infoSpec % (
        versionInfo['rc'], versionInfo['major'],
        versionInfo['minor'], versionInfo['micro']
      )
      print(str.join(' ', str.split(info)))
      return 5
  func = funcDict[workflow]
  try:
    versionInfo = _readVersion()
    versionInfo = func(versionInfo)
    _writeVersion(versionInfo)
  except Exception as exception:
    print(exception)
    return 4
  else:
    return 0


if __name__ == '__main__':
  sys.exit(main(*sys.argv[1:]))

"""
This script returns the upcoming version number. It requires one argument
specifying the workflow, one of either:
- 'dev'
- 'rc'
- 'lts'
- 'minor'
- 'major'
The version numbering returned is the next version number for the
specified workflow. If it returns '1.2.3' for 'lts', it means that the
next LTS release should be version '1.2.3'. The dev version has the same
version as the next lts release, but with a '-dev' suffix. For example,
if the next LTS release is '1.2.3', the dev version is '1.2.3-dev0' for
the first dev version. Release candidates follow the same scheme, but with
the '-rc' suffix. For example, if the next LTS release is '1.2.3',
the first release candidate is '1.2.3-rc0'.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import sys
import os


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
  This function locates the 'VERSION' file beside this script.

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
    f = open(versionPath, 'r')
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
      infoSpec = """Received invalid data in 'VERSION' file! Expected keys:
      'major', 'minor', 'micro', 'dev' and 'rc', with integer values for 
      each."""
      raise RuntimeError(str.join(' ', str.split(infoSpec)))
    return out
  finally:
    try:
      f.close()  # noqa: F821
    except AttributeError:
      pass


def _getDEV() -> str:
  """
  Getter-function for the next dev version number.

  Returns
  -------
  str
    The next dev version number, in the format 'X.Y.Z-devN', where X, Y,
    Z and N are integers. The X.Y.Z part is the same as the next LTS
    version number, and the N part is the next dev version number,
    starting from 0.
  """
  infoSpec = """%d.%d.%d-dev%d"""
  versionInfo = _readVersion()
  major = versionInfo['major']
  minor = versionInfo['minor']
  micro = versionInfo['micro']
  dev = versionInfo['dev']
  return infoSpec % (major, minor, micro, dev)


def _getRC() -> str:
  """
  Getter-function for the next release candidate version number.

  Returns
  -------
  str
    The next release candidate version number, in the format 'X.Y.Z-rcN',
    where X, Y, Z and N are integers. The X.Y.Z part is the same as the
    next LTS version number, and the N part is the next release candidate
    version number, starting from 0.
  """
  infoSpec = """%d.%d.%d-rc%d"""
  versionInfo = _readVersion()
  major = versionInfo['major']
  minor = versionInfo['minor']
  micro = versionInfo['micro']
  rc = versionInfo['rc']
  return infoSpec % (major, minor, micro, rc)


def _getLTS() -> str:
  """
  Getter-function for the next LTS version number.

  Returns
  -------
  str
    The next LTS version number, in the format 'X.Y.Z', where X, Y and Z
    are integers. The X part is the next major version number, the Y part
    is the next minor version number, and the Z part is the next micro
    version number.
  """
  infoSpec = """%d.%d.%d"""
  versionInfo = _readVersion()
  major = versionInfo['major']
  minor = versionInfo['minor']
  micro = versionInfo['micro']
  return infoSpec % (major, minor, micro)


def _getMINOR() -> str:
  """
  Getter-function for the next minor version number.

  Returns
  -------
  str
    The next minor version number, in the format 'X.Y.0', where X and Y
    are integers. The X part is the next major version number, and the Y
    part is the next minor version number.
  """
  infoSpec = """%d.%d.0"""
  versionInfo = _readVersion()
  major = versionInfo['major']
  minor = versionInfo['minor']
  return infoSpec % (major, minor + 1)


def _getMAJOR() -> str:
  """
  Getter-function for the next major version number.

  Returns
  -------
  str
    The next major version number, in the format 'X.0.0', where X is an
    integer. The X part is the next major version number.
  """
  infoSpec = """%d.0.0"""
  versionInfo = _readVersion()
  major = versionInfo['major']
  return infoSpec % (major + 1)


def _saveVersion(versionStr: str, envKey: str) -> None:
  """
  This function appends 'envKey=versionStr' to the file named by the
  'GITHUB_ENV' environment variable, the mechanism a GitHub Actions step
  uses to export a value to the steps that follow it.

  Parameters
  ----------
  versionStr : str
    The version string to save, expected to be in the format 'X.Y.Z' for
    LTS versions, 'X.Y.Z-devN' for dev versions, and 'X.Y.Z-rcN' for
    release candidate versions, where X, Y, Z and N are integers.
  envKey : str
    The name of the environment variable to export the version under, for
    example 'VERSION_INFO'.
  """
  f = None
  try:
    f = open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8')
  except Exception as exception:
    raise exception
  else:
    f.write('%s=%s\n' % (envKey, versionStr))
  finally:
    try:
      f.close()  # noqa: F821
    except AttributeError:
      pass


def main(*args: str, ) -> int:
  """
  This is the main function of the script. The first argument specifies
  the workflow, one of either: 'dev', 'rc', 'lts', 'minor' or 'major'. An
  optional second argument names an environment variable: when given, the
  resolved version is exported under that name through 'GITHUB_ENV' (the
  channel used by GitHub Actions to pass a value to later steps); when
  omitted, the version is printed to stdout so a local caller can read it
  directly. It returns 0 on success, and a non-zero integer on failure.

  Parameters
  ----------
  *args : str
    The command-line arguments passed to the script, excluding the script
    name. The first selects the workflow:
    - 'dev': The development workflow, with version strings in the format
      'X.Y.Z-devN', where X, Y, Z and N are integers. The X.Y.Z part is
      the same as the next LTS version number, and the N part is the next
      dev version number, starting from 0.
    - 'rc': The release candidate workflow, with version strings in the
      format 'X.Y.Z-rcN', where X, Y, Z and N are integers. The X.Y.Z part
      is the same as the next LTS version number, and the N part is the
      next release candidate version number, starting from 0.
    - 'lts': The long-term support workflow, with version strings in the
      format 'X.Y.Z', where X, Y and Z are integers. The X part is the
      next major
      version number, the Y part is the next minor version number, and the
      Z part is the next micro version number.
    - 'minor': The minor version update incrementing the minor version
    number, zeroing the micro number.
    - 'major': The major version update incrementing the major version
    number, zeroing the minor and micro numbers.

    An optional second argument names an environment variable. When it is
    present, the resolved version is exported under that name through
    'GITHUB_ENV'; when it is absent, the version is printed to stdout.

  Returns
  -------
  int
    0 on success, and a non-zero integer on failure. Possible failure codes:
    - 1: No arguments provided.
    - 2: More than two arguments provided.
    - 3: Unrecognized workflow argument.
    - 4: Exception raised while exporting the version string.
    - 5: A dev version was requested while a release candidate cycle is
      already underway for the current version.
  """
  if not args:
    infoSpec = """Usage: python bin/release_tooling/version_get.py [dev|rc|lts|minor|major] """
    infoSpec += """[ENV_VAR_NAME]"""
    print(infoSpec)
    return 1
  funcDict = dict(
      dev=_getDEV,
      rc=_getRC,
      lts=_getLTS,
      minor=_getMINOR,
      major=_getMAJOR,
  )
  workflow, *remainder = args
  envKey, *extra = remainder or [None]
  if extra:
    infoSpec = """Received unexpected extra arguments: %s! Expected the
    workflow and an optional environment variable name."""
    argStr = ', '.join(["'%s'" % arg for arg in extra])
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
      infoSpec = """Refusing to resolve a dev version while a release
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
  versionStr = func()
  if envKey is None:
    print(versionStr)
    return 0
  try:
    _saveVersion(versionStr, envKey)
  except Exception as exception:
    print(exception)
    return 4
  else:
    return 0


if __name__ == '__main__':
  sys.exit(main(*sys.argv[1:]))

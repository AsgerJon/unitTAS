"""
This script names the version a press of a release button publishes. It
requires one argument naming the button, which is the name of its
workflow file, one of:
- 'micro-dev', 'micro-rc', 'micro-lts'
- 'minor-dev', 'minor-rc', 'minor-lts'
- 'major-dev', 'major-rc', 'major-lts'

The name comes from the state of 'VERSION' and the release state machine
in 'release_state.py': for example '1.2.0-dev0' for the first press of
'minor-dev' after the release of 1.1.0. A press the state machine refuses
names nothing: the script prints the refusal and fails. The publish job
of every button runs this script before the build, from the branch tip,
so a press another run made obsolete since the 'safety' job is refused
here as well.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import sys
import os

import release_state


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


def _saveVersion(versionStr: str, envKey: str) -> None:
  """
  This function appends 'envKey=versionStr' to the file named by the
  'GITHUB_ENV' environment variable, the mechanism a GitHub Actions step
  uses to export a value to the steps that follow it.

  Parameters
  ----------
  versionStr : str
    The version string to save, in the format 'X.Y.Z', 'X.Y.Z-devN' or
    'X.Y.Z-rcN', where X, Y, Z and N are integers.
  envKey : str
    The name of the environment variable to export the version under, for
    example 'VERSION_INFO'.
  """
  handle = None
  try:
    handle = open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8')
  except Exception as exception:
    raise exception
  else:
    handle.write('%s=%s\n' % (envKey, versionStr))
  finally:
    if handle is not None:
      handle.close()


def main(*args: str, ) -> int:
  """
  This is the main function of the script. The first argument names the
  button. An optional second argument names an environment variable: when
  given, the version is exported under that name through 'GITHUB_ENV'
  (the channel used by GitHub Actions to pass a value to later steps);
  when omitted, the version is printed to stdout so a local caller can
  read it directly. It returns 0 on success, and a non-zero integer on
  failure.

  Parameters
  ----------
  *args : str
    The command-line arguments passed to the script, excluding the script
    name: the button, and optionally the environment variable name.

  Returns
  -------
  int
    0 on success, and a non-zero integer on failure. Possible failure codes:
    - 1: No arguments provided.
    - 2: More than two arguments provided.
    - 3: Unrecognized button.
    - 4: 'VERSION' could not be read, or the version could not be exported.
    - 5: The state machine refuses the press in the state of 'VERSION'.
  """
  if not args:
    infoSpec = """Usage: python bin/release_tooling/version_get.py BUTTON """
    infoSpec += """[ENV_VAR_NAME]"""
    print(infoSpec)
    return 1
  button, *remainder = args
  envKey, *extra = remainder or [None]
  if extra:
    infoSpec = """Received unexpected extra arguments: %s! Expected the
    button and an optional environment variable name."""
    argStr = ', '.join(["'%s'" % arg for arg in extra])
    print(str.join(' ', str.split(infoSpec % argStr)))
    return 2
  button = str.lower(str.strip(button))
  if button not in release_state.BUTTONS:
    infoSpec = """Unrecognized button: '%s'! Expected one of: %s"""
    expected = release_state.joinChoices(*release_state.BUTTONS)
    print(infoSpec % (button, expected))
    return 3
  try:
    if _badLocation():
      raise RuntimeError('Could not validate location of this script!')
    versionPath = os.path.join(_here(), 'VERSION')
    info = release_state.readVersion(versionPath)
  except Exception as exception:
    print(exception)
    return 4
  press = release_state.decide(info, button)
  if press.kind == release_state.REFUSED:
    print(press.message)
    return 5
  if envKey is None:
    print(press.name)
    return 0
  try:
    _saveVersion(press.name, envKey)
  except Exception as exception:
    print(exception)
    return 4
  else:
    return 0


if __name__ == '__main__':
  sys.exit(main(*sys.argv[1:]))

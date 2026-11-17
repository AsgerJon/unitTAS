"""
This script records a published press in the 'VERSION' file. It requires
one argument naming the button that just published, which is the name of
its workflow file, one of:
- 'micro-dev', 'micro-rc', 'micro-lts'
- 'minor-dev', 'minor-rc', 'minor-lts'
- 'major-dev', 'major-rc', 'major-lts'

The release state machine in 'release_state.py' advances the counters and
the locked level as the press requires: a dev press of the locked level
adds one to DEV, a dev press opening a cycle or climbing to a higher level
locks that level, an rc press adds one to RC, and an lts press moves the
counters to the next line and sets LEVEL back to none. A press the state
machine refuses changes nothing: the script prints the refusal and fails.
The publish job of every button runs this script only after the publish
succeeded, so a failed publish never records a version.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import sys
import os

import release_state


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


def main(*args: str, ) -> int:
  """
  This is the main function of the script. It requires exactly one
  argument naming the button that just published. It reads the 'VERSION'
  file, advances it as the state machine requires, and writes it back.
  It returns 0 on success, and a non-zero integer on failure.

  Parameters
  ----------
  *args : str
    The command-line arguments passed to the script, excluding the
    script name. Expected to contain exactly one argument naming the
    button that just published.

  Returns
  -------
  int
    0 on success, and a non-zero integer on failure. Possible failure
    codes:
    - 1: No arguments provided.
    - 2: More than one argument provided.
    - 3: Unrecognized button.
    - 4: Exception raised while reading or writing the VERSION file.
    - 5: The state machine refuses the press in the state of 'VERSION',
      which is left as it was.
  """
  if not args:
    infoSpec = """Usage: python bin/release_tooling/version_bump.py
    BUTTON"""
    print(str.join(' ', str.split(infoSpec)))
    return 1
  button, *remainder = args
  if remainder:
    infoSpec = """Received unexpected extra arguments: %s! Expected
    exactly one argument naming the button."""
    argStr = ', '.join(["'%s'" % arg for arg in remainder])
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
  try:
    info = release_state.advance(info, button)
  except release_state.ReleaseRefused as refusal:
    print(refusal)
    return 5
  try:
    release_state.writeVersion(versionPath, info)
  except Exception as exception:
    print(exception)
    return 4
  else:
    return 0


if __name__ == '__main__':
  sys.exit(main(*sys.argv[1:]))

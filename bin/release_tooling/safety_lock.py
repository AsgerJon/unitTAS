"""
This script locks every safety file beside it. The four files
'rc.safety', 'micro.safety', 'minor.safety' and 'major.safety' guard the
release workflows that publish something irreversible: a release
candidate, which closes the dev window of its version for good, and the
three official releases. A locked safety holds the sole word 'STOP'. The
author arms one by hand, replacing 'STOP' with 'ALLOW' and committing,
right before pressing the button of the workflow it guards.

Every release workflow, the dev workflow included, locks the safeties in
its first job, so no run of any workflow leaves one armed: an arming is
spent by the next press of any button, whatever that press goes on to do.
The dev workflow runs this script, since it answers to no safety. The
guarded workflows run 'safety_check.py', which reads the one safety it
answers to and then performs this same lock. The files are written whether
or not they exist, so a missing safety comes back locked.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import sys
import os

SAFETY_CHANNELS = ('rc', 'micro', 'minor', 'major',)
LOCKED = 'STOP'
ARMED = 'ALLOW'


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


def safetyPath(channel: str) -> str:
  """
  This function resolves the path of the safety file guarding 'channel',
  which sits beside this script as '<channel>.safety'.

  Parameters
  ----------
  channel : str
    One of 'rc', 'micro', 'minor' or 'major'.

  Returns
  -------
  str
    The absolute path to the safety file of the channel.
  """
  return os.path.join(_here(), '%s.safety' % channel)


def _writeText(path: str, text: str) -> None:
  """
  This function writes 'text' to the file at 'path', creating or replacing
  it.

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


def lockAll() -> list[str]:
  """
  This function writes 'STOP' as the sole content of the safety file of
  every channel, creating any that is missing.

  Returns
  -------
  list[str]
    The absolute paths of the files written, in channel order.
  """
  out = []
  for channel in SAFETY_CHANNELS:
    path = safetyPath(channel)
    _writeText(path, '%s\n' % LOCKED)
    out.append(path)
  return out


def main(*args) -> int:
  """
  This is the main function of the script. It takes no arguments, locks
  every safety and names the files written. It returns 0 on success, and a
  non-zero integer on failure.

  Parameters
  ----------
  *args
    The command-line arguments passed to the script, excluding the script
    name. None are expected.

  Returns
  -------
  int
    0 on success, and a non-zero integer on failure. Possible failure
    codes:
    - 1: Arguments were provided.
    - 3: Could not resolve the repository root.
    - 4: Exception raised while writing a safety file.
  """
  if args:
    print('Usage: python bin/release_tooling/safety_lock.py')
    return 1
  if _badLocation():
    print('Could not validate location of this script!')
    return 3
  try:
    paths = lockAll()
  except Exception as exception:
    print(exception)
    return 4
  for path in paths:
    print('Locked: %s' % os.path.basename(path))
  return 0


if __name__ == '__main__':
  sys.exit(main(*sys.argv[1:]))

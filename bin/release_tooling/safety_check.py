"""
This script decides whether a guarded release workflow may run, and locks
every safety whatever it decides. It requires one argument naming the
channel the workflow publishes, one of either:
- 'rc'
- 'micro'
- 'minor'
- 'major'
and reads the safety file of that name beside it, 'minor.safety' for
'minor'. The verdict is 'ALLOW' when that file holds the sole word
'ALLOW', which the author wrote by hand and committed before pressing the
button, and 'STOP' for any other content, or for no file at all. The
workflow checks out the commit the button was pressed on, so the state of
the file at that moment decides, and nothing pushed afterwards changes
the verdict.

Having read the file, the script writes 'STOP' into every safety file,
the one it read included, so an arming is spent by the press of the
button whether the run goes on or not. An optional second argument names
an environment variable: when given, the verdict is exported under that
name through 'GITHUB_ENV', the channel GitHub Actions uses to pass a
value to later steps, which push the lock first and act on the verdict
after; when omitted, the verdict is only printed. The script exits 0 on
either verdict, since the workflow must push the lock before it fails or
continues; a non-zero exit reports a usage or file error alone.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import sys
import os

SAFETY_CHANNELS = ('rc', 'micro', 'minor', 'major',)
LOCKED = 'STOP'
ARMED = 'ALLOW'
MISSING = '<missing>'


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


def readVerdict(channel: str) -> tuple[str, str]:
  """
  This function reads the safety file of 'channel' and decides the
  verdict: 'ALLOW' when the stripped content is exactly 'ALLOW', 'STOP'
  for anything else, a missing file included.

  Parameters
  ----------
  channel : str
    One of 'rc', 'micro', 'minor' or 'major'.

  Returns
  -------
  tuple[str, str]
    The verdict, 'ALLOW' or 'STOP', and the stripped content the file
    held, or '<missing>' when there was no file.
  """
  path = safetyPath(channel)
  if not os.path.isfile(path):
    return LOCKED, MISSING
  content = str.strip(_readText(path))
  verdict = ARMED if content == ARMED else LOCKED
  return verdict, content


def _saveVerdict(verdict: str, envKey: str) -> None:
  """
  This function appends 'envKey=verdict' to the file named by the
  'GITHUB_ENV' environment variable, the mechanism a GitHub Actions step
  uses to export a value to the steps that follow it.

  Parameters
  ----------
  verdict : str
    The verdict to export, 'ALLOW' or 'STOP'.
  envKey : str
    The name of the environment variable to export the verdict under, for
    example 'SAFETY_VERDICT'.
  """
  f = None
  try:
    f = open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8')
  except Exception as exception:
    raise exception
  else:
    f.write('%s=%s\n' % (envKey, verdict))
  finally:
    try:
      f.close()  # noqa: F821
    except AttributeError:
      pass


def main(*args) -> int:
  """
  This is the main function of the script. The first argument names the
  channel, one of 'rc', 'micro', 'minor' or 'major'. An optional second
  argument names the environment variable to export the verdict under
  through 'GITHUB_ENV'; without it the verdict is only printed. The script
  reads the safety of the channel, locks every safety, and reports what it
  found and decided. It returns 0 on either verdict, and a non-zero
  integer on failure.

  Parameters
  ----------
  *args
    The command-line arguments passed to the script, excluding the script
    name: the channel, and optionally the environment variable name.

  Returns
  -------
  int
    0 on either verdict, and a non-zero integer on failure. Possible
    failure codes:
    - 1: No arguments provided.
    - 2: More than two arguments provided.
    - 3: Unrecognized channel argument.
    - 4: Exception raised while reading or locking the safeties, or while
      exporting the verdict.
    - 5: Could not resolve the repository root.
  """
  if not args:
    infoSpec = """Usage: python bin/release_tooling/safety_check.py """
    infoSpec += """[rc|micro|minor|major] [ENV_VAR_NAME]"""
    print(infoSpec)
    return 1
  channel, *remainder = args
  envKey, *extra = remainder or [None]
  if extra:
    infoSpec = """Received unexpected extra arguments: %s! Expected the
    channel and an optional environment variable name."""
    argStr = ', '.join(["'%s'" % arg for arg in extra])
    print(str.join(' ', str.split(infoSpec % argStr)))
    return 2
  channel = str.lower(str.strip(channel))
  if channel not in SAFETY_CHANNELS:
    infoSpec = """Unrecognized channel: '%s'! Expected one of: %s"""
    print(infoSpec % (channel, 'rc, micro, minor or major'))
    return 3
  if _badLocation():
    print('Could not validate location of this script!')
    return 5
  try:
    verdict, content = readVerdict(channel)
    lockAll()
  except Exception as exception:
    print(exception)
    return 4
  print("%s.safety read '%s', verdict: %s" % (channel, content, verdict))
  print('Every safety now reads: %s' % LOCKED)
  if envKey is None:
    return 0
  try:
    _saveVerdict(verdict, envKey)
  except Exception as exception:
    print(exception)
    return 4
  print('Exported %s=%s' % (envKey, verdict))
  return 0


if __name__ == '__main__':
  sys.exit(main(*sys.argv[1:]))

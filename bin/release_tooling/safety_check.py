"""
This script decides whether a press of a release button may run, and
locks every safety whatever it decides. It requires one argument naming
the button, which is the name of its workflow file, one of:
- 'micro-dev', 'micro-rc', 'micro-lts'
- 'minor-dev', 'minor-rc', 'minor-lts'
- 'major-dev', 'major-rc', 'major-lts'

First, a press on any branch but 'main' is refused before anything is
read or written, with exit code 6, so the job stops there and pushes
nothing to that branch. GitHub Actions names the branch in 'GITHUB_REF';
outside GitHub Actions, where it is unset, the check is passed over.

The release state machine in 'release_state.py' then decides the press
from 'VERSION': refused, free, or armed. An armed press runs only when the
safety file of the button holds the sole word 'ALLOW', which the author
wrote by hand and committed before pressing the button. The workflow
checks out the commit the button was pressed on, so the state of both
files at that moment decides, and nothing pushed afterwards changes the
verdict. The verdict is 'ALLOW' for a free press and for an armed press
whose safety read 'ALLOW', 'STOP' for an armed press whose safety read
anything else or was missing, and 'REFUSED' for a refused press or a
'VERSION' that cannot be read.

Having decided, the script writes 'STOP' into all nine safety files, the
one it read included, so an arming is spent by the press of any button
whether the run goes on or not. An optional second argument names an
environment variable: when given, the verdict is exported under that
name, and the message explaining it under that name followed by
'_MESSAGE', through 'GITHUB_ENV', the channel GitHub Actions uses to
pass a value to later steps, which push the lock first and act on the
verdict after; when omitted, the verdict is only printed. The script
exits 0 on every verdict, since the workflow must push the lock before it
fails or continues; a non-zero exit reports a usage or file error, or a
press on another branch.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import sys
import os

import release_state

LOCKED = 'STOP'
ARMED = 'ALLOW'
REFUSED = 'REFUSED'
MISSING = '<missing>'
MAIN_REF = 'refs/heads/main'
BRANCH_PREFIX = 'refs/heads/'


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


def safetyPath(name: str) -> str:
  """
  This function resolves the path of the safety file of the stem 'name',
  which sits beside this script as '<name>.safety'.

  Parameters
  ----------
  name : str
    One of 'release_state.SAFETY_NAMES', as 'minor-dev'.

  Returns
  -------
  str
    The absolute path to the safety file.
  """
  return os.path.join(_here(), '%s.safety' % name)


def _readText(path: str) -> str:
  """
  This function reads and returns the full text of the file at 'path'.
  """
  handle = None
  try:
    handle = open(path, 'r', encoding='utf-8')
  except Exception as exception:
    raise exception
  else:
    return handle.read()
  finally:
    if handle is not None:
      handle.close()


def _writeText(path: str, text: str) -> None:
  """
  This function writes 'text' to the file at 'path', creating or replacing
  it.
  """
  handle = None
  try:
    handle = open(path, 'w', encoding='utf-8')
  except Exception as exception:
    raise exception
  else:
    handle.write(text)
  finally:
    if handle is not None:
      handle.close()


def lockAll() -> list[str]:
  """
  This function writes 'STOP' as the sole content of the safety file of
  every button, creating any that is missing.

  Returns
  -------
  list[str]
    The absolute paths of the files written, in the order of the buttons.
  """
  out = []
  for name in release_state.SAFETY_NAMES:
    path = safetyPath(name)
    _writeText(path, '%s\n' % LOCKED)
    out.append(path)
  return out


def readVerdict(name: str) -> tuple[str, str]:
  """
  This function reads the safety file of the stem 'name' and decides the
  verdict: 'ALLOW' when the stripped content is exactly 'ALLOW', 'STOP'
  for anything else, a missing file included.

  Returns
  -------
  tuple[str, str]
    The verdict, 'ALLOW' or 'STOP', and the stripped content the file
    held, or '<missing>' when there was no file.
  """
  path = safetyPath(name)
  if not os.path.isfile(path):
    return LOCKED, MISSING
  content = str.strip(_readText(path))
  verdict = ARMED if content == ARMED else LOCKED
  return verdict, content


def _otherBranch(button: str) -> str:
  """
  This function returns the refusal of a press on any branch but 'main',
  or an empty string when the press may go on: on 'main', and outside
  GitHub Actions, where 'GITHUB_REF' is unset.
  """
  if 'GITHUB_REF' not in os.environ:
    return ''
  ref = os.environ['GITHUB_REF']
  if ref == MAIN_REF:
    return ''
  if str.startswith(ref, BRANCH_PREFIX):
    ref = ref[len(BRANCH_PREFIX):]
  infoSpec = """The release buttons run from 'main' alone, but '%s' was
  pressed on '%s'. Nothing was locked, tested or published."""
  return str.join(' ', str.split(infoSpec % (button, ref)))


def _decide(button: str) -> tuple:
  """
  This function decides the press from 'VERSION' and the safety of the
  button, and returns the verdict, the message explaining it, and the
  line naming what the safety read, empty when no safety was read.
  """
  try:
    if _badLocation():
      raise RuntimeError('Could not validate location of this script!')
    versionPath = os.path.join(_here(), 'VERSION')
    press = release_state.decide(release_state.readVersion(versionPath),
                                 button)
  except Exception as exception:
    infoSpec = """'%s' is refused, since VERSION cannot be read: %s"""
    return REFUSED, infoSpec % (button, exception), ''
  if press.kind == release_state.REFUSED:
    return REFUSED, press.message, ''
  if press.kind == release_state.FREE:
    return ARMED, press.message, ''
  verdict, content = readVerdict(press.safety)
  read = "%s.safety read '%s', verdict: %s" % (press.safety, content,
                                                verdict)
  if verdict == ARMED:
    return verdict, "%s It read 'ALLOW'." % press.message, read
  infoSpec = """'%s' would publish %s but needs %s.safety to read 'ALLOW'
  in the commit it was pressed on, and it read '%s'."""
  info = infoSpec % (button, press.name, press.safety, content)
  return verdict, str.join(' ', str.split(info)), read


def _saveVerdict(envKey: str, verdict: str, message: str) -> None:
  """
  This function appends 'envKey=verdict' and 'envKey_MESSAGE=message' to
  the file named by the 'GITHUB_ENV' environment variable, the mechanism
  a GitHub Actions step uses to export a value to the steps that follow.
  """
  handle = None
  try:
    handle = open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8')
  except Exception as exception:
    raise exception
  else:
    handle.write('%s=%s\n' % (envKey, verdict))
    handle.write('%s_MESSAGE=%s\n' % (envKey, message))
  finally:
    if handle is not None:
      handle.close()


def main(*args) -> int:
  """
  This is the main function of the script. The first argument names the
  button. An optional second argument names the environment variable to
  export the verdict under through 'GITHUB_ENV'; without it the verdict is
  only printed. It returns 0 on every verdict, and a non-zero integer on
  failure.

  Parameters
  ----------
  *args
    The command-line arguments passed to the script, excluding the script
    name: the button, and optionally the environment variable name.

  Returns
  -------
  int
    0 on every verdict, and a non-zero integer on failure. Possible
    failure codes:
    - 1: No arguments provided.
    - 2: More than two arguments provided.
    - 3: Unrecognized button.
    - 4: Exception raised while locking the safeties, or while exporting
      the verdict.
    - 5: Could not resolve the repository root.
    - 6: The button was pressed on a branch other than 'main'; nothing was
      read or written.
  """
  if not args:
    infoSpec = """Usage: python bin/release_tooling/safety_check.py """
    infoSpec += """BUTTON [ENV_VAR_NAME]"""
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
  refusal = _otherBranch(button)
  if refusal:
    print(refusal)
    return 6
  try:
    if _badLocation():
      print('Could not validate location of this script!')
      return 5
  except RuntimeError as runtimeError:
    print(runtimeError)
    return 5
  verdict, message, read = _decide(button)
  try:
    lockAll()
  except Exception as exception:
    print(exception)
    return 4
  print(message)
  if read:
    print(read)
  print('Verdict: %s' % verdict)
  print('Every safety now reads: %s' % LOCKED)
  if envKey is None:
    return 0
  try:
    _saveVerdict(envKey, verdict, message)
  except Exception as exception:
    print(exception)
    return 4
  print('Exported %s=%s' % (envKey, verdict))
  return 0


if __name__ == '__main__':
  sys.exit(main(*sys.argv[1:]))

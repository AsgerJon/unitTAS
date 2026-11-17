"""
ReleaseToolingTest is the base of the tests of the release tooling.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

#  The folder of the release tooling, where 'release_state' is imported
#  from, whichever folder the tests are started in.
TOOLING = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLING not in sys.path:
  sys.path.insert(0, TOOLING)
#  The 'VERSION' of the repository, which a test may read and never write.
TOOLING_VERSION = os.path.join(TOOLING, 'VERSION')

import release_state  # noqa: E402

SCRIPTS = (
  'release_state.py',
  'version_get.py',
  'version_bump.py',
  'safety_check.py',
  'safety_lock.py',
)

#  The safety file each button reads, written out here rather than taken
#  from 'release_state', so the tests state the design independently:
#  every button reads the safety of its own name.
SAFETY = {
  'micro-dev': 'micro-dev',
  'micro-rc': 'micro-rc',
  'micro-lts': 'micro-lts',
  'minor-dev': 'minor-dev',
  'minor-rc': 'minor-rc',
  'minor-lts': 'minor-lts',
  'major-dev': 'major-dev',
  'major-rc': 'major-rc',
  'major-lts': 'major-lts',
}

#  The counters after the 1.1.0 release, from which every state of the
#  tests is counted: micro targets 1.1.1, minor 1.2.0 and major 2.0.0.
BASE = dict(major=1, minor=1, micro=1)


class ReleaseToolingTest(unittest.TestCase):
  """
  Every test of the release tooling must work on copies, never on the
  'VERSION' file, the safety files or the scripts of the repository: a
  test that wrote the real 'VERSION' would change the next name a button
  publishes. A test of the state machine itself must also be able to say
  what each press does without trusting the code it tests.

  Implementation
  --------------

  'setUp' builds a temporary folder laid out as the repository is, with
  'settings.gradle', 'gradle.properties', 'README.md', 'src' and copies of
  the scripts under 'bin/release_tooling', and 'tearDown' removes it. 'writeVersion'
  and 'readCounters' write and read that copy of 'VERSION', the latter
  with a parser of its own. 'runScript' starts a copied script as the
  workflows start it, with 'GITHUB_ENV' pointing at a file of the test
  and 'GITHUB_REF' naming 'main' unless told otherwise. 'assertPresses'
  checks one state against a table of every button.
  """

  def setUp(self) -> None:
    self.tempFolder = tempfile.mkdtemp(prefix='release_tooling_')
    self.root = os.path.join(self.tempFolder, 'repository')
    self.tooling = os.path.join(self.root, 'bin', 'release_tooling')
    os.makedirs(self.tooling)
    os.makedirs(os.path.join(self.root, 'src'))
    self.writeText(os.path.join(self.root, 'settings.gradle'), '')
    self.writeText(os.path.join(self.root, 'gradle.properties'), '')
    self.writeText(os.path.join(self.root, 'README.md'), '')
    for script in SCRIPTS:
      shutil.copy(os.path.join(TOOLING, script), self.tooling)
    self.envPath = os.path.join(self.tempFolder, 'github_env')
    for button in release_state.BUTTONS:
      self.writeSafety(SAFETY[button], 'STOP\n')
    self.writeVersion()

  def tearDown(self) -> None:
    shutil.rmtree(self.tempFolder)

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  FILES  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  @staticmethod
  def writeText(path: str, text: str) -> None:
    handle = None
    try:
      handle = open(path, 'w', encoding='utf-8')
    except OSError as osError:
      raise osError
    else:
      handle.write(text)
    finally:
      if handle is not None:
        handle.close()

  @staticmethod
  def readText(path: str) -> str:
    handle = None
    try:
      handle = open(path, 'r', encoding='utf-8')
    except OSError as osError:
      raise osError
    else:
      return handle.read()
    finally:
      if handle is not None:
        handle.close()

  @property
  def versionPath(self) -> str:
    return os.path.join(self.tooling, 'VERSION')

  def writeVersion(self, level: str = 'none', rc: int = 0, dev: int = 0,
                   **counters: int) -> None:
    values = dict(BASE)
    values.update(counters)
    lines = [
      '#  A copy of VERSION, written by a test.',
      'MAJOR=%d' % values['major'],
      'MINOR=%d' % values['minor'],
      'MICRO=%d' % values['micro'],
      'RC=%d' % rc,
      'DEV=%d' % dev,
      'LEVEL=%s' % level,
      '',
    ]
    self.writeText(self.versionPath, str.join('\n', lines))

  def readCounters(self) -> dict:
    out = dict()
    for line in str.split(self.readText(self.versionPath), '\n'):
      line = str.strip(line)
      if not line or str.startswith(line, '#'):
        continue
      key, value = str.split(line, '=')
      key = str.lower(key)
      out[key] = value if key == 'level' else int(value)
    return out

  def safetyPath(self, name: str) -> str:
    return os.path.join(self.tooling, '%s.safety' % name)

  def writeSafety(self, name: str, text: str) -> None:
    self.writeText(self.safetyPath(name), text)

  def readSafety(self, name: str) -> str:
    return str.strip(self.readText(self.safetyPath(name)))

  def readEnv(self) -> dict:
    out = dict()
    if not os.path.isfile(self.envPath):
      return out
    for line in str.split(self.readText(self.envPath), '\n'):
      if not line:
        continue
      key, value = str.split(line, '=', 1)
      out[key] = value
    return out

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  SCRIPTS  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  def runScript(self, script: str, *args: str, **kwargs) -> tuple:
    """
    Runs a copied script with the interpreter running the tests, and
    returns its exit code and its output, the error output included.
    The keyword 'ref' sets 'GITHUB_REF', 'refs/heads/main' by default;
    'None' leaves it unset, as a run outside GitHub Actions has it. The
    interpreter starts with '-S', without the 'site' module: the scripts
    use the standard library alone, and a 'sitecustomize.py' printing at
    every start, as one local 3.7 environment has, would reach the output.
    """
    if os.path.isfile(self.envPath):
      os.remove(self.envPath)
    env = dict(os.environ)
    env['GITHUB_ENV'] = self.envPath
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    ref = kwargs['ref'] if 'ref' in kwargs else 'refs/heads/main'
    for key in ('GITHUB_REF', 'GITHUB_REF_NAME'):
      if key in env:
        del env[key]
    if ref is not None:
      env['GITHUB_REF'] = ref
    command = [sys.executable, '-B', '-S',
               os.path.join(self.tooling, script)]
    result = subprocess.run(
        [*command, *args],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    return result.returncode, result.stdout

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  STATES  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  @staticmethod
  def info(level: str = 'none', rc: int = 0, dev: int = 0, **counters: int
           ) -> dict:
    out = dict(BASE)
    out.update(counters)
    out.update(rc=rc, dev=dev, level=level)
    return out

  def assertPresses(self, info: dict, table: dict) -> None:
    """
    Checks a press of every button in the state 'info' against 'table',
    which maps each of the nine buttons to one of:

      ('armed', name, changes)   the press needs its safety
      ('free', name, changes)    the press needs no safety
      ('refused', accepted)      the press is refused

    'name' is the version the press publishes, 'changes' the counters and
    LEVEL that differ after it, and 'accepted' the buttons the refusal
    names as accepted in this state.
    """
    self.assertEqual(sorted(table), sorted(release_state.BUTTONS))
    for button in release_state.BUTTONS:
      expected = table[button]
      with self.subTest(button=button):
        before = dict(info)
        press = release_state.decide(info, button)
        self.assertEqual(info, before)
        self.assertEqual(press.button, button)
        self.assertEqual(press.kind, expected[0])
        if expected[0] == 'refused':
          self.assertIsNone(press.name)
          self.assertIsNone(press.safety)
          self.assertEqual(press.accepted, expected[1])
          self.assertTrue(
              str.startswith(press.message, "'%s' is refused. " % button))
          with self.assertRaises(release_state.ReleaseRefused) as context:
            release_state.advance(info, button)
          self.assertEqual(str(context.exception), press.message)
          self.assertEqual(info, before)
          continue
        self.assertEqual(press.name, expected[1])
        if expected[0] == 'armed':
          self.assertEqual(press.safety, SAFETY[button])
        else:
          self.assertIsNone(press.safety)
        after = release_state.advance(info, button)
        self.assertEqual(info, before)
        self.assertEqual(after, dict(before, **expected[2]))

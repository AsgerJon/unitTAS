"""
Step 8a of phase 3 (SPEC.md section 9.3), on the run's port (19.7 step 9c): the 'unittas' command, run as a user runs
it ('python -m unittas', a process of its own), from an instance spec: 1.7.10's on unitTAS's development client
(client = "gradle"); every other port's on a real client of its version, the agent its probe (ports.agentSpec).
- run: step 7's suites (green, red and one that isn't there), its report checked by bin/self_red_check.py --python,
  each test's line shown as it ended;
- launch --world: up in the test world, then Ctrl+C: the game gone, and the game folder's own options.txt back.

  python -m unittas.selftest test_command.      (through the watcher: "probe test_command.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import unittest

from ports import V1_7_10, agentSpec, specLoader, version
from probegame import GONE_SECONDS, READY_SECONDS, ROOT, results
from unittas.release import gameJvms

#  1.7.10's development client's game folder
GAME = os.path.join(ROOT, 'run', 'client')


def _defaultCtrlC() -> None:
  """In the command's process: Ctrl+C as Python has it by default, whatever this process was started with."""
  signal.signal(signal.SIGINT, signal.SIG_DFL)


class CommandTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    folder = os.path.join(results(), 'specs')
    os.makedirs(folder, exist_ok=True)
    cls.spec = os.path.join(folder, 'command.toml')
    if version() == V1_7_10:
      cls.game = GAME
      with open(cls.spec, 'w', encoding='utf-8') as file:
        file.write('minecraft = "1.7.10"\nloader = { forge = "10.13.4.1614" }\nclient = "gradle"\n[gradle]\n'
                   'project = "%s"\ntask = "runClient"\ngame = "%s"\n' % (ROOT, GAME))
    else:
      cls.game = os.path.join(ROOT, 'run', '%s-%s-command' % (specLoader()[0], version()))
      agentSpec(cls.spec, cls.game)
    # unitTAS's own Gradle cache, as ./unittas.sh gives its Gradle (a mod's project would use its own)
    cls.environment = dict(os.environ, GRADLE_USER_HOME=os.path.join(ROOT, '.gradle-home'))

  def command(self, *args: str, **options) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, '-m', 'unittas'] + list(args), cwd=os.path.join(ROOT, 'python', 'tests'),
                            env=self.environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, **options)

  def test_1_run(self) -> None:
    folder = os.path.join(results(), 'command-run')
    process = self.command('run', 'selfsuite.green', 'selfsuite.red', 'selfsuite.nosuch', '--instance', self.spec,
                           '--results', folder)
    said, _ = process.communicate(timeout=READY_SECONDS + 900)
    with open(os.path.join(folder, 'said.txt'), 'w', encoding='utf-8') as file:
      file.write(said)
    # the red suite fails on purpose: FAILED, exit 1, and the checker says whether it failed as it should
    self.assertEqual(1, process.returncode, said)
    report = os.path.join(folder, 'report.txt')
    self.assertIn('report: %s' % report, said)
    self.assertIn('ChatTests.testTypedTextIsRead ... ok', said, "each test's line shown as it ended")
    checked = subprocess.run([sys.executable, '-I', os.path.join(ROOT, 'bin', 'self_red_check.py'), '--python',
                              '--game', self.game, report], capture_output=True, text=True)
    self.assertEqual(0, checked.returncode, checked.stdout + checked.stderr)

  def test_2_launch_until_ctrl_c(self) -> None:
    options = os.path.join(self.game, 'options.txt')
    before = open(options, encoding='utf-8').read() if os.path.isfile(options) else None
    folder = os.path.join(results(), 'command-launch')
    process = self.command('launch', '--world', '--instance', self.spec, '--results', folder,
                           preexec_fn=_defaultCtrlC)
    said = []
    try:
      deadline = time.monotonic() + READY_SECONDS
      while time.monotonic() < deadline:
        line = process.stdout.readline()
        if not line:
          break
        said.append(line)
        if line.startswith('the game is up in the test world'):
          break
      self.assertTrue(said and said[-1].startswith('the game is up in the test world'), ''.join(said))
      self.assertIn('for looking at', said[0])
      self.assertTrue(gameJvms(self.game), 'no game running in %s' % self.game)
      process.send_signal(signal.SIGINT)
      rest, _ = process.communicate(timeout=GONE_SECONDS)
      said.append(rest)
    finally:
      if process.poll() is None:
        process.kill()
        process.wait(30)
    self.assertEqual(0, process.returncode, ''.join(said))
    self.assertIn('Ctrl+C: the game is asked to quit', ''.join(said))
    self.assertEqual([], gameJvms(self.game), 'the game is still running')
    after = open(options, encoding='utf-8').read() if os.path.isfile(options) else None
    self.assertEqual(before, after, "the game folder's own options.txt isn't back")


if __name__ == '__main__':
  unittest.main()

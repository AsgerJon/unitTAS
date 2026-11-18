"""
A launched game's wait for its hello never hangs (Asger, 2026-11-17: "if
you open a game, it must never hang"; unittas.game.LaunchedGame.accept),
with commands that are no game, each acting one way a game can:
- one whose probe dialled (its line in the output) but never said hello
  fails once HELLO_AFTER_DIAL has passed, not at the run's limit;
- one whose agent woke but whose game still loads (its loader, its mods,
  Minecraft's start: its output growing) is waited for, past that limit:
  the probe dials only once Minecraft is launched (a Fabric game's start
  took over 30 s, 2026-11-18);
- one that says nothing at all fails once its quiet limit has passed;
- one that keeps saying what it does (a launcher fetching, an installer
  installing) is waited for as long as it does, past the quiet limit;
  when it then ends, that is said (LinkClosed), not taken for a timeout;
- a game that ends before its hello is said at once, its exit code named;
- one whose launcher couldn't start it (its reason left in the results,
  unittas.launcher.FAILED) is that reason, one error, no exit code: a
  launch in the test display ends with gamescope's, 0, whatever the
  launcher's; a reason an earlier launch left isn't taken for this one's.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

from unittas import game
from unittas.errors import LinkClosed, LinkTimeout
from unittas.game import LaunchedGame
from unittas.launcher import FAILED

#  each 'game', a Python script: what it prints, how it waits
DIALLED_AND_SILENT = (
  "import sys, time\n"
  "print('[unitTAS] the probe wakes: 19 hooks', file=sys.stderr, "
  "flush=True)\n"
  "print('[main/INFO]: unitTAS probe: dialling 127.0.0.1:5000 as game "
  "(client)', flush=True)\n"
  "time.sleep(60)\n")
WOKE_AND_LOADING = (
  "import sys, time\n"
  "print('[unitTAS] the probe wakes: 19 hooks', file=sys.stderr, "
  "flush=True)\n"
  "for each in range(10):\n"
  "  print('[main/INFO]: loading, step %d' % each, flush=True)\n"
  "  time.sleep(0.5)\n")
SILENT = "import time\ntime.sleep(60)\n"
BUSY = (
  "import time\n"
  "for each in range(8):\n"
  "  print('unitTAS launcher: fetched asset %d' % each, flush=True)\n"
  "  time.sleep(0.5)\n")
ENDS = "import sys\nsys.exit(70)\n"
#  the launcher's refusal, ended by the display as gamescope does: 0
REFUSED = (
  "import os\n"
  "with open(os.path.join(os.environ['UNITTAS_RESULTS'], %r), 'w') as f:\n"
  "  f.write(\"Forge 47.4.28's installer refused the jars it made\")\n"
  % FAILED)


class ScriptGame(LaunchedGame):
  """A 'game' that is a Python script, its output in output.log."""

  def __init__(self, root: str, results: str, script: str) -> None:
    LaunchedGame.__init__(self, root, results, 'script')
    self.script = script

  def gameFolder(self) -> str:
    return os.path.join(self.root(), 'game')

  def command(self) -> list:
    return [sys.executable, '-c', self.script]

  def outputName(self) -> str:
    return 'output.log'


class HelloWaitTests(unittest.TestCase):

  def setUp(self) -> None:
    self.folder = tempfile.mkdtemp(prefix='unittas-hellowait-')
    self.addCleanup(shutil.rmtree, self.folder, True)

  def started(self, script: str, seconds: float) -> tuple:
    """The game started, and what its start raised, and how long it took."""
    launched = ScriptGame(self.folder, os.path.join(self.folder, 'results'),
                          script)
    began = time.monotonic()
    with self.assertRaises((LinkTimeout, LinkClosed)) as raised:
      launched.start(seconds)
    return raised.exception, time.monotonic() - began, launched

  def test_dialled_but_never_said_hello(self) -> None:
    with mock.patch.object(game, 'HELLO_AFTER_DIAL', 2.0):
      raised, took, launched = self.started(DIALLED_AND_SILENT, 60)
    self.assertIsInstance(raised, LinkTimeout)
    self.assertIn('dialled', str(raised))
    self.assertLess(took, 10, 'within HELLO_AFTER_DIAL, not the 60 s')
    self.assertIsNotNone(launched.process().poll(), 'and stopped')

  def test_woke_and_still_loading_is_waited_for(self) -> None:
    with mock.patch.object(game, 'HELLO_AFTER_DIAL', 2.0):
      raised, took, _ = self.started(WOKE_AND_LOADING, 3)
    self.assertIsInstance(raised, LinkClosed, 'it ended, not timed out')
    self.assertGreater(took, 4, 'waited past HELLO_AFTER_DIAL as it loaded')

  def test_silent(self) -> None:
    raised, took, launched = self.started(SILENT, 2)
    self.assertIsInstance(raised, LinkTimeout)
    self.assertIn('nothing new', str(raised))
    self.assertLess(took, 10)
    self.assertIsNotNone(launched.process().poll(), 'and stopped')

  def test_busy_is_waited_for(self) -> None:
    raised, took, _ = self.started(BUSY, 2)
    self.assertIsInstance(raised, LinkClosed, 'it ended, not timed out')
    self.assertGreater(took, 3, 'waited past the quiet limit as it worked')

  def test_an_end_before_the_hello_is_said_at_once(self) -> None:
    raised, took, _ = self.started(ENDS, 60)
    self.assertIsInstance(raised, LinkClosed)
    self.assertIn('exit 70', str(raised))
    self.assertLess(took, 10)

  def test_the_launcher_s_reason_is_the_error(self) -> None:
    raised, took, _ = self.started(REFUSED, 60)
    self.assertIsInstance(raised, LinkClosed)
    self.assertIn("Forge 47.4.28's installer refused the jars it made",
                  str(raised))
    self.assertNotIn('exit 0', str(raised), "gamescope's, not the reason")
    self.assertTrue(raised.__suppress_context__, 'one error, no chain')
    self.assertLess(took, 10)

  def test_an_earlier_launch_s_reason_isn_t_this_one_s(self) -> None:
    results = os.path.join(self.folder, 'results')
    os.makedirs(results)
    with open(os.path.join(results, FAILED), 'w') as file:
      file.write('an earlier launch could not start')
    raised, _, _ = self.started(ENDS, 60)
    self.assertIn('exit 70', str(raised))
    self.assertNotIn('earlier', str(raised))



if __name__ == '__main__':
  unittest.main()

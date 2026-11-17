"""
A game the agent's probe can't be loaded in ends (SPEC.md 19.7; Asger,
2026-11-17: "if unittas opens a game, unittas closes it", "it must never
hang"). unitTAS opens the game for a run, and a game no probe drives is no
test: the agent says why on the error stream and ends the JVM at once, by
its own exit code, so the orchestrator sees the game gone within seconds
rather than waiting for a hello that never comes. Without a game: a small
one of its own (its main calls one hooked method, then would go on), the
agent's real bootstrap and a probe whose start throws, packed as
bin/build_agent.py packs a version's, run on the newest Java installed.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

BIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BIN)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_agent  # noqa: E402
from test_agent_wrap import JAVAS, java, javac  # noqa: E402

#  the agent's exit code for a game its probe can't be loaded in (Bridge)
NO_PROBE = 70
#  the orchestrator's start file, without which the agent stays asleep
START_FILE = os.path.join('unittas', 'probe.properties')

GAME = '''package noprobe;

public final class Game {
\tpublic static void main(String[] args) {
\t\tnew Game().run();
\t\tSystem.out.println("the game ran on without its probe");
\t}

\tpublic void run() {
\t}
}
'''
PROBE = '''package noprobe;

public final class BrokenProbe {
\tpublic static Object start(java.io.File game, Object pass, java.util.Set<?> hooked,
\t\tjava.util.Set<?> rewritten, java.util.function.Function<?, ?> names) {
\t\tthrow new IllegalStateException("broken on purpose");
\t}
}
'''
HOOKS = (b'entry\tnoprobe.BrokenProbe\n'
         b'BEFORE\tnoprobe/Game\trun\t()V\tminecraft.made\n')


class NoProbeTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    homes = {major: java(major) for major in JAVAS}
    homes = {major: home for major, home in homes.items() if home}
    compiler = javac(homes)
    if compiler is None:
      raise unittest.SkipTest('no javac from 17 on is installed')
    cls.java = os.path.join(homes[max(homes)], 'bin', 'java')
    cls.folder = tempfile.mkdtemp(prefix='unittas-noprobe-')
    sources = os.path.join(cls.folder, 'src', 'noprobe')
    os.makedirs(sources)
    for name, text in (('Game.java', GAME), ('BrokenProbe.java', PROBE)):
      with open(os.path.join(sources, name), 'w', encoding='utf-8') as file:
        file.write(text)
    bootstrap = os.path.join(cls.folder, 'bootstrap')
    build_agent.compileBootstrap(compiler, bootstrap)
    cls.game = os.path.join(cls.folder, 'game')
    build_agent._compile(compiler, [], [os.path.join(sources, 'Game.java')],
                         cls.game, '17')
    probe = os.path.join(cls.folder, 'probe')
    build_agent._compile(compiler, [],
                         [os.path.join(sources, 'BrokenProbe.java')], probe,
                         '17')
    cls.agent = build_agent.assemble(bootstrap, probe, '0',
                                     os.path.join(cls.folder, 'agent.jar'),
                                     HOOKS, 'test')

  @classmethod
  def tearDownClass(cls) -> None:
    shutil.rmtree(cls.folder, ignore_errors=True)

  def test_the_game_ends_saying_why(self) -> None:
    folder = os.path.join(self.folder, 'run')
    os.makedirs(os.path.join(folder, 'unittas'), exist_ok=True)
    with open(os.path.join(folder, START_FILE), 'w', encoding='utf-8') as file:
      file.write('port=1\n')
    began = time.monotonic()
    done = subprocess.run(
      [self.java, '-javaagent:%s=%s' % (self.agent, folder), '-cp', self.game,
       'noprobe.Game'], stdin=subprocess.DEVNULL, capture_output=True,
      text=True, timeout=60)
    self.assertEqual(NO_PROBE, done.returncode, done.stdout + done.stderr)
    self.assertIn("[unitTAS] the probe couldn't be loaded, so the game ends",
                  done.stderr)
    self.assertIn('broken on purpose', done.stderr)
    self.assertNotIn('the game ran on', done.stdout,
                     'ended at the hook, before the game went on')
    self.assertLess(time.monotonic() - began, 30, 'at once')


if __name__ == '__main__':
  unittest.main()

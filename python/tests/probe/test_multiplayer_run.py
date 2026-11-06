"""
Phase 3b step 5 (SPEC.md section 11.3): a run with multiplayer classes, as a user runs one ('python -m unittas run
--multiplayer'), on a real client from an instance spec: the release jar beside UniMixins, its [server] the EULA on
Asger's standing yes and 1G. selfsuite.multiplayer's four classes, in order:
- the first multiplayer class: the run's own client leaves its world, the server and bob start, both join;
- a fresh world for the next: a restart, a new server's world (what the first placed is gone);
- a shared one: the world as the one before it left it;
- a singleplayer class after them: the run's own client in its own world again.
The report has every test ok and a world line for each; the server and bob are gone after.
Three games at once (about 5 GB): asked for before it is run.

  python -m unittas.selftest test_multiplayer_run.      (through the watcher: "probe test_multiplayer_run.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest

from probegame import READY_SECONDS, ROOT, results
from unittas.release import releaseJar


class MultiplayerRunTests(unittest.TestCase):

  def test_1_a_run_with_its_multiplayer_classes(self) -> None:
    if not os.path.isfile(os.path.join(ROOT, 'asger_accepts_all_eulas.txt')):
      self.skipTest("a dedicated server needs Mojang's EULA accepted: this runs on Asger's standing yes only")
    folder = os.path.join(results(), 'mp-run')
    os.makedirs(folder, exist_ok=True)
    jar = releaseJar(ROOT, os.path.join(folder, 'build.log'))
    mixins = os.path.join(ROOT, 'run', 'oldsaves', 'mods', 'unimixins-1.7.10-0.3.1.jar')
    game = os.path.join(results(), 'mp-client')
    shutil.rmtree(game, ignore_errors=True)
    spec = os.path.join(folder, 'multiplayer.toml')
    with open(spec, 'w', encoding='utf-8') as file:
      file.write('minecraft = "1.7.10"\nloader = { forge = "10.13.4.1614" }\nclient = "real"\nmods = ["%s"]\n'
                 'libraries = ["%s"]\nprobe = "%s"\ngame = "%s"\n[server]\neula = true\nmemory = "1G"\n'
                 % (jar, mixins, jar, game))
    run = os.path.join(folder, 'run')
    environment = dict(os.environ, GRADLE_USER_HOME=os.path.join(ROOT, '.gradle-home'))
    process = subprocess.run([sys.executable, '-m', 'unittas', 'run', 'selfsuite.multiplayer', '--multiplayer',
                              '--instance', spec, '--results', run], cwd=os.path.join(ROOT, 'python', 'tests'),
                             env=environment, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                             timeout=READY_SECONDS * 3 + 900)
    said = process.stdout + process.stderr
    with open(os.path.join(folder, 'said.txt'), 'w', encoding='utf-8') as file:
      file.write(said)
    with open(os.path.join(run, 'report.txt'), encoding='utf-8') as file:
      report = file.read()
    self.assertEqual(0, process.returncode, report)
    for line in ('AServerTests.test_a_both_in ... ok', 'AServerTests.test_b_a_block_bob_sees ... ok',
                 'AServerTests.test_c_both_at_the_start ... ok', 'AServerTests.test_d_alices_chat_reaches_bob ... ok',
                 'BFreshTests.test_a_what_a_placed_is_gone ... ok',
                 'BFreshTests.test_b_leaves_wool ... ok', 'CSharedTests.test_a_the_wool_b_left ... ok',
                 'DSingleTests.test_a_its_own_world_again ... ok'):
      self.assertIn(line, report)
    for world in ("world 2: the server's, fresh for AServerTests", "world 3: the server's, fresh for BFreshTests",
                  'world 3, shared: CSharedTests runs in it as BFreshTests left it', 'world 4: fresh for DSingleTests'):
      self.assertIn(world, report)
    left = subprocess.run(['pgrep', '-f', 'ServerLaunchWrapper|client-bob-game'], capture_output=True, text=True)
    self.assertEqual('', left.stdout.strip(), 'a game of the run left running')


if __name__ == '__main__':
  unittest.main()

"""
The loader-free probe (SPEC.md 19.7 step 5a): unitTAS's probe for 26.3 as a Java agent in vanilla 26.3, no loader
and no library, from unitTAS's own launcher (bin/launch_client.py --minecraft 26.3 --agent JAR). It wakes at the
game's first hook, loaded under the game's own class loader; its hello says what runs (the port 26.3, Minecraft
26.3, no loader, Mojang's names, the probe's version from its own jar); ready once loaded, every hooked class
rewritten; its window's behaviours (PROTOCOL.md 2.5); a world made and a block set and read in it; asked to quit, it
does.

  python -m unittas.selftest test_agent.      (through the watcher: "probe test_agent.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from agentgame import HOOKED, MINECRAFT, AgentGame, buildAgent
from probegame import GONE_SECONDS, READY_SECONDS, modVersion, results
from unittas.reset import reset

TITLE = 'net.minecraft.client.gui.screens.TitleScreen'


class AgentTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    jar = buildAgent(os.path.join(results(), 'agent-build', 'build.log'))
    cls.game = AgentGame(results(), jar)
    shutil.rmtree(os.path.join(cls.game.gameDir, 'saves', 'unittas'), ignore_errors=True)
    cls.connection = cls.game.start(READY_SECONDS)
    cls.ready = cls.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop(30)

  def test_1_its_hello_says_what_runs(self) -> None:
    hello = self.connection.hello
    self.assertEqual('26.3', hello.probePort)
    self.assertEqual(MINECRAFT, hello.minecraft)
    self.assertEqual(('', ''), (hello.loaderName, hello.loaderVersion), 'vanilla: no loader')
    self.assertEqual('mojang', hello.names, '26.x is unobfuscated: no mappings')
    self.assertFalse(hello.development)
    self.assertEqual(modVersion(), hello.probeVersion, "the probe's version from its own jar's manifest")
    self.assertTrue(hello.javaVersion.startswith('25'), hello.javaVersion)

  def test_2_ready_with_every_hook(self) -> None:
    self.assertEqual(TITLE, self.ready['screen'])
    self.assertEqual([], self.ready['mods'], 'vanilla: no mods, no loader to list them')
    self.assertEqual(HOOKED, self.ready['mixins']['applied'], 'each hooked class rewritten as it loaded')
    self.assertEqual([], self.ready['mixins']['missing'])
    self.assertEqual('unitTAS', self.ready['window']['title'], "the window's behaviours (PROTOCOL.md 2.5)")

  def test_3_status_and_the_pointer(self) -> None:
    status = self.connection.request('status')
    self.assertEqual('menu', status['state'])
    self.assertEqual('unitTAS', status['window']['title'])
    self.assertFalse(status['window']['pointer_grabbed'])
    self.assertGreaterEqual(status['ticks']['client'], 1)

  def test_4_a_world_and_a_block(self) -> None:
    self.connection.request('world.create', {}, timeout=240)
    self.connection.request('world.prepare')
    reset(self.connection, at=(0.5, -60.0, 0.5))
    self.connection.request('block.set', {'pos': [2, -60, 2], 'block': {'id': 'minecraft:red_wool'}})
    held = self.connection.request('wait.until', {'side': 'client', 'op': 'block.get', 'args': {'pos': [2, -60, 2]},
                                                  'max_ticks': 40, 'test': {'path': ['id'], 'eq': 'minecraft:red_wool'}})
    self.assertTrue(held['held'], held)
    self.assertEqual('world', self.connection.request('status')['state'])

  def test_9_quit(self) -> None:
    self.assertEqual({}, self.connection.request('quit', {'reason': 'test_9'}))
    self.assertTrue(self.game.ended(GONE_SECONDS))


if __name__ == '__main__':
  unittest.main()

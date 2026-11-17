"""
The probe beside NeoForge (SPEC.md 19.7 step 7b): unitTAS's loader-free
probe, a Java agent beside NeoForge (the loader a NeoForge mod under test
brings), mods/ empty, in one game: a real 1.21.1 NeoForge 21.1.267 client
from unitTAS's own launcher (bin/launch_client.py --minecraft 1.21.1
--loader neoforge --loader-version 21.1.267), NeoForge installed by its
own installer into the download cache as the launcher first needs it. As
test_fabric's game checks have it beside Fabric:
- its hello says what really runs: the port 1.21.1, Minecraft 1.21.1,
  NeoForge 21.1.267 beside it, Mojang's names (NeoForge's installer renames
  the game so: no table), a client, on Java 21;
- ready once loaded, naming NeoForge's mods (minecraft and neoforge, not
  unitTAS: no mod), every hooked class rewritten (after NeoForge's own
  transformers), its window titled unitTAS;
- status in the menu, ticks counted exactly, wait.until on the screen, the
  heartbeat's ticks; quit ends the game, as the Quit button does.

  python -m unittas.selftest test_neoforge.
  (through the watcher: "probe test_neoforge.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import unittest

from agentgame import HOOKED, buildAgent
from fabricgame import TITLE
from neoforgegame import NEOFORGE, NeoForgeGame
from ports import neoForgeVersion
from probegame import GONE_SECONDS, READY_SECONDS, modVersion, results

#  what each version runs on beside NeoForge
JAVAS = {'1.21.1': '21'}
#  the probe's operations its hello lists, each in every port
OPS = ('status', 'quit', 'ticks.wait', 'screen.get', 'key.down',
       'player.perceive', 'container.click', 'view.block', 'block.faces',
       'texture.get', 'reflect.get', 'reflect.set')


def isEvent(kind: str):
  """A test of an event: its kind."""
  return lambda event: event.get('event') == kind


class NeoForgeGameTests(unittest.TestCase):
  """
  The probe beside NeoForge, on the NeoForge port's version (1.21.1 on any
  other port).
  """

  @classmethod
  def setUpClass(cls) -> None:
    cls.version = neoForgeVersion()
    folder = os.path.join(results(), 'neoforge')
    jar = buildAgent(os.path.join(folder, 'build.log'), cls.version)
    cls.game = NeoForgeGame(results(), jar, 'neoforge',
                            minecraft=cls.version)
    cls.connection = cls.game.start(READY_SECONDS)
    cls.ready = cls.connection.events.waitFor(isEvent('ready'),
                                              READY_SECONDS)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop(30)

  def request(self, op: str, args: dict = None, timeout: float = 60.0):
    return self.connection.request(op, args, timeout=timeout)

  def test_1_its_hello_says_what_runs(self) -> None:
    hello = self.connection.hello
    self.assertEqual(self.version, hello.probePort,
                     "the agent's port: the same beside any loader")
    self.assertEqual(self.version, hello.minecraft)
    self.assertEqual(('neoforge', NEOFORGE[self.version]),
                     (hello.loaderName, hello.loaderVersion))
    self.assertEqual('mojang', hello.names,
                     "NeoForge's installer renames the game by Mojang's")
    role = hello.role
    self.assertEqual('client', role.value if hasattr(role, 'value')
                     else str(role))
    self.assertFalse(hello.development, 'a real client')
    self.assertEqual(modVersion(), hello.probeVersion,
                     "the probe's version from its own jar")
    self.assertTrue(hello.javaVersion.startswith(JAVAS[self.version]),
                    hello.javaVersion)

  def test_2_the_probe_s_own_operations(self) -> None:
    for op in OPS:
      self.assertIn(op, self.connection.hello.ops)

  def test_2b_ready_once_loaded(self) -> None:
    self.assertEqual(TITLE, self.ready['screen'])
    mods = {mod['id'] for mod in self.ready['mods']}
    self.assertTrue({'minecraft', 'neoforge'} <= mods, mods)
    self.assertNotIn('unittas', mods, 'the probe is no NeoForge mod')
    self.assertEqual(HOOKED[self.version], self.ready['mixins']['applied'],
                     "each hooked class rewritten after NeoForge's own")
    self.assertEqual([], self.ready['mixins']['missing'])
    window = self.ready['window']
    self.assertEqual((854, 480), (window['width'], window['height']))
    self.assertEqual('unitTAS', window['title'],
                     "the window's behaviours (PROTOCOL.md 2.5)")

  def test_3_status_answers(self) -> None:
    status = self.request('status')
    self.assertEqual('menu', status['state'])
    self.assertEqual(TITLE, status['screen'])
    self.assertEqual(['client'], status['sides'], 'no world: no server')
    self.assertEqual('unitTAS', status['player'])

  def test_3b_ticks_counted_exactly(self) -> None:
    waited = self.request('ticks.wait', {'side': 'client', 'n': 20}, 30)
    self.assertEqual(20, waited['tick'] - waited['from'])

  def test_3c_wait_until_on_the_screen(self) -> None:
    found = self.request('wait.until', {
      'side': 'client', 'op': 'screen.get', 'args': {},
      'test': {'path': ['class'], 'eq': TITLE}, 'max_ticks': 100})
    self.assertTrue(found['held'], found)

  def test_3d_the_heartbeat_s_ticks(self) -> None:
    events = self.connection.events
    mark = events.mark()
    first = events.waitFor(isEvent('tick'), 10, since=mark)
    self.request('ticks.wait', {'side': 'client', 'n': 40}, 30)
    later = events.waitFor(
      lambda event: (event.get('event') == 'tick'
                     and event['client'] > first['client']), 10, since=mark)
    self.assertGreater(later['client'], first['client'])

  def test_4_quit_ends_the_game(self) -> None:
    events = self.connection.events
    mark = events.mark()
    self.assertEqual({}, self.request('quit', {'reason': 'test_4'}, 10))
    gone = events.waitFor(isEvent('quit'), 30, since=mark)
    self.assertEqual('asked', gone['reason'])
    self.assertTrue(self.game.ended(GONE_SECONDS),
                    'the game is still running %s s after quit'
                    % GONE_SECONDS)


if __name__ == '__main__':
  unittest.main()

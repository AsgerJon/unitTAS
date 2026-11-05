"""
Step 2 of phase 2 (SPEC.md section 8.3): the probe connects. In the real
development client: the hello, status while the game loads, ready at the
title screen, an operation the probe doesn't have, events.set, the
heartbeat, quit; a hello refused; and the orchestrator going away, while the game loads and
at the title screen. Each class is one launch of its own.

  python -m unittas.selftest connect      (through the watcher: "probe connect")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import re
import time
import unittest

from probegame import GONE_SECONDS, MIXINS, READY_SECONDS, ROOT, modVersion, results
from unittas.dev import DevGame
from unittas.errors import LinkClosed, LinkTimeout, Unsupported
from unittas.wire import Role


def isReady(event: dict) -> bool:
  return event.get('event') == 'ready'


class ConnectTests(unittest.TestCase):
  """One launch, its tests in order (unittest runs them by name)."""

  @classmethod
  def setUpClass(cls) -> None:
    cls.game = DevGame(ROOT, results(), 'connect')
    cls.connection = cls.game.start()

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop()

  def test_1_the_hello(self) -> None:
    hello = self.connection.hello
    self.assertEqual((1,), hello.protocol)
    self.assertEqual('connect', hello.name)
    self.assertIs(Role.CLIENT, hello.role)
    self.assertEqual('1.7.10', hello.minecraft)
    self.assertEqual(('forge', '10.13.4.1614'), (hello.loaderName, hello.loaderVersion))
    self.assertEqual(modVersion(), hello.probeVersion)
    self.assertEqual('1.7.10-forge', hello.probePort)
    self.assertEqual('mcp', hello.names, 'a development run names Minecraft by MCP')
    self.assertTrue(hello.development)
    self.assertRegex(hello.javaVersion, r'^1\.8\.')
    self.assertGreater(hello.pid, 0)
    self.assertTrue(hello.gameDir.endswith('run/client'), hello.gameDir)
    for op in ('status', 'events.set', 'quit'):
      self.assertIn(op, hello.ops)
    self.assertIn('log', hello.events)
    self.assertIn('java.result', hello.events, 'java.run sends one for each line of its report')
    self.assertIn('tick', hello.events, 'the heartbeat')
    self.assertIn('crash', hello.events)

  def test_1b_dialled_only_once_minecraft_is_launched(self) -> None:
    # Until LaunchWrapper launches Minecraft, its tweakers are still adding class transformers, and its class loader
    # goes through that list without a lock: a class the probe's link thread loaded meanwhile failed (a
    # ConcurrentModificationException) and stayed unloadable for the rest of the game: no request answered again, or,
    # when it was Gson's parser, the game unable to launch at all (2026-11-05)
    path = os.path.join(self.game.results, 'gradle.log')
    dialled = -1
    deadline = time.monotonic() + 10
    while dialled == -1 and time.monotonic() < deadline:
      with open(path, encoding='utf-8', errors='replace') as log:
        text = log.read()
      dialled = text.find('unitTAS probe: dialling')
      if dialled == -1:
        time.sleep(0.2)
    self.assertNotEqual(-1, dialled, "the probe's dialling line isn't in the game's log")
    self.assertNotEqual(-1, text.find('Launching wrapped minecraft', 0, dialled),
                        'the probe dialled before LaunchWrapper launched Minecraft, while its tweakers were still adding'
                        ' class transformers')

  def test_2_status_while_the_game_loads(self) -> None:
    status = self.connection.request('status', timeout=10)
    self.assertEqual('loading', status['state'])
    self.assertEqual('client', status['role'])
    self.assertIsNone(status['world'])
    self.assertGreater(status['memory_mb']['max'], 0)

  def test_3_ready_at_the_title_screen(self) -> None:
    ready = self.connection.events.waitFor(isReady, READY_SECONDS)
    self.assertTrue(ready['screen'].endswith('GuiMainMenu'), ready['screen'])
    ids = [mod['id'] for mod in ready['mods']]
    for mod in ('mcp', 'FML', 'Forge', 'unittas'):
      self.assertIn(mod, ids)
    self.assertEqual(sorted(MIXINS), sorted(ready['mixins']['applied']))
    self.assertEqual([], ready['mixins']['missing'])
    self.assertEqual('unitTAS', ready['window']['title'])
    self.assertGreater(ready['load_ms'], 0)
    self.assertEqual(1, ready['at']['client'], 'ready is the first client tick')

  def test_4_status_at_the_title_screen(self) -> None:
    first = self.connection.request('status', timeout=10)
    time.sleep(1)
    second = self.connection.request('status', timeout=10)
    self.assertEqual('menu', second['state'])
    self.assertEqual(['client'], second['sides'])
    self.assertIsNone(second['world'])
    self.assertIsNone(second['joined'])
    self.assertTrue(second['screen'].endswith('GuiMainMenu'), second['screen'])
    self.assertEqual('unitTAS', second['window']['title'])
    self.assertFalse(second['window']['pointer_grabbed'])
    self.assertGreater(second['ticks']['client'], first['ticks']['client'], 'the client ticks')
    self.assertIsNone(second['ticks']['server'], 'no server while no world is open')

  def test_5_an_operation_the_probe_lacks(self) -> None:
    with self.assertRaises(Unsupported) as caught:
      self.connection.request('wobble.about', timeout=10)
    self.assertIn('wobble.about', caught.exception.message)

  def test_6_events_set_says_its_settings(self) -> None:
    settings = self.connection.request('events.set', {'log': 'info', 'sound': False}, timeout=10)
    self.assertEqual({'chat': True, 'sound': False, 'screen': True, 'log': 'info'}, settings)
    again = self.connection.request('events.set', {'log': 'warn'}, timeout=10)
    self.assertEqual({'chat': True, 'sound': False, 'screen': True, 'log': 'warn'}, again)

  def test_6b_the_heartbeat(self) -> None:
    # once a second, from the probe's own thread, whether or not the game ticks (PROTOCOL.md 7). Held in a client tick
    # on purpose (debug.lag, 10 s), the heartbeat still comes: two in that one tick, the client's count standing and
    # its age growing. Decided by the events; the waits' times are only there for a heartbeat that never comes.
    def isTick(event: dict) -> bool:
      return event.get('event') == 'tick'

    beat = self.connection.events.waitFor(isTick, 30, since=self.connection.events.mark())
    for field in ('client', 'server', 'client_ago_ms', 'server_ago_ms', 'screen', 'state', 'paused'):
      self.assertIn(field, beat)
    self.assertEqual('menu', beat['state'])
    self.assertIsNone(beat['server'], 'no server while no world is open')
    self.assertIsNone(beat['server_ago_ms'])
    self.assertTrue(beat['screen'].endswith('GuiMainMenu'), beat['screen'])
    self.assertFalse(beat['paused'])
    mark = self.connection.events.mark()
    self.connection.request('debug.lag', {'ms': 10000, 'ticks': 1}, side='client', timeout=30)
    held = self.connection.events.waitFor(lambda event: isTick(event) and event['client_ago_ms'] >= 2000, 60,
                                          since=mark)
    after = self.connection.events.mark()
    again = self.connection.events.waitFor(isTick, 30, since=after)
    self.assertEqual(held['client'], again['client'], 'the client ticked while held: %s, then %s' % (held, again))
    self.assertGreater(again['client_ago_ms'], held['client_ago_ms'])
    # and once it is let go, the client ticks on, and the heartbeat says so
    self.connection.events.waitFor(lambda event: isTick(event) and event['client'] > held['client'], 60, since=after)

  def test_7_quit(self) -> None:
    mark = self.connection.events.mark()
    self.assertEqual({}, self.connection.request('quit', {'reason': 'test_7'}, timeout=10))
    gone = self.connection.events.waitFor(lambda event: event.get('event') == 'quit', 30, since=mark)
    self.assertEqual('asked', gone['reason'])
    self.assertTrue(self.game.ended(GONE_SECONDS), 'the game is still running %s s after quit' % GONE_SECONDS)
    self.assertTrue(self.connection.closed)


class RefusedTests(unittest.TestCase):
  """A hello with a token the orchestrator didn't give: refused, and the game quits by itself."""

  def test_the_game_quits(self) -> None:
    game = DevGame(ROOT, results(), 'refused')
    self.addCleanup(game.stop)

    def spoil(expected) -> None:
      with open(expected.startFile, encoding='utf-8') as file:
        text = file.read()
      with open(expected.startFile, 'w', encoding='utf-8') as file:
        file.write(re.sub(r'token=[0-9a-f]+', 'token=' + '0' * 64, text))

    game.launch(spoil)
    with self.assertRaises(LinkTimeout) as caught:
      game.accept(READY_SECONDS)
    self.assertIn('wrong token', str(caught.exception))
    self.assertTrue(game.ended(GONE_SECONDS), 'the refused game is still running after %s s' % GONE_SECONDS)


class GoneWhileLoadingTests(unittest.TestCase):
  """The orchestrator goes away while the game loads: the game quits (no window left behind)."""

  def test_the_game_quits(self) -> None:
    game = DevGame(ROOT, results(), 'gone-loading')
    self.addCleanup(game.stop)
    connection = game.start()
    self.assertEqual('loading', connection.request('status', timeout=10)['state'])
    connection.close()
    self.assertTrue(game.ended(GONE_SECONDS), 'the game is still running %s s after its orchestrator went' % GONE_SECONDS)


class GoneAtTheTitleScreenTests(unittest.TestCase):
  """The orchestrator goes away once the game is up: the game quits as its own Quit does."""

  def test_the_game_quits(self) -> None:
    game = DevGame(ROOT, results(), 'gone-menu')
    self.addCleanup(game.stop)
    connection = game.start()
    connection.events.waitFor(isReady, READY_SECONDS)
    connection.close()
    self.assertTrue(game.ended(GONE_SECONDS), 'the game is still running %s s after its orchestrator went' % GONE_SECONDS)
    with self.assertRaises(LinkClosed):
      connection.request('status', timeout=1)


if __name__ == '__main__':
  unittest.main()

"""
Phase 3b step 3 (SPEC.md section 11.3): a real client joins a dedicated server and leaves it. The server as step 2
has it (on 127.0.0.1 alone, its ready let through), the client as test_realclient has it (the release jar beside
UniMixins, offline as unitTAS). The client joins, stands 40 ticks, and its probe says it joined; its own side reads the
server's world, while the server side is the server's probe's to ask. It leaves for the title screen. A join to a
port where nothing listens is Disconnected with the reason the client was shown, and the client is at the title screen
again; a join to anywhere but 127.0.0.1 is refused; a client joins one server at a time. The join guard: a join the
server drops as 1.7.10's race does (made to happen by debug.drop_login on the server) is cancelled after 200 client
ticks at the connecting screen and joined again, with a warning; dropped twice, it is Disconnected naming the race.
The server's log saw it come and go.

  python -m unittas.selftest test_join.      (through the watcher: "probe test_join.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import math
import os
import shutil
import unittest

from probegame import READY_SECONDS, ROOT, results
from unittas.api import Game
from unittas.errors import BadRequest, Disconnected, NotReady
from unittas.launcher import Sources
from unittas.release import ReleaseGame, releaseJar
from unittas.servergame import ServerGame, freePort

PLAYER = 'unitTAS'


class JoinTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    if not os.path.isfile(os.path.join(ROOT, 'asger_accepts_all_eulas.txt')):
      raise unittest.SkipTest("a dedicated server needs Mojang's EULA accepted: this runs on Asger's standing yes only")
    os.makedirs(os.path.join(results(), 'join-server'), exist_ok=True)
    cls.jar = releaseJar(ROOT, os.path.join(results(), 'join-server', 'build.log'))
    mixins = os.path.join(ROOT, 'run', 'oldsaves', 'mods', 'unimixins-1.7.10-0.3.1.jar')
    folder = os.path.join(results(), 'join-server-folder')
    shutil.rmtree(folder, ignore_errors=True)
    cls.server = ServerGame(ROOT, results(), 'join-server', folder=folder, mods=[cls.jar, mixins], players=(PLAYER,),
                            eula=True, memory='1G', sources=Sources(gradleHome=os.path.join(ROOT, '.gradle-home')))
    cls.serverConnection, _ = cls.server.ready(READY_SECONDS)
    cls.client = ReleaseGame(ROOT, results(), 'join-client', jar=cls.jar)
    try:
      cls.connection = cls.client.start()
      cls.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    except BaseException:
      cls.server.stop()
      raise
    cls.game = Game(cls.connection)

  @classmethod
  def tearDownClass(cls) -> None:
    try:
      cls.client.stop()
    finally:
      cls.server.stop()

  def connections(self, state: str, since: int = 0) -> list:
    return [event for event in self.connection.events.since(since) if event.get('event') == 'connection'
            and event.get('state') == state]

  def test_1_joined_and_standing_in_its_world(self) -> None:
    ms = self.game.join(self.server.port)
    self.assertGreater(ms, 0)
    status = self.connection.request('status', timeout=10)
    self.assertEqual('127.0.0.1:%d' % self.server.port, status['joined'])
    self.assertEqual('world', status['state'])
    player = self.game.player(side='client')
    self.assertEqual(PLAYER, player.name)
    under = (int(math.floor(player.pos.x)), 3, int(math.floor(player.pos.z)))
    self.assertEqual('minecraft:grass', self.game.block(under, side='client').id,
                     "the server's flat world under the player, as the client sees it")
    self.assertEqual(1, len(self.connections('joined')))
    with self.assertRaises(NotReady) as raised:
      self.game.block(under, side='server')
    self.assertIn('joined', str(raised.exception))

  def test_2_left_for_the_title_screen(self) -> None:
    self.game.leave()
    status = self.connection.request('status', timeout=10)
    self.assertIsNone(status['joined'])
    self.assertEqual('menu', status['state'])
    left = self.connections('left')
    self.assertEqual(1, len(left), left)
    self.assertEqual(self.server.port, left[0]['port'])

  def test_3_refused_where_nothing_listens(self) -> None:
    with self.assertRaises(Disconnected) as raised:
      self.game.join(freePort(), maxSeconds=60)
    self.assertIn('refused', str(raised.exception).lower())
    answer = self.connection.request('wait.until', {'side': 'client', 'op': 'screen.get', 'args': {},
                                                    'test': {'path': ['class'], 'eq': 'net.minecraft.client.gui.GuiMainMenu'},
                                                    'max_ticks': 200}, timeout=60)
    self.assertTrue(answer['held'], 'not back at the title screen: %r' % (answer['value'],))
    self.assertIsNone(self.connection.request('status', timeout=10)['joined'])

  def test_4_loopback_only_and_one_server_at_a_time(self) -> None:
    with self.assertRaises(BadRequest):
      self.connection.request('server.join', {'address': '10.0.0.1', 'port': self.server.port}, timeout=10)
    self.game.join(self.server.port, settleTicks=10)
    try:
      with self.assertRaises(NotReady):
        self.game.join(self.server.port, settleTicks=10)
    finally:
      self.game.leave()

  def test_5_a_dropped_join_is_joined_again(self) -> None:
    mark = self.connection.events.mark()
    self.serverConnection.request('debug.drop_login', {'logins': 1}, timeout=10)
    pending = self.connection.send('server.join', {'address': '127.0.0.1', 'port': self.server.port, 'settle_ticks': 10,
                                                   'max_seconds': 180})
    try:
      self.assertIn('load_ms', pending.result(240))
    finally:
      self.serverConnection.request('debug.drop_login', {'logins': 0}, timeout=10)
    try:
      self.assertTrue(any("1.7.10's race" in warning and 'joined again' in warning for warning in pending.warnings),
                      pending.warnings)
      self.assertEqual(1, len(self.connections('dropped', mark)))
    finally:
      self.game.leave()

  def test_6_dropped_twice_is_disconnected(self) -> None:
    self.serverConnection.request('debug.drop_login', {'logins': 2}, timeout=10)
    try:
      with self.assertRaises(Disconnected) as raised:
        self.game.join(self.server.port, settleTicks=10)
      self.assertIn("1.7.10's race", str(raised.exception))
      self.assertIn('again after one more try', str(raised.exception))
    finally:
      self.serverConnection.request('debug.drop_login', {'logins': 0}, timeout=10)
    answer = self.connection.request('wait.until', {'side': 'client', 'op': 'screen.get', 'args': {},
                                                    'test': {'path': ['class'], 'eq': 'net.minecraft.client.gui.GuiMainMenu'},
                                                    'max_ticks': 200}, timeout=60)
    self.assertTrue(answer['held'], 'not back at the title screen: %r' % (answer['value'],))

  def test_7_the_servers_log_saw_it_come_and_go(self) -> None:
    with open(os.path.join(self.server.results, 'server.log'), encoding='utf-8', errors='replace') as file:
      log = file.read()
    self.assertEqual(3, log.count('%s joined the game' % PLAYER), 'joined three times: test_1, test_4, test_5')
    self.assertEqual(3, log.count('%s left the game' % PLAYER))
    self.assertNotIn('NoClassDefFoundError', log)


if __name__ == '__main__':
  unittest.main()

"""
Phase 3b step 4 (SPEC.md section 11.3): players by name, with two real clients, alice and bob, on one dedicated server.
Three games at once (about 5 GB): asked for before it is run.
- Both listed by the server, in its status and its player.joined events.
- A player named, or the only one in; unnamed with two in is a BadRequest that names them; a name not in is NotFound.
- A command run as each: /tp @p moves the one it names (the server and that client see it), not the other.
- A kick: the kicked client is disconnected (its connection event says left, with what its screen showed), the server
  lists one player left, and its player.left event says who. Whether the kicked client is shown the kick's own reason
  is 1.7.10's affair: on 2026-11-06 it showed "Connection Lost: Disconnected from server" instead, the server's
  goodbye unread before the connection closed. unitTAS shows the game as it is.
- The last one leaves: the server lists nobody, and a command as a player is NotReady.

  python -m unittas.selftest test_players.      (through the watcher: "probe test_players.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from probegame import READY_SECONDS, ROOT, results
from unittas.api import Game
from unittas.errors import BadRequest, NotFound, NotReady
from unittas.launcher import Sources
from unittas.release import ReleaseGame, releaseJar
from unittas.servergame import ServerGame

NAMES = ('alice', 'bob')
KICKED = 'the test is done with bob'


class PlayersTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    if not os.path.isfile(os.path.join(ROOT, 'asger_accepts_all_eulas.txt')):
      raise unittest.SkipTest("a dedicated server needs Mojang's EULA accepted: this runs on Asger's standing yes only")
    os.makedirs(os.path.join(results(), 'players-server'), exist_ok=True)
    jar = releaseJar(ROOT, os.path.join(results(), 'players-server', 'build.log'))
    mixins = os.path.join(ROOT, 'run', 'oldsaves', 'mods', 'unimixins-1.7.10-0.3.1.jar')
    folder = os.path.join(results(), 'players-server-folder')
    shutil.rmtree(folder, ignore_errors=True)
    cls.launched = []
    cls.server = ServerGame(ROOT, results(), 'players-server', folder=folder, mods=[jar, mixins], players=NAMES,
                            eula=True, memory='1G', sources=Sources(gradleHome=os.path.join(ROOT, '.gradle-home')))
    cls.launched.append(cls.server)
    try:
      serverConnection, _ = cls.server.ready(READY_SECONDS)
      cls.serverGame = Game(serverConnection)
      cls.serverConnection = serverConnection
      cls.clients = {}
      for name in NAMES:
        client = ReleaseGame(ROOT, results(), 'players-' + name, jar=jar, username=name,
                             folder=os.path.join(results(), 'players-%s-game' % name))
        cls.launched.append(client)
        connection = client.start()
        connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
        cls.clients[name] = (connection, Game(connection))
      for name in NAMES:
        cls.clients[name][1].join(cls.server.port)
    except BaseException:
      cls.stopAll()
      raise

  @classmethod
  def stopAll(cls) -> None:
    for game in reversed(cls.launched):
      try:
        game.stop()
      except Exception:  # each is stopped whatever the one before did
        pass

  @classmethod
  def tearDownClass(cls) -> None:
    cls.stopAll()

  def serverEvents(self, kind: str) -> list:
    return [event for event in self.serverConnection.events.since(0) if event.get('event') == kind]

  def test_1_both_listed(self) -> None:
    self.assertEqual(sorted(NAMES), sorted(player['name'] for player in self.serverGame.players()))
    self.assertEqual(sorted(NAMES), self.serverConnection.request('status', timeout=10)['players'])
    self.assertEqual(sorted(NAMES), sorted(event['name'] for event in self.serverEvents('player.joined')))

  def test_2_named_or_refused(self) -> None:
    self.assertEqual('bob', self.serverGame.player(name='bob').name)
    with self.assertRaises(BadRequest) as raised:
      self.serverGame.player()
    for name in NAMES:
      self.assertIn(name, str(raised.exception))
    with self.assertRaises(NotFound):
      self.serverGame.player(name='carol')

  def test_3_a_command_as_each(self) -> None:
    before = self.serverGame.player(name='alice').pos
    said = self.serverGame.command('/tp @p 10 4 10', as_='bob')
    self.assertEqual(1, said.result, said)
    bob = self.serverGame.player(name='bob').pos
    self.assertTrue(abs(bob.x - 10.5) <= 0.5 and abs(bob.z - 10.5) <= 0.5, bob)
    self.assertEqual(before, self.serverGame.player(name='alice').pos, 'alice was not the one moved')
    seen = self.clients['bob'][0].request('wait.until', {'side': 'client', 'op': 'player.get', 'args': {},
                                                         'test': {'path': ['pos', 0], 'ge': 9.9}, 'max_ticks': 100},
                                          timeout=60)
    self.assertTrue(seen['held'], "bob's own client didn't see the move: %r" % (seen['value'],))

  def test_4_a_kick(self) -> None:
    bob = self.clients['bob'][0]
    since = bob.events.mark()
    self.serverGame.kick('bob', KICKED)
    left = bob.events.waitFor(lambda event: event.get('event') == 'connection' and event.get('state') == 'left', 60,
                              since)
    self.assertTrue(left['reason'], 'disconnected with no reason shown: %r' % (left,))
    self.assertIsNone(bob.request('status', timeout=10)['joined'])
    self.serverConnection.events.waitFor(lambda event: event.get('event') == 'player.left' and event.get('name') == 'bob',
                                         30)
    self.assertEqual(['alice'], [player['name'] for player in self.serverGame.players()])

  def test_5_the_last_one_leaves(self) -> None:
    self.clients['alice'][1].leave()
    self.serverConnection.events.waitFor(
      lambda event: event.get('event') == 'player.left' and event.get('name') == 'alice', 30)
    self.assertEqual((), self.serverGame.players())
    with self.assertRaises(NotReady):
      self.serverGame.command('/time set 100')


if __name__ == '__main__':
  unittest.main()

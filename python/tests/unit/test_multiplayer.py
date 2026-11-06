"""
Phase 3b step 5 (SPEC.md 11.3), without a game: several games in one run. test_run's fake game is the run's own client
(alice, D2); a fake dedicated server and fake further clients are made by the factories a Multiplayer is given, each
over a real connection.
- A multiplayer class: the run's own client leaves its singleplayer world, the server starts (its world prepared,
  its setUpWorld run), the other clients start, and all join it.
- Each test's reset runs across the games: one batch on the server for every player, each client's own part.
- A fresh world for the next class is a restart: the clients leave, the server goes, its world folder goes, a new
  server starts on a new port, they join it. A shared class runs on as it is.
- A singleplayer class after a multiplayer one: the clients leave, the run's own client gets its kept world back.
- Short of memory for the other games: refused with the numbers, nothing started.
- The run's end: the clients leave, the other games stop.
- MultiplayerTestCase: skipped unless the run is asked for multiplayer, and skipped in a run that can't hold one.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import unittest

import gamecases
from fakeprobe import FakeError, FakeProbe, inThread
from unittas.link import Listener
from unittas.multiplayer import MemoryShort, Multiplayer, availableMb, megabytes
from unittas.run import Run, runSuite
from unittas.servergame import awaitServerReady
from unittas.wire import Role
from test_run import FakeRun
from test_values import PLAYER


def batchAnswer(args, side):
  """A server's batch: each op ok, the reset's player.reset not respawned, resetPlayer's plugins none."""
  out = []
  for op in args['ops']:
    value = {'respawned': False} if op['op'] == 'player.reset' else {'plugins': []} if op['op'] == 'hooks.run' else {}
    out.append({'ok': True, 'value': value})
  return out


class FakeServer:
  """A dedicated server's face for a Multiplayer: 'ready' (its fake probe connects and says it listens on 127.0.0.1)."""

  def __init__(self, folder: str, port: int, players: tuple) -> None:
    self.folder = folder
    self.port = port
    self.players = players
    self.asked = []
    self.stops = 0
    self.fake = None
    self.connection = None
    self.listener = None
    os.makedirs(os.path.join(folder, 'unittas', 'region'), exist_ok=True)

  def worldFolder(self) -> str:
    return os.path.join(self.folder, 'unittas')

  def ready(self, seconds: float = 10) -> tuple:
    self.listener = Listener()
    expected = self.listener.prepare(self.folder, 'server', Role.SERVER)
    self.fake = FakeProbe(expected.startFile)
    thread, _ = inThread(self.fake.connect)
    self.connection = self.listener.accept(timeout=10)
    thread.join(10)
    self.asked = self.fake.serve({
      'world.prepare': lambda args, side: {},
      'hooks.run': lambda args, side: {'plugins': []},
      'player.get': lambda args, side: dict(PLAYER, name=args.get('player', 'Dev')),
      'batch': batchAnswer,
      'quit': lambda args, side: {},
    })
    self.fake.event('ready', world='unittas', listening=[{'address': '127.0.0.1', 'port': self.port}],
                    address='127.0.0.1', port=self.port, mods=[], mixins={'applied': [], 'missing': []})
    return self.connection, awaitServerReady(self.connection, self.stop, seconds)

  def stop(self) -> None:
    self.stops += 1
    for each in (self.connection, self.fake, self.listener):
      if each is not None:
        each.close()

  def ops(self) -> list:
    return [request['op'] for request in self.asked]


class FakeClient:
  """A further client's face: 'start' (its fake probe connects, then ready), 'stop'; it joins and leaves."""

  def __init__(self, folder: str, name: str) -> None:
    self.folder = folder
    self.name = name
    self.asked = []
    self.stops = 0
    self.joined = False
    os.makedirs(folder, exist_ok=True)

  def start(self):
    self.listener = Listener()
    expected = self.listener.prepare(self.folder, self.name, Role.CLIENT)
    self.fake = FakeProbe(expected.startFile)
    thread, _ = inThread(self.fake.connect)
    self.connection = self.listener.accept(timeout=10)
    thread.join(10)
    me = dict(PLAYER, name=self.name)

    def join(args, side):
      self.joined = True
      return {'load_ms': 50}

    def leave(args, side):
      self.joined = False
      return {'leave_ms': 5}

    def player(args, side):
      if not self.joined:
        raise FakeError('NotReady', 'the client has no player: no world is open')
      return me

    self.asked = self.fake.serve({
      'server.join': join,
      'server.leave': leave,
      'status': lambda args, side: {'joined': '127.0.0.1:1' if self.joined else None, 'state': 'world',
                                    'player': self.name},
      'player.get': player,
      'client.reset': lambda args, side: {},
      'wait.until': lambda args, side: {'held': True, 'tick': 5, 'checks': 1, 'value': me},
      'quit': lambda args, side: {},
    })
    self.fake.event('ready', screen='net.minecraft.client.gui.GuiMainMenu', load_ms=10, mods=[], mixins=[],
                    window={'title': 'unitTAS', 'width': 854, 'height': 480, 'pointer_grabbed': False})
    return self.connection

  def stop(self) -> None:
    self.stops += 1
    for each in (self.connection, self.fake, self.listener):
      each.close()

  def ops(self) -> list:
    return [request['op'] for request in self.asked]


class MultiplayerCase(FakeRun, unittest.TestCase):

  def setUp(self) -> None:
    FakeRun.setUp(self)
    self.aliceJoined = [False]

    def join(args, side):
      self.aliceJoined[0] = True
      return {'load_ms': 40}

    def leave(args, side):
      self.aliceJoined[0] = False
      return {'leave_ms': 5}

    self.handlers['server.join'] = join
    self.handlers['server.leave'] = leave
    self.handlers['status'] = lambda args, side: {'joined': '127.0.0.1:1' if self.aliceJoined[0] else None,
                                                  'state': 'world', 'player': 'Dev'}
    # as the game has it: no player while no world is open (its own, or a server's)
    self.aliceWorld = [True]
    close, open_, playerGet = self.handlers['world.close'], self.handlers['world.open'], self.handlers['player.get']

    def closing(args, side):
      self.aliceWorld[0] = False
      return close(args, side)

    def opening(args, side):
      self.aliceWorld[0] = True
      return open_(args, side)

    def player(args, side):
      if side == 'client' and not (self.aliceWorld[0] or self.aliceJoined[0]):
        raise FakeError('NotReady', 'the client has no player: no world is open')
      return playerGet(args, side)

    self.handlers['world.close'] = closing
    self.handlers['world.open'] = opening
    self.handlers['player.get'] = player
    self.handlers['client.reset'] = lambda args, side: {}
    self.servers = []
    self.clients = {}
    self.ports = iter(range(41300, 41400))
    self.available = 32000

    def serverFor(players):
      server = FakeServer(os.path.join(self.scratch, 'server-%d' % len(self.servers)), next(self.ports), players)
      self.servers.append(server)
      return server

    def clientFor(name):
      client = FakeClient(os.path.join(self.scratch, 'client-' + name), name)
      self.clients[name] = client
      return client

    self.run.multiplayer = Multiplayer(self.run, serverFor, clientFor, serverMb=1024,
                                       available=lambda: self.available)
    self.run.multiplayerAllowed = True
    self.run.begin()
    Run.current = self.run
    self.addCleanup(setattr, Run, 'current', None)

  def aliceOps(self) -> list:
    return [request['op'] for request in self.asked]

  def joins(self, asked: list) -> list:
    return [request['args']['port'] for request in asked if request['op'] == 'server.join']


class MultiplayerTests(MultiplayerCase):

  def test_a_class_joins_them_all(self) -> None:
    games = self.run.enterMultiplayer('AMpTests', ('alice', 'bob'), shared=False)
    self.assertEqual({'server', 'alice', 'bob'}, set(games))
    self.assertIs(self.run.game, games['alice'], "alice is the run's own client")
    server = self.servers[0]
    self.assertEqual(('Dev', 'bob'), server.players, 'operators: the players by the names their games have')
    ops = self.aliceOps()
    self.assertLess(ops.index('world.close'), ops.index('server.join'), 'its own world left first')
    self.assertEqual([server.port], self.joins(self.asked))
    self.assertEqual([server.port], self.joins(self.clients['bob'].asked))
    self.assertIn('world.prepare', server.ops())
    self.assertIn({'hook': 'setUpWorld'}, [request.get('args') for request in server.asked])

  def test_the_reset_runs_across_the_games(self) -> None:
    self.run.enterMultiplayer('AMpTests', ('alice', 'bob'), shared=False)
    server = self.servers[0]
    before = len(server.asked)
    self.run.beforeTest('AMpTests.test_a', 60)
    batches = [request for request in server.asked[before:] if request['op'] == 'batch']
    self.assertEqual(1, len(batches))
    ops = batches[0]['args']['ops']
    self.assertEqual([('player.reset', 'Dev'), ('player.reset', 'bob')],
                     [(op['op'], op['args'].get('player')) for op in ops if op['op'] == 'player.reset'])
    self.assertEqual(['world.reset', 'hooks.run'], [op['op'] for op in ops[2:]])
    self.assertIn('client.reset', self.clients['bob'].ops())
    self.assertNotIn('batch', self.aliceOps()[-6:], "the run's own client is no server now")

  def test_a_fresh_world_is_a_restart_and_a_shared_one_isnt(self) -> None:
    self.run.enterMultiplayer('AMpTests', ('alice', 'bob'), shared=False)
    first = self.servers[0]
    self.run.enterMultiplayer('BMpTests', ('alice', 'bob'), shared=False)
    self.assertEqual(2, len(self.servers), 'a new server for a fresh world')
    second = self.servers[1]
    self.assertEqual(1, first.stops)
    self.assertFalse(os.path.exists(first.worldFolder()), 'its world went with it')
    self.assertIn({'hook': 'tearDownWorld'}, [request.get('args') for request in first.asked])
    self.assertEqual([first.port, second.port], self.joins(self.asked))
    self.assertEqual([first.port, second.port], self.joins(self.clients['bob'].asked))
    self.assertEqual(1, self.aliceOps().count('server.leave'), 'left once, between the two')
    self.run.enterMultiplayer('CMpTests', ('alice', 'bob'), shared=True)
    self.assertEqual(2, len(self.servers), 'a shared class runs on the same server')
    self.assertIn('world 3, shared', self.run.worldNote)

  def test_a_singleplayer_class_after_gets_its_world_back(self) -> None:
    self.run.enterMultiplayer('AMpTests', ('alice', 'bob'), shared=False)
    before = len(self.asked)
    self.run.enterClass('BSpTests', shared=True)
    ops = [request['op'] for request in self.asked[before:]]
    self.assertEqual('server.leave', ops[0])
    self.assertIn('world.open', ops)
    self.assertNotIn('world.close', ops, 'no singleplayer world was open to close')
    self.assertIn('server.leave', self.clients['bob'].ops())
    self.assertIn('fresh for BSpTests', self.run.worldNote, 'a world of its own again, shared or not')

  def test_short_of_memory_refuses_and_starts_nothing(self) -> None:
    self.available = 2000
    before = len(self.asked)
    with self.assertRaises(MemoryShort) as raised:
      self.run.enterMultiplayer('AMpTests', ('alice', 'bob'), shared=False)
    self.assertIn('4096 MB', str(raised.exception), 'the server 1024, bob 2048, and 1024 to spare')
    self.assertIn('2000 MB', str(raised.exception))
    self.assertEqual([], self.servers)
    self.assertEqual({}, self.clients)
    self.assertEqual([], self.aliceOps()[before:], 'its own world left as it was')

  def test_the_end_stops_them(self) -> None:
    self.run.enterMultiplayer('AMpTests', ('alice', 'bob'), shared=False)
    self.run.finish()
    self.assertEqual(1, self.servers[0].stops)
    self.assertEqual(1, self.clients['bob'].stops)
    self.assertIn('server.leave', self.clients['bob'].ops())
    self.assertIn('quit', self.aliceOps())

  def test_a_client_a_test_put_out_joins_again_before_the_next(self) -> None:
    """A test that kicks bob (or makes him leave) doesn't leave the class's next tests without him."""
    self.run.enterMultiplayer('AMpTests', ('alice', 'bob'), shared=False)
    bob = self.clients['bob']
    port = self.servers[0].port
    joinsBefore = self.joins(bob.asked)
    bob.joined = False
    self.run.beforeTest('AMpTests.test_b', 60)
    self.assertEqual(joinsBefore + [port], self.joins(bob.asked), 'bob joined again before the reset')
    self.assertEqual([port], self.joins(self.asked), "alice, still in, didn't join again")

  def test_a_shared_class_with_fewer_clients_lets_the_others_go(self) -> None:
    self.run.enterMultiplayer('AMpTests', ('alice', 'bob'), shared=False)
    self.run.enterMultiplayer('BMpTests', ('alice',), shared=True)
    self.assertEqual(1, len(self.servers), 'shared: the same server')
    self.assertIn('server.leave', self.clients['bob'].ops(), "bob isn't the class's: out of the server")
    self.assertNotIn('server.leave', self.aliceOps())

  def test_a_shared_class_brings_back_one_an_earlier_let_go(self) -> None:
    """A (alice, bob), B shared (alice), C shared (alice, bob): bob, let go for B, joins again for C, before its reset."""
    self.run.enterMultiplayer('AMpTests', ('alice', 'bob'), shared=False)
    self.run.enterMultiplayer('BMpTests', ('alice',), shared=True)
    bob = self.clients['bob']
    port = self.servers[0].port
    self.assertFalse(bob.joined)
    self.run.enterMultiplayer('CMpTests', ('alice', 'bob'), shared=True)
    self.assertEqual(1, len(self.servers), 'shared: the same server')
    self.assertIn('world 2, shared', self.run.worldNote)
    self.assertEqual([port, port], self.joins(bob.asked), 'bob in again for C')
    ops = bob.ops()
    self.assertEqual('client.reset', ops[-1], "the class's reset after bob's join")

  def worldHooks(self) -> list:
    """The world hooks the run's own client was asked for, in order."""
    return [request['args']['hook'] for request in self.asked
            if request['op'] == 'hooks.run' and request['args']['hook'] in ('setUpWorld', 'tearDownWorld')]

  def test_a_multiplayer_class_first_tears_down_nothing_it_didnt_set_up(self) -> None:
    """The run's world, opened at its start, had no setUpWorld when a multiplayer class comes first: no tearDownWorld."""
    self.run.enterMultiplayer('AMpTests', ('alice', 'bob'), shared=False)
    self.assertIn('world.close', self.aliceOps())
    self.assertEqual([], self.worldHooks())
    self.run.enterClass('BSpTests')
    self.run.finish()
    self.assertEqual(['setUpWorld', 'tearDownWorld'], self.worldHooks())

  def test_the_world_hooks_pair_up_around_a_multiplayer_class(self) -> None:
    self.run.enterClass('ASpTests')
    self.run.enterMultiplayer('BMpTests', ('alice', 'bob'), shared=False)
    self.run.enterClass('CSpTests')
    self.run.enterMultiplayer('DMpTests', ('alice', 'bob'), shared=False)
    self.run.finish()
    self.assertEqual(['setUpWorld', 'tearDownWorld'] * 2, self.worldHooks())

  def test_no_result_names_the_game_that_went(self) -> None:
    """bob's game gone mid-class: a test's NO RESULT says it was bob's, not the run's own client."""
    from unittas.errors import LinkClosed
    self.run.enterMultiplayer('AMpTests', ('alice', 'bob'), shared=False)
    self.clients['bob'].fake.close()
    import time
    deadline = time.monotonic() + 5
    while not self.clients['bob'].connection.closed and time.monotonic() < deadline:
      time.sleep(0.02)
    why = self.run.whyNoResult(LinkClosed('the connection has ended'))
    self.assertIn("bob's game", why)

  def test_memory_words(self) -> None:
    self.assertEqual(2048, megabytes('2G'))
    self.assertEqual(1536, megabytes('1536M'))
    self.assertIsNone(availableMb('/no/such/meminfo'))


class MultiplayerTestCaseTests(MultiplayerCase):

  def runCase(self, case) -> str:
    runSuite(self.run, unittest.TestLoader().loadTestsFromTestCase(case), stream=io.StringIO())
    with open(self.run.writeReport(), encoding='utf-8') as file:
      return file.read()

  def test_its_games_as_the_class_names_them(self) -> None:
    text = self.runCase(gamecases.MpCaseTests)
    self.assertIn('MpCaseTests.test_a_three_games ... ok', text)
    seen = gamecases.MpCaseTests.seen[self.run]
    self.assertIs(self.run.game, seen['alice'])
    self.assertIsNot(seen['alice'], seen['bob'])
    self.assertEqual('bob', seen['bobName'])

  def test_skipped_unless_asked_for(self) -> None:
    self.run.multiplayerAllowed = False
    text = self.runCase(gamecases.MpCaseTests)
    self.assertIn('MpCaseTests.test_a_three_games ... skipped', text)
    self.assertIn('--multiplayer', text)
    self.assertEqual([], self.servers)

  def test_skipped_where_a_run_cant_hold_one(self) -> None:
    self.run.multiplayer = None
    text = self.runCase(gamecases.MpCaseTests)
    self.assertIn('MpCaseTests.test_a_three_games ... skipped', text)
    self.assertIn('client = "real"', text)

  def test_short_of_memory_is_no_result_for_that_class_only(self) -> None:
    self.available = 1000
    text = self.runCase(gamecases.MpCaseTests)
    self.assertIn('MpCaseTests.test_a_three_games ... NO RESULT', text)
    self.assertIn('MB', text)
    self.assertIsNone(self.run.stopped, 'the run goes on with its other classes')


if __name__ == '__main__':
  unittest.main()

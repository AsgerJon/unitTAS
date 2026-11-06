"""
Phase 3b (SPEC.md section 11.3), the dedicated server in the game.
- Step 1, no probe yet: a 1.7.10 Forge dedicated server from the project's Gradle cache, its folder written as a run
  writes it (the EULA on Asger's standing yes, asger_accepts_all_eulas.txt in the repository), started as FML starts
  a server. It says Done, listens on 127.0.0.1 alone at the port given (the system's own table says so, not only
  its log), and stops on /stop with its world saved.
- Step 2, the probe in it: the release jar and UniMixins in its mods/, its start file saying role server. It says hello
  as a server by Searge's names, with a server's operations only; its ready names the world and every address it
  listens on (127.0.0.1 alone, let through by the orchestrator's check, and so by the system's table); it ticks; a
  client side is Unsupported; world.get and world.prepare; a console command's answer comes back as lines, a red one
  as an error; a command as a player with nobody in is NotReady; its quit is /stop: the world saved, the process gone.

  python -m unittas.selftest test_server.      (through the watcher: "probe test_server.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
import unittest

from probegame import GONE_SECONDS, READY_SECONDS, ROOT, results
from unittas.errors import NotReady, Unsupported
from unittas.launcher import Sources, findJava, serverCommand
from unittas.release import releaseJar
from unittas.servergame import LOOPBACK_FORMS, ServerGame, freePort, serverFiles
from unittas.wire import Role

#  /proc/net/tcp's state for a socket that listens
LISTEN = '0A'
#  127.0.0.1 as the system's tables write it: an IPv4 socket's, and an IPv6 socket's (Java's on Linux) as ::ffff:127.0.0.1,
#  the same loopback address. Any other, '::' or 0.0.0.0 above all, would be the network.
LOOPBACK = ('0100007F', '0000000000000000FFFF00000100007F')


def listeners(port: int) -> list:
  """The addresses something listens on at that TCP port, from the system's own tables (IPv4 and IPv6, as hex)."""
  found = []
  for table in ('/proc/net/tcp', '/proc/net/tcp6'):
    try:
      with open(table, encoding='ascii') as file:
        rows = file.read().split('\n')[1:]
    except OSError:
      continue
    for row in rows:
      fields = row.split()
      if len(fields) < 4 or fields[3] != LISTEN:
        continue
      address, hexPort = fields[1].rsplit(':', 1)
      if int(hexPort, 16) == port:
        found.append(address)
  return found


class ServerTests(unittest.TestCase):

  def waitFor(self, log: str, process: subprocess.Popen, text: str, seconds: float) -> str:
    """The server's output once it holds the text; a failure if the server ends first or the time runs out."""
    deadline = time.monotonic() + seconds
    while True:
      with open(log, encoding='utf-8', errors='replace') as file:
        said = file.read()
      if text in said:
        return said
      if process.poll() is not None:
        self.fail('the server ended (exit %s) before it said %r; its output: %s' % (process.returncode, text, log))
      if time.monotonic() > deadline:
        self.fail('the server didn\'t say %r within %d s; its output: %s' % (text, seconds, log))
      time.sleep(0.5)

  def test_1_it_starts_on_loopback_alone_and_stops(self) -> None:
    if not os.path.isfile(os.path.join(ROOT, 'asger_accepts_all_eulas.txt')):
      self.skipTest("a dedicated server needs Mojang's EULA accepted: this test runs on Asger's standing yes only")
    folder = os.path.join(results(), 'server-step1')
    shutil.rmtree(folder, ignore_errors=True)
    port = freePort()
    serverFiles(folder, port, ('alice',), eula=True)
    launch = serverCommand(folder, findJava(), Sources(gradleHome=os.path.join(ROOT, '.gradle-home')), memory='1G')
    log = os.path.join(folder, 'server-output.log')
    with open(log, 'wb') as out:
      process = subprocess.Popen(launch.java, cwd=folder, stdin=subprocess.PIPE, stdout=out,
                                 stderr=subprocess.STDOUT, start_new_session=True)
    try:
      said = self.waitFor(log, process, 'Done (', READY_SECONDS)
      self.assertRegex(said, r'Forge Mod Loader version \S+ for Minecraft 1\.7\.10 loading')
      self.assertIn('Starting Minecraft server on 127.0.0.1:%d' % port, said)
      found = listeners(port)
      self.assertEqual(1, len(found), 'one listener at its port: %s' % found)
      self.assertIn(found[0], LOOPBACK, 'listening on 127.0.0.1 alone, by the system\'s own table')
      process.stdin.write(b'stop\n')
      process.stdin.flush()
      code = process.wait(GONE_SECONDS)
      with open(log, encoding='utf-8', errors='replace') as file:
        said = file.read()
      self.assertIn('Stopping server', said)
      self.assertEqual(0, code, 'its exit after /stop; its output: %s' % log)
      self.assertTrue(os.path.isfile(os.path.join(folder, 'unittas', 'level.dat')), 'its world saved')
      self.assertEqual([], listeners(port), 'nothing left listening')
    finally:
      if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(15)


class ServerProbeTests(unittest.TestCase):
  """Step 2: one dedicated server with the probe in it, its tests in order."""

  @classmethod
  def setUpClass(cls) -> None:
    if not os.path.isfile(os.path.join(ROOT, 'asger_accepts_all_eulas.txt')):
      raise unittest.SkipTest("a dedicated server needs Mojang's EULA accepted: this runs on Asger's standing yes only")
    folder = os.path.join(results(), 'server-step2')
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(os.path.join(results(), 'server-probe'), exist_ok=True)
    jar = releaseJar(ROOT, os.path.join(results(), 'server-probe', 'build.log'))
    mixins = os.path.join(ROOT, 'run', 'oldsaves', 'mods', 'unimixins-1.7.10-0.3.1.jar')
    cls.game = ServerGame(ROOT, results(), 'server-probe', folder=folder, mods=[jar, mixins], players=('alice',),
                          eula=True, memory='1G', sources=Sources(gradleHome=os.path.join(ROOT, '.gradle-home')))
    cls.connection, cls.ready = cls.game.ready(READY_SECONDS)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop()

  def test_1_its_hello_is_a_servers(self) -> None:
    hello = self.connection.hello
    self.assertIs(Role.SERVER, hello.role)
    self.assertEqual('srg', hello.names, "a real server names Minecraft's members by Searge")
    for op in ('status', 'quit', 'ticks.wait', 'wait.until', 'batch', 'world.get', 'world.prepare', 'command.run',
               'debug.threads', 'debug.drop_login'):
      self.assertIn(op, hello.ops)
    for op in ('screen.get', 'world.create', 'world.open', 'player.look', 'key.tap', 'screenshot', 'java.run',
               'client.reset', 'server.join'):
      self.assertNotIn(op, hello.ops, "a client's operation, on a server")

  def test_2_its_ready_says_loopback_alone(self) -> None:
    ready = self.ready
    self.assertEqual('unittas', ready['world'])
    self.assertEqual(1, len(ready['listening']), ready['listening'])
    self.assertIn(ready['listening'][0]['address'], LOOPBACK_FORMS)
    self.assertEqual(self.game.port, ready['listening'][0]['port'])
    self.assertIn('MixinDedicatedServer', ready['mixins']['applied'], ready['mixins'])
    found = listeners(self.game.port)
    self.assertEqual(1, len(found), found)
    self.assertIn(found[0], LOOPBACK, "and the system's own table agrees")

  def test_3_it_ticks_and_has_no_client_side(self) -> None:
    waited = self.connection.request('ticks.wait', {'n': 20}, timeout=60)
    self.assertGreaterEqual(waited['tick'], 20)
    status = self.connection.request('status', timeout=10)
    self.assertEqual(['server'], status['sides'])
    self.assertIsNone(status['ticks']['client'])
    self.assertEqual('server', status['role'])
    with self.assertRaises(Unsupported):
      self.connection.request('ticks.wait', {'side': 'client', 'n': 1}, timeout=10)
    with self.assertRaises(Unsupported):
      self.connection.request('world.get', side='client', timeout=10)

  def test_4_world_get_and_prepare(self) -> None:
    world = self.connection.request('world.get', timeout=10)
    self.assertEqual('unittas', world['folder'])
    self.assertEqual('flat', world['type'])
    self.assertEqual('creative', world['game_mode'])
    self.assertEqual('2;7,2x3,2;1;', world['generator'])
    self.connection.request('world.prepare', timeout=10)
    world = self.connection.request('world.get', timeout=10)
    for rule in ('doDaylightCycle', 'doMobSpawning', 'doFireTick', 'mobGriefing'):
      self.assertEqual('false', world['rules'][rule], rule)
    self.assertEqual(6000, world['day_time'] % 24000)
    self.assertFalse(world['raining'])

  def test_5_a_console_command_and_its_lines(self) -> None:
    said = self.connection.request('command.run', {'command': '/time set 1000', 'as': 'server'}, timeout=10)
    self.assertEqual(1, said['result'])
    self.assertTrue(any('1000' in line for line in said['lines']), said)
    self.assertEqual([], said['errors'])
    refused = self.connection.request('command.run', {'command': '/time set nonsense', 'as': 'server'}, timeout=10)
    self.assertEqual(0, refused['result'])
    self.assertTrue(refused['errors'], refused)
    with self.assertRaises(NotReady):
      self.connection.request('command.run', {'command': '/time set 2000'}, timeout=10)

  def test_6_a_clients_operation_is_unsupported(self) -> None:
    for op, args in (('screen.get', None), ('player.look', {'yaw': 0, 'pitch': 0}), ('world.create', {})):
      with self.assertRaises(Unsupported, msg=op):
        self.connection.request(op, args, timeout=10)

  def test_7_its_quit_is_stop(self) -> None:
    self.connection.request('quit', {'reason': 'the step 2 check is done'}, timeout=10)
    self.assertTrue(self.game.ended(GONE_SECONDS), 'the server process didn\'t end after its quit')
    self.assertTrue(os.path.isfile(os.path.join(self.game.gameDir, 'unittas', 'level.dat')), 'its world saved')
    self.assertEqual([], listeners(self.game.port), 'nothing left listening')
    with open(os.path.join(self.game.results, 'server.log'), encoding='utf-8', errors='replace') as file:
      log = file.read()
    self.assertIn('Stopping server', log)
    self.assertNotIn('NoClassDefFoundError', log, 'a client class reached on the server')


if __name__ == '__main__':
  unittest.main()

"""
A run's other games for its multiplayer classes, as its spec makes them
(session.multiplayerFor; SPEC.md 11.3 step 5, 19.7 step 10d), with no
game started: on 26.3 as Mojang ships it, the dedicated server has the
spec's agent in (no mods: a vanilla server loads none), its version's
own Java, its memory and EULA the spec's [server]'s, and the memory
check counts a modern client's; a further client is a real client of
its own folder and player, the spec's build done already. 1.7.10's
clients are counted at its own client's memory; a Gradle run has none.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import tempfile
import textwrap
import unittest

from unittas import session
from unittas.cache import Cache
from unittas.launcher import MODERN_CLIENT_MEMORY
from unittas.multiplayer import CLIENT_MB, megabytes
from unittas.servergame import ServerGame
from unittas.spec import InstanceSpec
from unittas.specgame import RealGame


class MultiplayerForTests(unittest.TestCase):

  def setUp(self) -> None:
    self.folder = tempfile.mkdtemp(prefix='unittas-multiplayerfor-')
    self.addCleanup(shutil.rmtree, self.folder, True)
    self.results = os.path.join(self.folder, 'results')
    self.probe = os.path.join(self.folder, 'probe', 'unittas-probe-26.3.jar')
    os.makedirs(os.path.dirname(self.probe))
    with open(self.probe, 'wb') as file:
      file.write(b'the agent')
    self.cache = Cache(os.path.join(self.folder, 'cache'), fetch=self.refuse)

  @staticmethod
  def refuse(url: str) -> bytes:
    raise OSError('no downloads here: %s' % url)

  def spec(self, text: str) -> InstanceSpec:
    path = os.path.join(self.folder, 'unittas.toml')
    with open(path, 'w', encoding='utf-8') as file:
      file.write(textwrap.dedent(text))
    return InstanceSpec.read(path)

  def multiplayer(self, spec: InstanceSpec):
    launched = RealGame(spec, self.results, 'game', cache=self.cache)
    return session.multiplayerFor(spec, object(), self.results, launched, {})

  def test_26_3_s_server_has_the_agent_in(self) -> None:
    spec = self.spec('''
      minecraft = "26.3"
      client = "real"
      probe = "probe/unittas-probe-26.3.jar"
      window = { display = "plain" }
      [server]
      eula = true
      memory = "3G"
    ''')
    multiplayer = self.multiplayer(spec)
    server = multiplayer.serverFor(('unitTAS', 'bob'))
    self.assertIsInstance(server, ServerGame)
    self.assertEqual(('26.3', self.probe, []),
                     (server.minecraft, server.probe, server.mods))
    self.assertEqual((('unitTAS', 'bob'), True, '3G'),
                     (server.players, server.eula, server.memory))
    self.assertIsNone(server.java, "the version's own Java, found later")
    self.assertEqual((megabytes('3G'), megabytes(MODERN_CLIENT_MEMORY)),
                     (multiplayer.serverMb, multiplayer.clientMb))
    bob = multiplayer.clientFor('bob')
    self.assertIsInstance(bob, RealGame)
    self.assertEqual(('bob', True), (bob.username, bob.built))
    self.assertEqual(os.path.join(self.results, 'client-bob-game'),
                     bob.gameFolder())

  def test_1_7_10_s_clients_at_its_own_client_s_memory(self) -> None:
    spec = self.spec('''
      minecraft = "1.7.10"
      loader = { forge = "10.13.4.1614" }
      client = "real"
      probe = "probe/unittas-probe-26.3.jar"
    ''')
    self.assertEqual(CLIENT_MB, self.multiplayer(spec).clientMb)

  def test_none_for_a_gradle_run(self) -> None:
    spec = self.spec('''
      minecraft = "1.7.10"
      loader = { forge = "10.13.4.1614" }
      client = "gradle"
      [gradle]
      game = "run"
    ''')
    self.assertIsNone(self.multiplayer(spec))


if __name__ == '__main__':
  unittest.main()

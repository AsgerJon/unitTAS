"""
unitTAS's own multiplayer classes (SPEC.md 11.3, step 5): what a run with them must do, in order, by class name.
- AServerTests: alice (the run's own client) and bob on the server; a block the server places is the block bob's
  client sees; the reset puts both at the start; a chat line alice sends reaches bob's chat.
- BFreshTests: a fresh world (a restart): what A placed is gone; it leaves wool.
- CSharedTests (shared_world): the wool B left is there.
- DSingleTests: a singleplayer class after them: the run's own client in its own world again, joined to nothing.
Run only with --multiplayer (three games, about 5 GB). Each waits by ticks, never by the clock.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from unittas.testcase import GameTestCase, MultiplayerTestCase

GOLD = (2, 3, 2)
WOOL = (4, 3, 4)


def seen(test, game, pos, block: str) -> None:
  """The block at pos is that one on the game's client side, within 100 of its ticks: a failure naming what it saw."""
  answer = game.waitUntil('block.get', {'pos': list(pos)}, {'path': ['id'], 'eq': block}, side='client', maxTicks=100)
  test.assertTrue(answer['held'], '%s never showed at %s: it saw %r' % (block, pos, answer['value']))


class AServerTests(MultiplayerTestCase):
  clients = ('alice', 'bob')

  def test_a_both_in(self) -> None:
    players = sorted(player['name'] for player in self.server.players())
    self.assertEqual(sorted([self.alice.playerName(), self.bob.playerName()]), players)
    self.assertEqual('bob', self.bob.playerName())

  def test_b_a_block_bob_sees(self) -> None:
    said = self.server.command('/setblock %d %d %d minecraft:gold_block' % GOLD, as_='server')
    self.assertEqual(1, said.result, said)
    seen(self, self.bob, GOLD, 'minecraft:gold_block')
    seen(self, self.alice, GOLD, 'minecraft:gold_block')

  def test_c_both_at_the_start(self) -> None:
    for game in (self.alice, self.bob):
      pos = game.player(side='client').pos
      self.assertEqual((0.5, 0.5), (pos.x, pos.z), 'reset to the start: %r' % (pos,))

  def test_d_alices_chat_reaches_bob(self) -> None:
    mark = self.bob.mark()
    self.alice.request('chat.send', {'text': 'hello from alice'})
    for _ in range(100):
      if any('hello from alice' in line.plain for line in self.bob.chat(mark)):
        break
      self.bob.ticks(1)
    lines = [line.plain for line in self.bob.chat(mark)]
    self.assertTrue(any('hello from alice' in line and self.alice.playerName() in line for line in lines),
                    "bob's chat: %r" % (lines,))


class BFreshTests(MultiplayerTestCase):
  clients = ('alice', 'bob')

  def test_a_what_a_placed_is_gone(self) -> None:
    seen(self, self.bob, GOLD, 'minecraft:grass')

  def test_b_leaves_wool(self) -> None:
    said = self.server.command('/setblock %d %d %d minecraft:wool 14' % WOOL, as_='server')
    self.assertEqual(1, said.result, said)
    seen(self, self.bob, WOOL, 'minecraft:wool')


class CSharedTests(MultiplayerTestCase):
  clients = ('alice', 'bob')
  shared_world = True

  def test_a_the_wool_b_left(self) -> None:
    seen(self, self.alice, WOOL, 'minecraft:wool')


class DSingleTests(GameTestCase):

  def test_a_its_own_world_again(self) -> None:
    self.assertIsNone(self.game.request('status')['joined'])
    self.assertEqual('minecraft:grass', self.game.block(GOLD).id, "its own world: the server's gold isn't in it")

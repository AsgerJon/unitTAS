"""
unitTAS's own multiplayer classes (SPEC.md 11.3, step 5): what a run with them must do, in order, by class name.
- AServerTests: alice (the run's own client) and bob on the server; a block the server places is the block bob's
  client sees; the reset puts each at its own start (alice at the run's, bob 2 blocks east: two players in one place
  push each other apart in a modern version); a chat line alice sends reaches bob's chat.
- BFreshTests: a fresh world (a restart): what A placed is gone; it leaves wool.
- CSharedTests (shared_world): the wool B left is there.
- DSingleTests: a singleplayer class after them: the run's own client in its own world again, joined to nothing.
Run only with --multiplayer (three games: about 5 GB on 1.7.10, 10 GB on a modern version). Each waits by ticks,
never by the clock. On any version (SPEC.md 19.7 step 10e): its blocks on the flat world's surface under the run's
start, each block by its mcdex member, in the version's own words.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from mcdex import MCBlocks
from unittas.run import Run
from unittas.testcase import GameTestCase, MultiplayerTestCase
from unittas.things import resolve

#  where the classes place their blocks, by x and z: on the flat world's surface (surface)
GOLD = (2, 2)
WOOL = (4, 4)


def surface(at: tuple) -> tuple:
  """A place on the run's flat world's surface, under the start's feet (y 3 in 1.7.10's, -61 from 1.18 on)."""
  return (at[0], int(Run.current.flatStart[1]) - 1, at[1])


def named(test, member) -> str:
  """A block's id in the run's version, as block.get says it."""
  return resolve(member, test.game.version).name


def setblock(test, at: tuple, member) -> str:
  """/setblock on the surface, in the version's words: the block's id, and its meta where it has one (1.7.10's)."""
  thing = resolve(member, test.game.version)
  return '/setblock %d %d %d %s%s' % (surface(at) + (thing.name, ' %d' % thing.meta if thing.hasMeta else ''))


def seen(test, game, pos, block: str) -> None:
  """The block at pos is that one on the game's client side, within 100 of its ticks: a failure naming what it saw."""
  where = list(surface(pos))
  answer = game.waitUntil('block.get', {'pos': where}, {'path': ['id'], 'eq': block}, side='client', maxTicks=100)
  test.assertTrue(answer['held'], '%s never showed at %s: it saw %r' % (block, where, answer['value']))


class AServerTests(MultiplayerTestCase):
  clients = ('alice', 'bob')

  def test_a_both_in(self) -> None:
    players = sorted(player['name'] for player in self.server.players())
    self.assertEqual(sorted([self.alice.playerName(), self.bob.playerName()]), players)
    self.assertEqual('bob', self.bob.playerName())

  def test_b_a_block_bob_sees(self) -> None:
    said = self.server.command(setblock(self, GOLD, MCBlocks.GoldBlock), as_='server')
    self.assertEqual(1, said.result, said)
    seen(self, self.bob, GOLD, named(self, MCBlocks.GoldBlock))
    seen(self, self.alice, GOLD, named(self, MCBlocks.GoldBlock))

  def test_c_both_at_the_start(self) -> None:
    for game, x in ((self.alice, 0.5), (self.bob, 2.5)):
      pos = game.player(side='client').pos
      self.assertEqual((x, 0.5), (pos.x, pos.z), 'reset to its start: %r' % (pos,))

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
    seen(self, self.bob, GOLD, named(self, MCBlocks.GrassBlock))

  def test_b_leaves_wool(self) -> None:
    said = self.server.command(setblock(self, WOOL, MCBlocks.RedWool), as_='server')
    self.assertEqual(1, said.result, said)
    seen(self, self.bob, WOOL, named(self, MCBlocks.RedWool))


class CSharedTests(MultiplayerTestCase):
  clients = ('alice', 'bob')
  shared_world = True

  def test_a_the_wool_b_left(self) -> None:
    seen(self, self.alice, WOOL, named(self, MCBlocks.RedWool))


class DSingleTests(GameTestCase):

  def test_a_its_own_world_again(self) -> None:
    self.assertIsNone(self.game.request('status')['joined'])
    self.assertEqual(named(self, MCBlocks.GrassBlock), self.game.block(surface(GOLD)).id,
                     "its own world: the server's gold isn't in it")

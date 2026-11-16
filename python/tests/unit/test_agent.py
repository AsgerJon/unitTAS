"""
The agent walking (SPEC.md 15.6 step 2), without a game: a fake player
(fakeplayer.py) moves as 1.7.10's does on flat ground. The agent gets
there by a player's inputs alone, the keys and the look, closing the loop
on what it perceives each step. It stops within its margin and lets go of
every key. It walks into reach of a block and looks at it until the
crosshair targets it. A wall in the way, a block it can't target, or the
tick budget spent is a TesttimeError naming what happened.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import math
import random
import shutil
import tempfile
import unittest

from fakeplayer import FakePlayer
from fakeprobe import FakeProbe, inThread
from unittas.agent import Agent
from unittas.api import Game
from unittas.errors import TesttimeError
from unittas.link import Listener
from unittas.values import BlockPos, Vec3
from unittas.wire import Role

#  what a player has: the keys, the look, its senses and its own inventory
PLAYERS_MEANS = {'player.perceive', 'player.look', 'key.down', 'key.up',
                 'key.tap', 'ticks.wait', 'inventory.get', 'container.get',
                 'container.click', 'screen.close'}
#  test_walks_efficiently's forty walks, in ticks: what they took when
#  written (1168), and a tenth more
SPENT = 1285


class PlayedTests(unittest.TestCase):
  """An agent playing a fake player (fakeplayer.py): its tests' base."""

  def setUp(self) -> None:
    folder = tempfile.mkdtemp(prefix='unittas-agent-')
    self.addCleanup(shutil.rmtree, folder, True)
    listener = Listener()
    self.addCleanup(listener.close)
    expected = listener.prepare(folder, 'alice', Role.CLIENT)
    fake = FakeProbe(expected.startFile,
                     extra={'names': 'mcp', 'minecraft': '1.7.10'})
    thread, box = inThread(fake.connect)
    connection = listener.accept(timeout=10)
    thread.join(10)
    self.addCleanup(connection.close)
    self.addCleanup(fake.close)
    self.player = FakePlayer()
    fake.serve(self.player.handlers())
    self.agent = Agent(Game(connection))

  def assertThere(self, place: Vec3, within: float = 0.25) -> None:
    short = math.hypot(place.x - self.player.x, place.z - self.player.z)
    self.assertLessEqual(short, within, 'at %.3f, %.3f' % (
      self.player.x, self.player.z))

  def assertOnlyAPlayersMeans(self) -> None:
    self.assertEqual(set(), set(self.player.ops) - PLAYERS_MEANS)
    self.assertEqual(set(), self.player.keys, 'every key let go')
    self.assertFalse(self.player.flew, 'jump tapped twice: it flew')


class AgentTests(PlayedTests):

  def test_walks_to_a_place_ahead(self) -> None:
    place = Vec3(0.5, 4.0, 8.5)
    seen = self.agent.walkTo(place)
    self.assertThere(place)
    self.assertLess(math.hypot(seen.motion.x, seen.motion.z), 0.01)
    self.assertOnlyAPlayersMeans()

  def test_walks_to_places_behind_and_aside(self) -> None:
    for place in (Vec3(-4.5, 4.0, -6.0), Vec3(7.25, 4.0, -2.0),
                  Vec3(7.0, 4.0, -1.0)):
      with self.subTest(place=place):
        self.agent.walkTo(place)
        self.assertThere(place)
    self.assertOnlyAPlayersMeans()

  def test_closer_margins(self) -> None:
    for place, within in ((Vec3(3.0, 4.0, 5.0), 0.1),
                          (Vec3(3.3, 4.0, 5.2), 0.05),
                          (Vec3(3.1, 4.0, 4.6), 0.05),
                          (Vec3(-1.0, 4.0, 2.0), 0.05)):
      with self.subTest(place=place, within=within):
        self.agent.walkTo(place, within=within)
        self.assertThere(place, within)

  def test_walks_straight(self) -> None:
    """It turns to its goal, though it looks almost that way already."""
    place = Vec3(2.5, 4.0, 12.5)
    self.agent.walkTo(place)
    #  the line from the start to the place, and each tick's way off it
    lx, lz = place.x - 0.5, place.z - 0.5
    length = math.hypot(lx, lz)
    off = [abs((x - 0.5) * lz - (z - 0.5) * lx) / length
           for x, z in self.player.trail]
    self.assertLessEqual(max(off), 0.1)

  def test_walks_efficiently(self) -> None:
    """Forty walks, near and far, close and loose, in a fixed tick count."""
    chance = random.Random(11)
    spent = 0
    for _ in range(40):
      far = chance.choice((0.2, 0.5, 1.0, 2.0, 5.0, 12.0))
      angle = chance.uniform(0.0, 2 * math.pi)
      place = Vec3(self.player.x + far * math.cos(angle), 4.0,
                   self.player.z + far * math.sin(angle))
      within = chance.choice((0.05, 0.1, 0.25, 0.5))
      before = self.player.tick
      self.agent.walkTo(place, within=within)
      self.assertThere(place, within)
      spent += self.player.tick - before
    self.assertLessEqual(spent, SPENT)

  def test_a_place_up_in_the_air(self) -> None:
    with self.assertRaises(TesttimeError) as raised:
      self.agent.walkTo(Vec3(0.5, 7.0, 3.5))
    self.assertIn('no way to (0.50, 7.00, 3.50)', str(raised.exception))
    self.assertEqual({'player.perceive'}, set(self.player.ops))

  def test_a_block_position_is_its_floor_s_middle(self) -> None:
    self.agent.walkTo(BlockPos(-3, 4, 4))
    self.assertThere(Vec3(-2.5, 4.0, 4.5))

  def test_where_it_stands_already(self) -> None:
    self.agent.walkTo(Vec3(0.5, 4.0, 0.5))
    self.assertNotIn('key.down', self.player.ops)

  def test_blocked_by_what_it_didn_t_see(self) -> None:
    """A wall it couldn't see when it set off (raised after its look)."""
    walls = self.player.walls
    seen = []

    def perceived(around: int) -> dict:
      answer = original(around)
      if not seen:
        seen.append(True)
        for x in range(-12, 13):
          for y in (4, 5):
            walls[(x, y, 3)] = 'minecraft:stone'
      return answer

    original = self.player.perceived
    self.player.perceived = perceived
    with self.assertRaises(TesttimeError) as raised:
      self.agent.walkTo(Vec3(0.5, 4.0, 6.5))
    message = str(raised.exception)
    self.assertIn('blocked by minecraft:stone at (0, 4, 3)', message)
    self.assertEqual('walkTo', raised.exception.step)
    self.assertTrue(raised.exception.seen.collidedHorizontally)
    self.assertOnlyAPlayersMeans()

  def test_slides_past_a_corner(self) -> None:
    """
    Running into the side of a block it didn't see when it set off, and
    sliding on along it, isn't blocked.
    """
    walls, seen = self.player.walls, []
    original = self.player.perceived

    def perceived(around: int) -> dict:
      answer = original(around)
      if not seen:
        seen.append(True)
        for y in (4, 5):
          walls[(3, y, 3)] = 'minecraft:stone'
      return answer

    self.player.perceived = perceived
    place = Vec3(6.5, 4.0, 6.5)
    self.agent.walkTo(place)
    self.assertThere(place)
    self.assertGreater(self.player.bumps, 0, 'it ran into the block')

  def test_the_budget_spent(self) -> None:
    with self.assertRaises(TesttimeError) as raised:
      self.agent.walkTo(Vec3(0.5, 4.0, 20.5), ticks=10)
    self.assertIn('tick budget (10) is spent', str(raised.exception))
    self.assertOnlyAPlayersMeans()

  def test_into_reach_and_looking_at_a_block(self) -> None:
    self.player.walls[(9, 4, 12)] = 'minecraft:wool'
    block = BlockPos(9, 4, 12)
    seen = self.agent.reach(block)
    centre = Vec3(9.5, 4.5, 12.5)
    far = math.dist((seen.eye.x, seen.eye.y, seen.eye.z),
                    (centre.x, centre.y, centre.z))
    self.assertLessEqual(far, seen.blockReach - 1.0 + 0.3)
    self.assertGreater(far, 2.0, 'it stopped short of the block')
    looked = self.agent.lookAt(block)
    self.assertEqual('block', looked.target.kind)
    self.assertEqual(block, looked.target.pos)
    self.assertOnlyAPlayersMeans()

  def test_a_face_when_the_middle_is_hidden(self) -> None:
    """A low block hides the wool's middle, not its top."""
    self.player.z = 1.5
    self.player.walls[(0, 4, 5)] = 'minecraft:wool'
    self.player.walls[(0, 4, 4)] = 'minecraft:stone'
    looked = self.agent.lookAt(BlockPos(0, 4, 5))
    self.assertEqual(BlockPos(0, 4, 5), looked.target.pos)
    self.assertEqual('up', looked.target.face)

  def test_a_block_it_can_t_target(self) -> None:
    #  a wool block behind a stone one, in reach
    self.player.walls[(0, 5, 4)] = 'minecraft:wool'
    for x in (-1, 0, 1):
      for y in (4, 5, 6):
        self.player.walls[(x, y, 3)] = 'minecraft:stone'
    with self.assertRaises(TesttimeError) as raised:
      self.agent.lookAt(BlockPos(0, 5, 4))
    message = str(raised.exception)
    self.assertIn('lookAt', message)
    self.assertIn('minecraft:stone at (0, 5, 3)', message)

  def test_a_block_out_of_reach(self) -> None:
    self.player.walls[(0, 4, 12)] = 'minecraft:wool'
    with self.assertRaises(TesttimeError) as raised:
      self.agent.lookAt(BlockPos(0, 4, 12))
    self.assertIn('out of reach', str(raised.exception))

  def test_mistakes_are_refused(self) -> None:
    with self.assertRaises(TypeError):
      self.agent.walkTo((0.5, 4.0, 0.5))
    with self.assertRaisesRegex(ValueError, 'least step'):
      self.agent.walkTo(Vec3(0.5, 4.0, 3.5), within=0.04)
    with self.assertRaises(ValueError):
      self.agent.walkTo(Vec3(0.5, 4.0, 3.5), ticks=0)

  def test_jump_never_tapped_twice_quickly(self) -> None:
    """
    Jump pressed again within 7 ticks makes creative's player fly: the
    agent leaves it up until JUMP_AGAIN ticks have passed (its own
    helper, as no walk of today's presses it so soon).
    """
    self.agent.perceive()
    self.agent._hold('key.jump', True)
    self.agent._hold('key.jump', False)
    self.agent._hold('key.jump', True)
    self.assertEqual(['key.jump'], self.player.keysAsked)
    self.agent.wait(Agent.JUMP_AGAIN)
    self.agent.perceive()
    self.agent._hold('key.jump', True)
    self.agent.letGo()
    self.assertEqual(['key.jump'] * 2, self.player.keysAsked)
    self.assertFalse(self.player.flew)


if __name__ == '__main__':
  unittest.main()

"""
The 'self' suite's twins (src/self/java/.../self/*.java), by the same names: every one must pass. StepTests stays
Java's own: it forces a race inside the JVM's step queue, which no request over the socket can. Each waits by ticks,
never by the clock (SPEC.md 9.8).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import time

from unittas.run import Run
from unittas.testcase import GameTestCase
from unittas.values import Block, Item

SELF_PLUGIN = 'io.github.asgerjon.unittas.self.SelfPlugin'


def waitTicks(test: GameTestCase, holds, ticks: int, what: str) -> None:
  """Until holds() is true, a client tick at a time, for at most that many ticks: a failure naming what never came."""
  for _ in range(ticks):
    if holds():
      return
    test.game.ticks(1)
  if not holds():
    test.fail('%s never came in %d ticks' % (what, ticks))


class ChatTests(GameTestCase):

  def testTypedTextIsRead(self) -> None:
    self.game.openScreen('chat')
    self.game.type('/time se')
    self.assertEqual('/time se', self.game.request('chat.read')['text'])
    self.game.closeScreen()

  def testTabCompletesFromTheServer(self) -> None:
    self.game.openScreen('chat')
    self.game.type('/tim')
    self.game.key('tab')
    read = self.game.request('chat.read')
    self.assertEqual('/time', read['text'])
    self.assertIn('/time', read['suggestions'])
    self.game.closeScreen()

  def testEnterRunsTheCommand(self) -> None:
    self.game.openScreen('chat', text='/time set 6000')
    self.game.key('enter')
    waitTicks(self, lambda: any('Set the time to 6000' in line.plain for line in self.chat()), 40, 'the answer')


class ClassFixtureTests(GameTestCase):
  #  where setUpClass builds: away from the spawn point and the other tests' ground
  X, Y, Z = 40, 4, 40
  #  setUpClass's count in each run, by the run: one Python process can hold several runs (the probe's tests run this
  #  suite in a development client and then in a real one), and a class's own state outlives a run
  setUps = {}

  @classmethod
  def setUpClass(cls) -> None:
    super().setUpClass()
    ClassFixtureTests.setUps[Run.current] = ClassFixtureTests.setUps.get(Run.current, 0) + 1
    cls.game.setBlock((cls.X, cls.Y, cls.Z), 'minecraft:gold_block')

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.setBlock((cls.X, cls.Y, cls.Z), 'minecraft:air')
    super().tearDownClass()

  def testA_setUpClassRanBeforeTheFirstTest(self) -> None:
    self.assertEqual(1, ClassFixtureTests.setUps[Run.current])
    self.assertEqual('minecraft:gold_block', self.game.block((self.X, self.Y, self.Z)).id,
                     'what setUpClass built is gone')

  def testB_andNotAgainBeforeTheNext(self) -> None:
    self.assertEqual(1, ClassFixtureTests.setUps[Run.current])
    self.assertEqual('minecraft:gold_block', self.game.block((self.X, self.Y, self.Z)).id,
                     'the reset took what setUpClass built')


class MixinTests(GameTestCase):

  def testWindowTitle(self) -> None:
    self.assertEqual('unitTAS', self.game.status()['window']['title'])

  def testPointerLeftFree(self) -> None:
    self.game.reflect(['mouseHelper', {'call': 'grabMouseCursor'}], source='minecraft', side='client')
    self.game.ticks(2)
    self.assertFalse(self.game.status()['window']['pointer_grabbed'], 'the game took the mouse pointer')

  def testSoundHeard(self) -> None:
    self.game.request('sound.play', {'id': 'minecraft:gui.button.press'})
    waitTicks(self, lambda: any(sound.id == 'minecraft:gui.button.press' for sound in self.sounds()), 20,
              'the sound')


class ResetContainerTests(GameTestCase):

  def testA_leavesTheCreativeInventoryOpen(self) -> None:
    self.game.openScreen('creative')
    self.game.ticks(2)
    self.assertFalse(self.game.request('container.get', side='client')['player_own'],
                     "the creative inventory didn't open its container")

  def testB_bootsReachTheClient(self) -> None:
    self.assertTrue(self.game.request('container.get', side='client')['player_own'],
                    'the reset left the client\'s container open')
    self.game.setSlot('armor.feet', Item('minecraft:leather_boots', 1, 0))
    waitTicks(self, lambda: not self.game.slot('armor.feet', side='client').empty, 40, "the boots on the client's feet")


class ResetTests(GameTestCase):

  def testA_leavesThePlayerFlyingWithExperience(self) -> None:
    # in the air: a player standing on the ground stops flying at once (1.7.10's own rule, on the client)
    self.game.teleport((0.5, 8.0, 0.5))
    self.game.reflectSet(['capabilities', 'isFlying'], True)
    self.game.reflect([{'call': 'sendPlayerAbilities'}])
    self.game.reflect([{'call': 'addExperienceLevel', 'args': [5]}])
    waitTicks(self, lambda: self.game.player(side='client').xpLevel == 5, 40, 'the client showing level 5')
    waitTicks(self, lambda: self.game.player(side='client').flying, 40, 'the client flying')

  def testB_startsGroundedWithNoExperience(self) -> None:
    self.assertFalse(self.game.player().flying, 'still flying on the server')
    self.assertEqual(0, self.game.player().xpLevel)
    waitTicks(self, lambda: not self.game.player(side='client').flying and self.game.player(side='client').xpLevel == 0,
              40, 'the client grounded at level 0')


class SlowGameTests(GameTestCase):
  TICKS = 25

  def testServerTicksOnASlowServer(self) -> None:
    # a second a server tick: 25 of them take 25 s, past the stall rule's 15 s, and that's fine: it ticks
    self.game.request('debug.lag', {'ms': 1000, 'ticks': self.TICKS}, side='server')
    start = time.monotonic()
    self.game.ticks(self.TICKS, side='server', timeout=120)
    took = time.monotonic() - start
    # a lower bound only, which slowness can't break: the server was slow, and the wait waited for it
    self.assertGreater(took, self.TICKS * 0.05 + 15 + 2, "the server wasn't slow enough to show it")


class WorldFreshATests(GameTestCase):
  X, Y, Z = 60, 4, 60
  world = 0

  def testLeavesABlock(self) -> None:
    WorldFreshATests.world = self.worldNumber()
    self.game.setBlock((self.X, self.Y, self.Z), 'minecraft:stone')
    self.assertEqual('minecraft:stone', self.game.block((self.X, self.Y, self.Z)).id)


class WorldFreshBTests(GameTestCase):

  def testFindsAFreshWorld(self) -> None:
    self.assertEqual(Block('minecraft:air', 0),
                     self.game.block((WorldFreshATests.X, WorldFreshATests.Y, WorldFreshATests.Z)),
                     'the block WorldFreshATests left is still there')
    self.assertEqual(WorldFreshATests.world + 1, self.worldNumber(), "not the world after WorldFreshATests's")
    if self.game.connection.hello.development:
      # SelfPlugin is the self source set's: in a development client only (the release jar doesn't carry it)
      plugin = {'class': SELF_PLUGIN}
      self.assertEqual(self.worldNumber(), self.game.reflect(['worldsSetUp'], source=plugin),
                       "setUpWorld didn't run for every world")
      self.assertEqual(self.worldNumber() - 1, self.game.reflect(['worldsTornDown'], source=plugin),
                       "tearDownWorld didn't run for every closed world")

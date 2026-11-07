"""
The 'self-red' suite's twins (src/self/java/.../self/Red*.java), by the same names: each comes out as
bin/self_red_check.py expects, on purpose. RedTests.testWarnsOutsideAStep stays Java's own: its warning is the Java
helpers' (player() outside a server step), which Python has no way to do.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import unittest

from unittas.run import Run
from unittas.testcase import GameTestCase

#  As RedTests.CONFIG_MARK and CONFIG_MADE (and bin/self_red_check.py's): appended to forge.cfg, a file made beside it;
#  both gone once the run has put the config back
CONFIG_MARK = "# changed by unitTAS's self-red run"
CONFIG_MADE = 'unittas-red.cfg'


@unittest.expectedFailure
class RedClassTests(GameTestCase):
  """The whole class is marked."""

  def testFailsUnderAClassMark(self) -> None:
    self.fail('on purpose')


class RedSetUpClassTests(GameTestCase):

  @classmethod
  def setUpClass(cls) -> None:
    super().setUpClass()
    raise RuntimeError('setUpClass fails on purpose')

  def testNeverRuns(self) -> None:
    self.fail('setUpClass failed: this test should not have run')


class RedSetUpTests(GameTestCase):

  def setUp(self) -> None:
    raise RuntimeError('setUp fails on purpose')

  @unittest.expectedFailure
  def testNeverRuns(self) -> None:
    self.fail('setUp should have stopped this test')


class RedSkipClassTests(GameTestCase):

  @classmethod
  def setUpClass(cls) -> None:
    super().setUpClass()
    raise unittest.SkipTest('the whole class is skipped')

  def testA_skipped(self) -> None:
    self.fail('setUpClass skipped the class: this test should not have run')

  def testB_skippedToo(self) -> None:
    self.fail('setUpClass skipped the class: this test should not have run')


class RedTearDownClassTests(GameTestCase):
  #  by the run, as ClassFixtureTests counts: a class's own state outlives a run
  testsRun = {}

  @classmethod
  def tearDownClass(cls) -> None:
    if RedTearDownClassTests.testsRun.get(Run.current) != 2:
      raise AssertionError('tearDownClass came before the class\'s tests were done')
    raise RuntimeError('tearDownClass fails on purpose, after both tests')

  def testA_runs(self) -> None:
    RedTearDownClassTests.testsRun[Run.current] = RedTearDownClassTests.testsRun.get(Run.current, 0) + 1

  def testB_runsToo(self) -> None:
    RedTearDownClassTests.testsRun[Run.current] = RedTearDownClassTests.testsRun.get(Run.current, 0) + 1


class RedTests(GameTestCase):

  @unittest.expectedFailure
  def testExpectedAssertion(self) -> None:
    self.assertEqual(1, 2)

  @unittest.expectedFailure
  def testExpectedException(self) -> None:
    raise RuntimeError('thrown on purpose')

  @unittest.expectedFailure
  def testUnexpectedSuccess(self) -> None:
    self.assertEqual(1, 1)

  def testLeavesTheConfigChanged(self) -> None:
    config = os.path.join(Run.current.gameDir, 'config')
    with open(os.path.join(config, 'forge.cfg'), 'a', encoding='utf-8') as file:
      file.write('\n' + CONFIG_MARK + '\n')
    with open(os.path.join(config, CONFIG_MADE), 'w', encoding='utf-8') as file:
      file.write("made by unitTAS's self-red run\n")


class RedWorldLeavesTests(GameTestCase):
  X, Y, Z = 70, 4, 70
  #  the world it ran in (not "world": that is the class's own world, when it asks for one)
  worldSeen = 0

  def testLeavesABlock(self) -> None:
    RedWorldLeavesTests.worldSeen = self.worldNumber()
    self.game.setBlock((self.X, self.Y, self.Z), 'minecraft:stone')


class RedWorldSharedTests(GameTestCase):
  shared_world = True

  def testFindsWhatTheClassBeforeLeft(self) -> None:
    self.assertEqual(RedWorldLeavesTests.worldSeen, self.worldNumber(), 'not the world RedWorldLeavesTests ran in')
    self.assertEqual('minecraft:stone',
                     self.game.block((RedWorldLeavesTests.X, RedWorldLeavesTests.Y, RedWorldLeavesTests.Z)).id,
                     'the block RedWorldLeavesTests left is gone')

"""
A small suite of GameTestCases for test_runs.py (and test_specgames.py) to run on the run's port: not a test module
(the probe's discovery doesn't load it). Things by mcdex member, places from the port's start. A fresh world for each
class but the shared one, the levels' own checks:

- AFreshTests leaves a gold block in its world;
- BFreshTests finds it gone (a fresh world) and leaves wool;
- CSharedTests (shared_world) finds the wool BFreshTests left;
- DChatTests reads its own chat, and fails once on purpose (its screenshot is checked).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from mcdex import MCBlocks, MCItems

from ports import at, command
from unittas.testcase import GameTestCase
from unittas.things import itemOf


def gold():
  """Where AFreshTests leaves its gold, on the port's flat world."""
  return at(10, 4, 10)


def wool():
  """Where BFreshTests leaves its wool."""
  return at(12, 4, 12)


class AFreshTests(GameTestCase):

  def test_leaves_a_gold_block(self) -> None:
    self.game.setBlock(gold(), MCBlocks.GoldBlock)
    self.assertEqual('minecraft:gold_block', self.game.block(gold()).id)


class BFreshTests(GameTestCase):

  def test_finds_it_gone_and_leaves_wool(self) -> None:
    self.assertEqual('minecraft:air', self.game.block(gold()).id, 'a fresh world: what AFreshTests left is gone')
    self.game.setBlock(wool(), MCBlocks.RedWool)


class CSharedTests(GameTestCase):
  shared_world = True

  def test_finds_the_wool(self) -> None:
    self.assertThing(self.game.block(wool()), MCBlocks.RedWool, 'a shared world: as BFreshTests left it')


class DChatTests(GameTestCase):

  def test_a_its_own_chat(self) -> None:
    said = self.command(command('one red wool'))
    self.assertEqual(1, said.result)
    self.assertTrue(any('Red Wool' in line.plain for line in self.chat()))
    self.assertEqual(itemOf(MCItems.RedWool, self.game.version, 1), self.held())

  def test_b_fails_on_purpose(self) -> None:
    self.assertEqual(itemOf(MCItems.RedWool, self.game.version, 1).id, self.held().id,
                     'the held item was reset: on purpose, this fails')

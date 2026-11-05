"""
A small suite of GameTestCases for test_runs.py to run in the development client: not a test module (the probe's
discovery doesn't load it). A fresh world for each class but the shared one, the levels' own checks:

- AFreshTests leaves a gold block in its world;
- BFreshTests finds it gone (a fresh world) and leaves wool;
- CSharedTests (shared_world) finds the wool BFreshTests left;
- DChatTests reads its own chat, and fails once on purpose (its screenshot is checked).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from unittas.testcase import GameTestCase
from unittas.values import Block, Item

GOLD = (10, 4, 10)
WOOL = (12, 4, 12)


class AFreshTests(GameTestCase):

  def test_leaves_a_gold_block(self) -> None:
    self.game.setBlock(GOLD, 'minecraft:gold_block')
    self.assertEqual('minecraft:gold_block', self.game.block(GOLD).id)


class BFreshTests(GameTestCase):

  def test_finds_it_gone_and_leaves_wool(self) -> None:
    self.assertEqual(Block('minecraft:air', 0), self.game.block(GOLD), 'a fresh world: what AFreshTests left is gone')
    self.game.setBlock(WOOL, Block('minecraft:wool', 14))


class CSharedTests(GameTestCase):
  shared_world = True

  def test_finds_the_wool(self) -> None:
    self.assertEqual(Block('minecraft:wool', 14), self.game.block(WOOL), 'a shared world: as BFreshTests left it')


class DChatTests(GameTestCase):

  def test_a_its_own_chat(self) -> None:
    said = self.command('/give @p wool 1 14')
    self.assertEqual(1, said.result)
    self.assertTrue(any('Red Wool' in line.plain for line in self.chat()))
    self.assertEqual(Item('minecraft:wool', 1, 14), self.held())

  def test_b_fails_on_purpose(self) -> None:
    self.assertEqual('minecraft:wool', self.held().id, 'the held item was reset: on purpose, this fails')

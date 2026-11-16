"""
A scenario's class for test_scenarios.py to run on a Run (SPEC.md 15.6
step 5): not a test module (unittest's discovery doesn't load it). Its
setup is by command; its actions are the agent's; its examinations are
by command, and noted under its tests' report lines.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from mcdex import MCBlocks, MCItems

from unittas.scenario import ScenarioTestCase
from unittas.values import Block

#  1.7.10's chest with three pink wool in its first slot
WITH_WOOL = '{Items:[{Slot:0b,id:35s,Count:3b,Damage:6s}]}'


class SceneTests(ScenarioTestCase):

  @classmethod
  def setUpClass(cls) -> None:
    super().setUpClass()
    cls.scene.place(Block('minecraft:lever', 5), at=(5, 0, 7))
    chest = cls.scene.at((3, 0, 5))
    cls.game.request('block.set', {
      'pos': [chest.x, chest.y, chest.z],
      'block': {'id': 'minecraft:chest', 'meta': 2}, 'tile': WITH_WOOL})

  def test_a_the_lever(self) -> None:
    lever = self.scene.thing(MCBlocks.Lever, at=(5, 0, 7))
    self.assertFalse(lever.isOn())
    lever.activate()
    self.assertTrue(lever)

  def test_b_the_chest(self) -> None:
    chest = self.scene.thing(MCBlocks.Chest, at=(3, 0, 5))
    self.assertIn(MCItems.PinkWool, chest.contents())
    chest.open()
    self.agent.take(MCItems.PinkWool)
    self.agent.close()
    self.assertNotIn(MCItems.PinkWool, chest.contents())

  def test_c_a_block_broken(self) -> None:
    stone = self.scene.place(MCBlocks.Stone, at=(2, 0, 3))
    self.assertTrue(stone.isThere())
    stone.breakIt()
    self.assertFalse(stone.isThere())

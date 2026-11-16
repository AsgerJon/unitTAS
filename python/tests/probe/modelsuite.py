"""
The model scenario (SPEC.md 15.3, 15.6 step 8), for test_model.py to run
on a Run: not a test module (unittest's discovery doesn't load it). A
line of hoppers points into a chest; a chest of pink wool sits on the
furthest, and a lever beside it, on, locks that one. The agent turns
the lever off, and the wool goes down the line into the chest; then it
takes the wool out. Left alone, the wool stays (the lock holds). Its
setup is by command; its actions are the agent's; its examinations are
by command, and noted under its tests' report lines (what the agent
knows of its own inventory too). README.md shows it as the example of a
scenario.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from mcdex import MCBlocks, MCItems

from unittas.scenario import ScenarioTestCase
from unittas.values import Block

#  The lever, and the chest the hoppers fill: from the start's block
A = (4, 0, 6)
B = (0, 0, 6)
#  1.7.10's chest with one pink wool
WOOL = '{Items:[{Slot:0b,id:35s,Count:1b,Damage:6s}]}'


class LeverAndChestTests(ScenarioTestCase):

  @classmethod
  def setUpClass(cls) -> None:
    super().setUpClass()
    #  1.7.10's blocks as the game keeps them: a chest faces south (3),
    #  a hopper west (4) points into the block west of it, a lever on
    #  the ground is 5, and 8 more when on
    cls.scene.place(Block('minecraft:chest', 3), at=B)
    for x in (1, 2, 3):
      cls.scene.place(Block('minecraft:hopper', 4), at=(x, 0, 6))
    #  on before the wool is there: the furthest hopper is locked
    cls.scene.place(Block('minecraft:lever', 13), at=A)
    cls.scene.place(Block('minecraft:chest', 3, True, WOOL), at=(3, 1, 6))

  def test_0_locked(self) -> None:
    """Left alone, the wool stays where it is: the lock holds."""
    self.agent.wait(40)
    above = self.scene.thing(MCBlocks.Chest, at=(3, 1, 6))
    self.assertIn(MCItems.PinkWool, above.contents())

  def test_a_the_wool_let_through(self) -> None:
    leverA = self.scene.thing(MCBlocks.Lever, at=A)
    chestB = self.scene.thing(MCBlocks.Chest, at=B)
    self.assertNotIn(MCItems.PinkWool, chestB.contents())
    if leverA.isOn():
      leverA.activate()
    #  a hopper passes an item on every 8 ticks: three of them
    self.agent.wait(40)
    self.assertFalse(leverA)
    self.assertIn(MCItems.PinkWool, chestB.contents())

  def test_b_the_wool_taken(self) -> None:
    chestB = self.scene.thing(MCBlocks.Chest, at=B)
    self.assertNotIn(MCItems.PinkWool, self.agent.inventory())
    chestB.open()
    self.agent.take(MCItems.PinkWool)
    self.agent.close()
    self.assertIn(MCItems.PinkWool, self.agent.inventory())
    self.assertNotIn(MCItems.PinkWool, chestB.contents())

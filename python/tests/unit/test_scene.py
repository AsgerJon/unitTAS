"""
A scenario's scene (SPEC.md 15.3, 15.6 step 5), without a game: things
placed relative to the scene's origin by command (setup, not the agent);
each thing's verbs carried out by the agent as a player; its state
examined by command, the default, each examination noted for the test's
report line (and given to the run when there is one). What a thing can't
be examined for is the test author's mistake (TypeError); a thing that
isn't there is the test's FAIL (NeedFailed).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import unittest

from mcdex import MCBlocks, MCItems

from test_agent import PlayedTests
from unittas.errors import NeedFailed
from unittas.run import Run
from unittas.scene import Scene
from unittas.values import Block, BlockPos, Item

LEVER = Block('minecraft:lever', 5)
WOOL = {'id': 'minecraft:wool', 'count': 3, 'meta': 6}


class _Noted:
  """A run, as far as notes go."""

  def __init__(self) -> None:
    self.notes = []

  def note(self, text: str) -> None:
    self.notes.append(text)


class SceneTests(PlayedTests):

  def setUp(self) -> None:
    PlayedTests.setUp(self)
    self.scene = Scene(self.agent, BlockPos(0, 4, 0))

  def test_places_relative_to_its_origin(self) -> None:
    lever = self.scene.place(LEVER, at=(5, 0, 7))
    self.assertEqual(BlockPos(5, 4, 7), lever.pos)
    self.assertIs(MCBlocks.Lever, lever.member)
    self.assertEqual('minecraft:lever', self.player.walls[(5, 4, 7)])
    stone = self.scene.place(MCBlocks.Stone, at=BlockPos(1, 1, 2))
    self.assertEqual(BlockPos(1, 5, 2), stone.pos)
    self.assertEqual('MCBlocks.Stone at (1, 5, 2)', stone.label())
    found = self.scene.thing(MCBlocks.Lever, at=(5, 0, 7))
    self.assertEqual(lever.pos, found.pos)
    self.assertEqual([], self.player.clicks, 'setup is not the agent')

  def test_a_lever_activated_and_examined(self) -> None:
    lever = self.scene.place(LEVER, at=(5, 0, 7))
    self.assertFalse(lever.isOn())
    lever.activate()
    self.assertEqual([('use', (5, 4, 7))], self.player.clicks)
    self.assertTrue(lever.isOn())
    self.assertTrue(lever)
    said = 'examined by command: MCBlocks.Lever at (5, 4, 7), isOn: %s'
    self.assertEqual([said % False, said % True, said % True],
                     list(self.scene.notes))

  def test_a_chest_s_contents(self) -> None:
    chest = self.scene.place(MCBlocks.Chest, at=(3, 0, 5))
    self.assertEqual(frozenset(), chest.contents())
    self.player.chests[(3, 4, 5)][4] = WOOL
    self.assertIn(MCItems.PinkWool, chest.contents())
    stacks = chest.stacks()
    self.assertEqual((Item('minecraft:wool', 3, 6),),
                     tuple(each for each in stacks if not each.empty))
    self.assertEqual(
      ['examined by command: MCBlocks.Chest at (3, 4, 5), contents: nothing',
       'examined by command: MCBlocks.Chest at (3, 4, 5), contents: '
       'MCItems.PinkWool',
       'examined by command: MCBlocks.Chest at (3, 4, 5), stacks: 3 '
       'minecraft:wool:6'], list(self.scene.notes))
    shown = chest.open()
    self.assertFalse(shown.playerOwn)

  def test_broken_and_gone(self) -> None:
    stone = self.scene.place(MCBlocks.Stone, at=(3, 0, 6))
    self.assertTrue(stone.isThere())
    stone.breakIt()
    self.assertFalse(stone.isThere())
    self.assertEqual(
      ['examined by command: MCBlocks.Stone at (3, 4, 6), isThere: True',
       'examined by command: MCBlocks.Stone at (3, 4, 6), isThere: False'],
      list(self.scene.notes))

  def test_what_a_thing_can_t_be_examined_for(self) -> None:
    chest = self.scene.place(MCBlocks.Chest, at=(3, 0, 5))
    with self.assertRaisesRegex(TypeError, 'minecraft:chest has no on'):
      chest.isOn()
    lever = self.scene.place(LEVER, at=(5, 0, 7))
    with self.assertRaisesRegex(NeedFailed, 'holds nothing'):
      lever.contents()
    self.player.walls.pop((5, 4, 7))
    with self.assertRaisesRegex(NeedFailed, "isn't there: minecraft:air"):
      lever.isOn()

  def test_a_thing_observed(self) -> None:
    stone = self.scene.place(MCBlocks.Stone, at=(3, 0, 6))
    view = stone.examine(side='west')
    self.assertEqual(stone.pos, view.pos)
    self.assertEqual({'west': 256}, view.faces)

  def test_notes_go_to_the_run(self) -> None:
    noted = _Noted()
    Run.current = noted
    self.addCleanup(setattr, Run, 'current', None)
    stone = self.scene.place(MCBlocks.Stone, at=(3, 0, 6))
    stone.isThere()
    self.assertEqual(
      ['examined by command: MCBlocks.Stone at (3, 4, 6), isThere: True'],
      noted.notes)

  def test_the_agent_waits(self) -> None:
    before = self.player.tick
    self.agent.wait(5)
    self.assertEqual(before + 5, self.player.tick)


if __name__ == '__main__':
  unittest.main()

"""
A scenario's scene (SPEC.md 15.3, 15.6 step 5), without a game: things
placed relative to the scene's origin by command (setup, not the agent);
each thing's verbs carried out by the agent as a player; its state
examined by command, the default, each examination noted for the test's
report line (and given to the run when there is one). What a thing can't
be examined for is the test author's mistake (TypeError); a thing that
isn't there is the test's FAIL (NeedFailed). From 1.13 on a thing's on or
off is its block state's (powered, lit, power), read by command too.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import unittest

from mcdex import MCBlocks, MCItems, Version

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
    #  each place verified, on the server and on the client
    self.assertEqual(4, self.player.ops.count('wait.until'))

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

  def test_a_thing_identified(self) -> None:
    furnace = self.scene.place(Block('minecraft:furnace', 2), at=(3, 0, 6))
    self.assertIs(MCBlocks.Furnace, furnace.identify(
      among=[MCBlocks.Furnace, MCBlocks.Stone]))

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



class _Game26:
  """A 26.3 game, as far as a thing's state goes: its blocks by place."""

  version = Version.V26_3

  def __init__(self, block: Block) -> None:
    self.blocks = {BlockPos(1, 2, 3): block}

  def block(self, pos: BlockPos, tile: bool = False,
            side: object = None) -> Block:
    return self.blocks[pos]


class _Agent26:
  """An agent, as far as a scene asks it: its game."""

  def __init__(self, block: Block) -> None:
    self.game = _Game26(block)


def _state(id_: str, **state: str) -> Block:
  return Block(id_, -1, state=tuple(sorted(state.items())))


class OnOffByStateTests(unittest.TestCase):
  """From 1.13 on: powered, lit, or power above 0."""

  def isOn(self, member: object, block: Block) -> bool:
    scene = Scene(_Agent26(block), BlockPos(0, 0, 0))
    return scene.thing(member, at=(1, 2, 3)).isOn()

  def test_a_lever_s_powered(self) -> None:
    lever = dict(face='floor', facing='north')
    self.assertTrue(self.isOn(MCBlocks.Lever, _state(
      'minecraft:lever', powered='true', **lever)))
    self.assertFalse(self.isOn(MCBlocks.Lever, _state(
      'minecraft:lever', powered='false', **lever)))

  def test_a_lamp_s_lit(self) -> None:
    self.assertTrue(self.isOn(MCBlocks.RedstoneLamp, _state(
      'minecraft:redstone_lamp', lit='true')))
    self.assertFalse(self.isOn(MCBlocks.RedstoneLamp, _state(
      'minecraft:redstone_lamp', lit='false')))

  def test_a_weighted_plate_s_power(self) -> None:
    plate = 'minecraft:light_weighted_pressure_plate'
    self.assertTrue(self.isOn(MCBlocks.LightWeightedPressurePlate,
                              _state(plate, power='3')))
    self.assertFalse(self.isOn(MCBlocks.LightWeightedPressurePlate,
                               _state(plate, power='0')))

  def test_a_block_with_no_on_or_off(self) -> None:
    chest = _state('minecraft:chest', facing='north', type='single',
                   waterlogged='false')
    with self.assertRaisesRegex(TypeError, 'minecraft:chest has no on'):
      self.isOn(MCBlocks.Chest, chest)


if __name__ == '__main__':
  unittest.main()

"""
The agent saying what a block is from its looks alone (SPEC.md 15.4's
identify, 15.6 step 6), without a game: a fake player whose views draw a
block's faces from its textures, and whose game answers block.faces and
texture.get as the running game does. Views from each side it can see
the block from, each face squared up and compared with each candidate's
faces (each variant: a furnace's facings); the best beats the next by
the margin, or a TesttimeError says the scores. Two candidates that look
the same are said so; air is known by touch.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import shutil
import tempfile
import unittest

from mcdex import MCBlocks

from fakeplayer import LOOKS
from test_agent import PlayedTests
from unittas.agent import Agent
from unittas.errors import Missing, TesttimeError
from unittas.run import Run
from unittas.values import BlockPos

PLACE = BlockPos(3, 4, 6)


class _Noted:
  """A run, as far as notes go."""

  def __init__(self) -> None:
    self.notes = []

  def note(self, text: str) -> None:
    self.notes.append(text)


class IdentifyTests(PlayedTests):

  def setUp(self) -> None:
    PlayedTests.setUp(self)
    folder = tempfile.mkdtemp(prefix='unittas-identify-')
    self.addCleanup(shutil.rmtree, folder, True)
    self.agent = Agent(self.agent.game, frames=folder)

  def put(self, block: str, meta: int = 0) -> None:
    self.player.walls[(3, 4, 6)] = block
    self.player.metas[(3, 4, 6)] = meta

  def test_stone_among_all(self) -> None:
    self.put('minecraft:stone')
    noted = _Noted()
    Run.current = noted
    self.addCleanup(setattr, Run, 'current', None)
    self.assertIs(MCBlocks.Stone, self.agent.identify(PLACE))
    said = [line for line in noted.notes if line.startswith('identified')]
    self.assertEqual(1, len(said), noted.notes)
    self.assertTrue(said[0].startswith(
      'identified by observation: the block at (3, 4, 6) as '
      'MCBlocks.Stone ('), said)
    self.assertIn('from 4 views', said[0])

  def test_a_furnace_by_its_front(self) -> None:
    """A dispenser has the furnace's top and sides: the front tells."""
    self.put('minecraft:furnace', 5)
    self.assertIs(MCBlocks.Furnace, self.agent.identify(PLACE))

  def test_among_a_given_few(self) -> None:
    self.put('minecraft:crafting_table')
    self.assertIs(MCBlocks.CraftingTable, self.agent.identify(
      PLACE, among=[MCBlocks.Stone, MCBlocks.Furnace,
                    MCBlocks.CraftingTable]))

  def test_the_same_pattern_in_another_colour(self) -> None:
    self.put('minecraft:wool', 14)
    self.assertIs(MCBlocks.RedWool, self.agent.identify(
      PLACE, among=[MCBlocks.RedWool, MCBlocks.BlueWool]))

  def test_two_that_look_the_same(self) -> None:
    self.player.looks[('minecraft:cobblestone', 0)] = LOOKS[
      ('minecraft:stone', 0)]
    self.put('minecraft:stone')
    with self.assertRaises(TesttimeError) as raised:
      self.agent.identify(PLACE, among=[MCBlocks.Stone,
                                        MCBlocks.Cobblestone])
    self.assertIn('MCBlocks.Cobblestone and MCBlocks.Stone look the same',
                  str(raised.exception))

  def test_only_the_metas_that_are_the_member(self) -> None:
    """
    Red wool is wool's meta 14 to mcdex: the blue look (meta 11) is no
    variant of it, though the game draws both for wool.
    """
    self.put('minecraft:wool', 11)
    with self.assertRaises(TesttimeError) as raised:
      self.agent.identify(PLACE, among=[MCBlocks.RedWool, MCBlocks.Stone])
    self.assertIn('looks like none of the candidates',
                  str(raised.exception))

  def test_one_that_looks_the_same_in_one_of_its_variants(self) -> None:
    """1.7.10's infested stone: stone's look among its own others."""
    stone = LOOKS[('minecraft:stone', 0)][0][1]
    self.player.looks[('minecraft:cobblestone', 0)] = [
      (0, dict(stone, down='cobblestone', up='cobblestone',
               north='cobblestone', south='cobblestone', west='cobblestone',
               east='cobblestone')), (1, stone)]
    self.put('minecraft:stone')
    with self.assertRaises(TesttimeError) as raised:
      self.agent.identify(PLACE, among=[MCBlocks.Stone,
                                        MCBlocks.Cobblestone])
    self.assertIn('MCBlocks.Cobblestone and MCBlocks.Stone look the same',
                  str(raised.exception))

  def test_no_look_by_the_margin(self) -> None:
    """Cobblestone here differs from stone only below, which no view sees."""
    faces = dict(LOOKS[('minecraft:stone', 0)][0][1], down='cobblestone')
    self.player.looks[('minecraft:cobblestone', 0)] = [(0, faces)]
    self.put('minecraft:stone')
    with self.assertRaises(TesttimeError) as raised:
      self.agent.identify(PLACE, among=[MCBlocks.Stone,
                                        MCBlocks.Cobblestone])
    message = str(raised.exception)
    self.assertEqual('identify', raised.exception.step)
    self.assertIn('no look beats the next by 0.10', message)
    self.assertIn('MCBlocks.Stone', message)
    self.assertIn('MCBlocks.Cobblestone', message)

  def test_air_by_touch(self) -> None:
    self.assertIs(MCBlocks.Air, self.agent.identify(PLACE))
    self.assertLess(abs(self.player.x - 3.5) + abs(self.player.z - 6.5), 0.5,
                    'it walked into the place')

  def test_what_can_t_be_a_candidate(self) -> None:
    self.put('minecraft:stone')
    with self.assertRaisesRegex(NotImplementedError, 'full cube'):
      self.agent.identify(PLACE, among=[MCBlocks.Stone, MCBlocks.Lever])
    with self.assertRaises(Missing):
      self.agent.identify(PLACE, among=[MCBlocks.Stone, MCBlocks.Barrier])


if __name__ == '__main__':
  unittest.main()

"""
The agent examining by observation (SPEC.md 15.4, 15.6 step 6), without
a game: a fake player (fakeplayer.py) whose views show the block when its
crosshair meets it. examine goes into reach and looks, or stands on the
side asked for and looks at that face, then takes the view, its frame
kept in the agent's frames folder; the view is noted as observed, its
pixels by the game's ray. A view with nothing of the block, a face it
can't target, a side above or below, each refused by name.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from test_agent import PLAYERS_MEANS, PlayedTests
from unittas.agent import Agent
from unittas.errors import TesttimeError
from unittas.run import Run
from unittas.values import BlockPos

STONE = BlockPos(3, 4, 6)


class _Noted:
  """A run, as far as notes go."""

  def __init__(self) -> None:
    self.notes = []

  def note(self, text: str) -> None:
    self.notes.append(text)


class ExamineTests(PlayedTests):

  def setUp(self) -> None:
    PlayedTests.setUp(self)
    self.folder = tempfile.mkdtemp(prefix='unittas-frames-')
    self.addCleanup(shutil.rmtree, self.folder, True)
    self.agent = Agent(self.agent.game, frames=self.folder)
    self.player.walls[(3, 4, 6)] = 'minecraft:obsidian'

  def test_examines_a_block(self) -> None:
    view = self.agent.examine(STONE)
    self.assertEqual(STONE, view.pos)
    self.assertEqual(256, view.count)
    self.assertEqual(((200, 40, 40),) * 256, view.pixels())
    self.assertEqual(self.folder, os.path.dirname(view.file))
    self.assertTrue(os.path.isfile(view.file))
    with open(view.file[:-4] + '.json', encoding='utf-8') as file:
      self.assertEqual(view.answer, json.load(file))
    self.assertGreater(self.player.z, 1.0, 'it walked into reach')
    self.assertEqual(set(), set(self.player.ops) - PLAYERS_MEANS -
                     {'view.block'})
    self.assertEqual(set(), self.player.keys)

  def test_from_a_side(self) -> None:
    view = self.agent.examine(STONE, side='west')
    self.assertLess(self.player.x, 3.0)
    self.assertEqual({'west': 256}, view.faces)

  def test_each_frame_its_own(self) -> None:
    first = self.agent.examine(STONE)
    second = self.agent.examine(STONE)
    self.assertNotEqual(first.file, second.file)

  def test_noted_as_observed(self) -> None:
    noted = _Noted()
    Run.current = noted
    self.addCleanup(setattr, Run, 'current', None)
    view = self.agent.examine(STONE)
    self.assertEqual(1, len(noted.notes))
    said = noted.notes[0]
    self.assertTrue(said.startswith(
      "observed (pixels by the game's ray): the block at (3, 4, 6) from "),
      said)
    self.assertIn('256 pixels (north 256)', said)
    self.assertIn(os.path.basename(view.file), said)

  def test_nothing_of_it_seen(self) -> None:
    self.player.blind = True
    with self.assertRaises(TesttimeError) as raised:
      self.agent.examine(STONE)
    self.assertEqual('examine', raised.exception.step)
    self.assertIn('nothing of the block at (3, 4, 6)', str(raised.exception))

  def test_a_face_it_can_t_target(self) -> None:
    self.player.walls[(3, 4, 5)] = 'minecraft:dirt'
    with self.assertRaises(TesttimeError) as raised:
      self.agent.examine(STONE, side='north')
    message = str(raised.exception)
    self.assertIn('north face', message)
    self.assertIn('minecraft:dirt at (3, 4, 5)', message)

  def test_above_or_below(self) -> None:
    with self.assertRaisesRegex(ValueError, 'climbing'):
      self.agent.examine(STONE, side='up')


if __name__ == '__main__':
  unittest.main()

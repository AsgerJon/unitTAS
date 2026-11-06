"""
The 'oldsaves' suite's twin (src/self/java/.../self/SaveTests.java), by the same names: save mode's own check, on the
self-check saves the probe's test_oldsaves makes (run/oldsaves/selfcheck). Run with 'unittas run selfsuite.oldsaves
--saves run/oldsaves/selfcheck'. Outside save mode it skips itself, and so does testB on a save with no marker.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os

from unittas.testcase import GameTestCase


def marker(save) -> tuple:
  """
  The marker's block from the save's building list ('name dim x1 y1 z1 x2 y2 z2 view ...', as
  oldsaves/make_vanilla_worlds.py writes it): the corner of the building named marker, or None without one.
  """
  if not save.buildings or not os.path.isfile(save.buildings):
    return None
  with open(save.buildings, encoding='utf-8') as file:
    for line in file:
      words = line.split()
      if len(words) >= 5 and words[0] == 'marker':
        return int(words[2]), int(words[3]), int(words[4])
  return None


class SaveTests(GameTestCase):

  def setUp(self) -> None:
    if self.save() is None:
      self.skipTest('not in save mode')

  def testA_loadedWithoutErrors(self) -> None:
    self.assertEqual((), self.save().loadErrors, 'logged while the save loaded')

  def testB_itsMarkerIsThere(self) -> None:
    at = marker(self.save())
    if at is None:
      self.skipTest('no marker in its building list: not a self-check save')
    self.assertEqual('minecraft:gold_block', self.game.block(at).id, 'the marker at %d %d %d' % at)

  def testC_theOneNamedIsOpen(self) -> None:
    self.assertEqual(self.save().folder, self.game.status()['world']['folder'])

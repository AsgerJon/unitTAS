"""
A block's view on the run's port (SPEC.md 15.6 step 6, 19.7 step 3c):
the frame the game drew for the player, the GUI hidden, and the block's
pixels on it by the game's ray (view.block). A stone's face straight
ahead fills its box; a fence post in front keeps its pixels for itself;
a redstone lamp, unlit and then lit, is told apart by the test's own
computation on the pixels; a block changed a moment before is seen as it
is now (26.3 builds a changed chunk section again on other threads: the
view waits for it). Each view is kept beside the results. Places written
as in 1.7.10's flat world and moved to the port's (ports.at).

  python -m unittas.selftest test_view.
  (through the watcher: "probe test_view.", "probe test_view on 26.3-fabric")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from mcdex import MCBlocks

from ports import FORGE_1_7_10, at, onlyOn, probeGame, start
from probegame import READY_SECONDS
from unittas.api import Game
from unittas.reset import reset
from unittas.values import Block

#  at eye height, two and a half blocks south of the start
AHEAD = at(0, 5, 3)


def lit(block: Block) -> bool:
  """A redstone lamp's on: 1.7.10's lit lamp is a block of its own, 26.3's a state."""
  if block.state:
    return block.properties['lit'] == 'true'
  return block.id == 'minecraft:lit_redstone_lamp'


class ViewTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = probeGame('view')
    shutil.rmtree(os.path.join(cls.launched.gameDir, 'saves', 'unittas'),
                  ignore_errors=True)
    connection = cls.launched.start(READY_SECONDS)
    connection.events.waitFor(
      lambda event: event.get('event') == 'ready', READY_SECONDS)
    cls.game = Game(connection)
    cls.game.request('world.create', {}, timeout=240)
    cls.folder = os.path.join(cls.launched.results, 'views')
    os.makedirs(cls.folder, exist_ok=True)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.launched.stop()

  def setUp(self) -> None:
    reset(self.game.connection, at=start())
    self.placed = []
    self.game.look(0, 0)

  def tearDown(self) -> None:
    for pos in reversed(self.placed):
      self.game.setBlock(pos, MCBlocks.Air)

  def place(self, pos, block) -> None:
    self.game.setBlock(pos, block)
    self.placed.append(pos)

  def view(self, name: str):
    view = self.game.view(AHEAD, os.path.join(self.folder, name + '.png'))
    if view.count:
      view.save(os.path.join(self.folder, name + '-view.png'))
    return view

  def test_a_a_face_straight_ahead(self) -> None:
    self.place(AHEAD, MCBlocks.Stone)
    view = self.view('stone')
    self.assertEqual(['north'], list(view.faces), view.faces)
    self.assertGreater(view.coverage, 0.85)
    x0, y0, x1, y1 = view.rect
    middle = (x0 + x1) / 2
    self.assertLess(abs(middle - view.width / 2), view.width * 0.05)

  def test_b_a_fence_post_in_front(self) -> None:
    self.place(AHEAD, MCBlocks.Stone)
    plain = self.view('plain').count
    self.place(at(0, 5, 2), MCBlocks.OakFence)
    hidden = self.view('behind-a-post').count
    self.assertLess(hidden, plain * 0.85, (hidden, plain))
    self.assertGreater(hidden, plain * 0.3, (hidden, plain))

  def test_c_a_lamp_unlit_and_lit(self) -> None:
    self.place(AHEAD, MCBlocks.RedstoneLamp)
    unlit = self.view('lamp-unlit').brightness()
    self.place(at(0, 5, 4), MCBlocks.RedstoneBlock)
    self.game.ticks(4)
    self.assertTrue(lit(self.game.block(AHEAD)), self.game.block(AHEAD))
    shown = self.view('lamp-lit').brightness()
    self.assertGreater(shown, unlit + 30, (unlit, shown))

  @onlyOn(FORGE_1_7_10, why='26.3 draws no toast while the HUD is hidden')
  def test_d_what_the_toast_covers(self) -> None:
    """
    1.7.10 draws its tutorial toast with the GUI hidden: a block behind it
    at the frame's top right keeps none of the toast's pixels.
    """
    up = at(-2, 7, 3)
    self.place(up, MCBlocks.Stone)
    view = self.game.view(up, os.path.join(self.folder, 'toast.png'))
    self.assertEqual(['toast'], [by for by, _ in view.covered])
    tx0, ty0, tx1, ty1 = view.covered[0][1]
    x0, y0, x1, y1 = view.rect
    under = [view.mask[y - y0][x - x0]
             for y in range(max(y0, ty0), min(y1, ty1))
             for x in range(max(x0, tx0), min(x1, tx1))]
    self.assertTrue(under, 'the block is behind the toast')
    self.assertEqual({'0'}, set(under))

  def test_e_a_block_changed_a_moment_before(self) -> None:
    """
    Stone seen, then glowstone set there and seen at once, its change not
    waited for by the test: the view is of glowstone, yellow where stone
    is grey (its mean red over its blue: stone's -10, glowstone's 58 in
    1.7.10's north face).
    """
    def yellow(view) -> float:
      r, g, b = view.mean()
      return r - b

    self.place(AHEAD, MCBlocks.Stone)
    stone = yellow(self.view('before-the-change'))
    self.game.setBlock(AHEAD, MCBlocks.Glowstone, verify=False)
    glowstone = yellow(self.view('just-changed'))
    self.assertGreater(glowstone, stone + 30, (stone, glowstone))


if __name__ == '__main__':
  unittest.main()

"""
A block's view (SPEC.md 15.4, 15.6 step 6) without a game: the frame
and the block's pixels on it, as view.block answers them; the test's own
computations on those pixels (their count, their mean colour, their
brightness); the view kept for review with the rest of its box clear.
A view of nothing has no mean; an answer whose mask doesn't fit its box
is refused by name.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from fakeplayer import faceCamera
from unittas import png
from unittas.blockview import BlockView
from unittas.values import BlockPos, Look, Vec3

GREY = (50, 50, 50)
RED = (200, 10, 10)
#  a 10 by 8 frame: grey, with a red block 4 by 3 at x 3 to 6, y 2 to 4
WIDTH, HEIGHT = 10, 8


def frame(path: str, channels: int = 3) -> None:
  data = bytearray()
  for y in range(HEIGHT):
    for x in range(WIDTH):
      colour = RED if 3 <= x < 7 and 2 <= y < 5 else GREY
      data += bytes(colour + (255,) * (channels - 3))
  png.write(path, WIDTH, HEIGHT, channels, bytes(data))


def answer(path: str) -> dict:
  """view.block's answer for the red block: its box [2, 1, 8, 6)."""
  mask = [''.join('1' if 3 <= x < 7 and 2 <= y < 5 else '0'
                  for x in range(2, 8)) for y in range(1, 6)]
  return {'file': path, 'width': WIDTH, 'height': HEIGHT, 'tick': 80,
          'camera': {'pos': [0.5, 5.62, 0.5],
                     'look': {'yaw': 0.0, 'pitch': 10.0},
                     'modelview': [0.0] * 16, 'projection': [0.0] * 16,
                     'viewport': [0, 0, WIDTH, HEIGHT]},
          'rect': [2, 1, 8, 6], 'mask': mask, 'faces': {'north': 12},
          'covered': []}


class BlockViewTests(unittest.TestCase):

  def setUp(self) -> None:
    self.folder = tempfile.mkdtemp(prefix='unittas-view-')
    self.addCleanup(shutil.rmtree, self.folder, True)
    self.file = os.path.join(self.folder, 'frame.png')
    frame(self.file)

  def test_the_block_s_pixels(self) -> None:
    view = BlockView(BlockPos(0, 5, 3), answer(self.file))
    self.assertEqual(BlockPos(0, 5, 3), view.pos)
    self.assertEqual((2, 1, 8, 6), view.rect)
    self.assertEqual(80, view.tick)
    self.assertEqual(Vec3(0.5, 5.62, 0.5), view.eye)
    self.assertEqual(Look(0.0, 10.0), view.look)
    self.assertEqual({'north': 12}, view.faces)
    self.assertEqual(answer(self.file), view.answer)
    self.assertEqual(12, view.count)
    self.assertAlmostEqual(12 / 30, view.coverage)
    self.assertEqual((RED,) * 12, view.pixels())

  def test_a_frame_with_alpha(self) -> None:
    frame(self.file, channels=4)
    view = BlockView(BlockPos(0, 5, 3), answer(self.file))
    self.assertEqual((RED,) * 12, view.pixels())

  def test_the_test_s_own_computations(self) -> None:
    view = BlockView(BlockPos(0, 5, 3), answer(self.file))
    self.assertEqual((200.0, 10.0, 10.0), view.mean())
    self.assertAlmostEqual(0.299 * 200 + 0.587 * 10 + 0.114 * 10,
                           view.brightness())

  def test_kept_for_review(self) -> None:
    view = BlockView(BlockPos(0, 5, 3), answer(self.file))
    kept = os.path.join(self.folder, 'view.png')
    view.save(kept)
    width, height, channels, data = png.read(kept)
    self.assertEqual((6, 5, 4), (width, height, channels))
    pixels = [tuple(data[i:i + 4]) for i in range(0, len(data), 4)]
    self.assertEqual(12, sum(1 for each in pixels if each == RED + (255,)))
    self.assertEqual(18, sum(1 for each in pixels if each[3] == 0))

  def test_what_covers_the_frame(self) -> None:
    """What the game draws over the world (1.7.10's toast) is said."""
    toast = {'by': 'toast', 'rect': [6, 0, 10, 2]}
    view = BlockView(BlockPos(0, 5, 3), dict(answer(self.file),
                                             covered=[toast]))
    self.assertEqual((('toast', (6, 0, 10, 2)),), view.covered)
    self.assertEqual((), BlockView(BlockPos(0, 5, 3),
                                   answer(self.file)).covered)

  def test_a_view_of_nothing(self) -> None:
    nothing = dict(answer(self.file), rect=None, mask=[], faces={})
    view = BlockView(BlockPos(0, 5, 3), nothing)
    self.assertEqual((0, 0.0, ()), (view.count, view.coverage,
                                    view.pixels()))
    with self.assertRaisesRegex(ValueError, 'nothing of the block'):
      view.mean()

  def test_refused_by_name(self) -> None:
    short = dict(answer(self.file), mask=answer(self.file)['mask'][:4])
    with self.assertRaisesRegex(ValueError, '4 rows'):
      BlockView(BlockPos(0, 5, 3), short)
    wide = dict(answer(self.file), mask=['0' * 7] * 5)
    with self.assertRaisesRegex(ValueError, '7 pixels'):
      BlockView(BlockPos(0, 5, 3), wide)
    with self.assertRaisesRegex(ValueError, 'has no "camera"'):
      BlockView(BlockPos(0, 5, 3), {key: value for key, value in
                                    answer(self.file).items()
                                    if key != 'camera'})


class SquaredUpTests(unittest.TestCase):
  """
  A face set square (SPEC.md 15.4): each texel's middle on the face put
  through the frame's camera, the frame's pixel there when it is the
  block's. A face turned away gives nothing.
  """

  def setUp(self) -> None:
    self.folder = tempfile.mkdtemp(prefix='unittas-square-')
    self.addCleanup(shutil.rmtree, self.folder, True)

  def drawn(self, face: str, eye: tuple, hide: int = 0) -> BlockView:
    """
    A 64 by 48 frame with the face of the block at (3, 4, 6) drawn one
    pixel a texel at [24, 16, 40, 32): texel (i, j) coloured (i * 16, j *
    16, 99); its first 'hide' columns not the block's.
    """
    data = bytearray()
    for y in range(48):
      for x in range(64):
        inside = 24 <= x < 40 and 16 <= y < 32
        data += bytes(((x - 24) * 16, (y - 16) * 16, 99) if inside
                      else GREY)
    path = os.path.join(self.folder, face + '.png')
    png.write(path, 64, 48, 3, bytes(data))
    mask = ['0' * hide + '1' * (16 - hide)] * 16
    camera = faceCamera((3, 4, 6), face, eye, (24, 16, 40, 32), 64, 48)
    return BlockView(BlockPos(3, 4, 6), {
      'file': path, 'width': 64, 'height': 48, 'tick': 1, 'camera': camera,
      'rect': [24, 16, 40, 32], 'mask': mask,
      'faces': {face: 256 - 16 * hide}, 'covered': []})

  def test_each_face_square(self) -> None:
    eyes = {'north': (3.5, 5.62, 3.0), 'south': (3.5, 5.62, 9.0),
            'west': (0.5, 5.62, 6.5), 'east': (6.5, 5.62, 6.5),
            'up': (3.5, 7.0, 6.5)}
    texels = tuple((i * 16, j * 16, 99) for j in range(16)
                   for i in range(16))
    for face, eye in eyes.items():
      with self.subTest(face=face):
        self.assertEqual(texels, self.drawn(face, eye).square(face))

  def test_a_point_on_the_frame(self) -> None:
    view = self.drawn('north', (3.5, 5.62, 3.0))
    #  the north face's top left, as one facing it sees it: (4, 5, 6)
    x, y = view.project(4.0, 5.0, 6.0)
    self.assertAlmostEqual(24.0, x)
    self.assertAlmostEqual(16.0, y)

  def test_what_isn_t_the_block_s(self) -> None:
    square = self.drawn('north', (3.5, 5.62, 3.0), hide=4).square('north')
    self.assertEqual([None] * 4, list(square[:4]))
    self.assertEqual((4 * 16, 0, 99), square[4])
    self.assertEqual(16 * 12, sum(1 for each in square if each))

  def test_a_face_turned_away(self) -> None:
    #  the south face from the north: nothing of it
    view = self.drawn('north', (3.5, 5.62, 3.0))
    self.assertEqual((None,) * 256, view.square('south'))

  def test_a_finer_texture(self) -> None:
    square = self.drawn('north', (3.5, 5.62, 3.0)).square('north', size=32)
    self.assertEqual(32 * 32, len(square))
    #  texels 0 and 1 of 32 both fall in the frame's first pixel
    self.assertEqual(square[0], square[1])


if __name__ == '__main__':
  unittest.main()

"""
BlockView: a block as the player sees it (SPEC.md 15.4, 15.6 step 6):
the frame the game drew, and the pixels of it the block covers.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from typing import TYPE_CHECKING

from worktoy.desc import Field
from worktoy.mcls import BaseObject

from . import png
from .values import BlockPos, Look, Vec3

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any


def _need(answer: dict, key: str) -> Any:
  if key not in answer:
    raise ValueError('a view has no "%s"' % key)
  return answer[key]


class BlockView(BaseObject):
  """
  The view of the block at 'pos' in one frame, from view.block's answer:
  the frame's file and size, its tick, its camera (the eye and look),
  the block's box on the frame [x0, y0, x1, y1) from its top left (empty
  when nothing of it is in front), and the mask of that box, a row of '0'
  and '1' for each of its rows, '1' where the game's ray through the
  pixel meets the block first. Until parallax comes (SPEC.md 15.4), the
  game's ray says which pixels are the block's.

  What the picture means is the test's computation on its pixels:

    view = self.agent.examine(lamp)
    self.assertGreater(view.brightness(), 150)
  """

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  NAMESPACE  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  #  Class Variables

  #  Fallback Variables

  #  Private Variables
  __pos__: BlockPos = None
  __answer__: dict = None
  __rect__: tuple = None
  __mask__: tuple = None
  #  the block's pixels, once read from the frame
  __pixels__: tuple = None

  #  Public Variables
  pos = Field()
  file = Field()
  width = Field()
  height = Field()
  tick = Field()
  eye = Field()
  look = Field()
  rect = Field()
  mask = Field()
  faces = Field()
  count = Field()
  coverage = Field()
  covered = Field()

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  GETTERS  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  @pos.GET
  def _getPos(self) -> BlockPos:
    return self.__pos__

  @file.GET
  def _getFile(self) -> str:
    """The frame's file."""
    return self.__answer__['file']

  @width.GET
  def _getWidth(self) -> int:
    return self.__answer__['width']

  @height.GET
  def _getHeight(self) -> int:
    return self.__answer__['height']

  @tick.GET
  def _getTick(self) -> int:
    """The client's tick the frame belongs to."""
    return self.__answer__['tick']

  @eye.GET
  def _getEye(self) -> Vec3:
    """Where the camera was."""
    return Vec3(*self.__answer__['camera']['pos'])

  @look.GET
  def _getLook(self) -> Look:
    look = self.__answer__['camera']['look']
    return Look(look['yaw'], look['pitch'])

  @rect.GET
  def _getRect(self) -> tuple:
    """The block's box on the frame, (x0, y0, x1, y1); () for none."""
    return self.__rect__

  @mask.GET
  def _getMask(self) -> tuple:
    return self.__mask__

  @faces.GET
  def _getFaces(self) -> dict:
    """How many of the block's pixels show each of its faces."""
    return dict(self.__answer__['faces'])

  @covered.GET
  def _getCovered(self) -> tuple:
    """
    What the game drew over the world, (by, (x0, y0, x1, y1)) each: its
    pixels are no block's (1.7.10's tutorial toast, which the hidden GUI
    still shows).
    """
    return tuple((each['by'], tuple(each['rect']))
                 for each in self.__answer__['covered'])

  @count.GET
  def _getCount(self) -> int:
    """How many pixels are the block's."""
    return sum(row.count('1') for row in self.__mask__)

  @coverage.GET
  def _getCoverage(self) -> float:
    """The share of its box the block's pixels take up."""
    if not self.__rect__:
      return 0.0
    x0, y0, x1, y1 = self.__rect__
    return self.count / ((x1 - x0) * (y1 - y0))

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  SETTERS  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  CONSTRUCTORS   # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  def __init__(self, pos: BlockPos, answer: dict) -> None:
    """
    The view of the block at 'pos' from view.block's answer.

    Raises
    ------
    ValueError
      The answer lacks a part, or its mask doesn't fit its box.
    """
    BaseObject.__init__(self)
    for key in ('file', 'width', 'height', 'tick', 'camera', 'rect',
                'mask', 'faces', 'covered'):
      _need(answer, key)
    rect = tuple(answer['rect'] or ())
    mask = tuple(answer['mask'])
    if rect:
      x0, y0, x1, y1 = rect
      if len(mask) != y1 - y0:
        raise ValueError('a view\'s box is %d rows, its mask %d rows' % (
          y1 - y0, len(mask)))
      for row in mask:
        if len(row) != x1 - x0:
          raise ValueError('a view\'s box is %d pixels across, a row of '
                           'its mask %d pixels' % (x1 - x0, len(row)))
    elif mask:
      raise ValueError('a view with no box has no mask, not %d rows' % len(
        mask))
    self.__pos__ = pos
    self.__answer__ = dict(answer)
    self.__rect__ = rect
    self.__mask__ = mask

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  DOMAIN SPECIFIC  # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  def pixels(self) -> tuple:
    """The block's pixels, (r, g, b) each, row by row from the top."""
    if self.__pixels__ is None:
      self.__pixels__ = tuple(colour for colour, mine in self._box() if mine)
    return self.__pixels__

  def mean(self) -> tuple:
    """The block's pixels' mean colour, (r, g, b)."""
    pixels = self.pixels()
    if not pixels:
      raise ValueError('nothing of the block at %s is in the view' % (
        self.__pos__,))
    return tuple(sum(each[i] for each in pixels) / len(pixels)
                 for i in range(3))

  def brightness(self) -> float:
    """The block's pixels' mean brightness, 0 to 255 (Rec. 601 luma)."""
    r, g, b = self.mean()
    return 0.299 * r + 0.587 * g + 0.114 * b

  def save(self, path: str) -> None:
    """The view's box as a PNG at 'path', clear but the block's pixels."""
    if not self.__rect__:
      raise ValueError('nothing of the block at %s is in the view' % (
        self.__pos__,))
    x0, y0, x1, y1 = self.__rect__
    data = bytearray()
    for colour, mine in self._box():
      data += bytes(colour) + (b'\xff' if mine else b'\x00')
    png.write(path, x1 - x0, y1 - y0, 4, bytes(data))

  def _box(self) -> list:
    """Each pixel of the box, with whether it is the block's."""
    if not self.__rect__:
      return []
    width, height, channels, data = png.read(self.file)
    x0, y0, x1, y1 = self.__rect__
    out = []
    for y in range(y0, y1):
      row = self.__mask__[y - y0]
      for x in range(x0, x1):
        at = (y * width + x) * channels
        out.append((tuple(data[at:at + 3]), row[x - x0] == '1'))
    return out

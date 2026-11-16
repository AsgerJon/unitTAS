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
  from typing import Any, Callable, Optional


#  Where a texel (u, v) of each face is, from the block's least corner, as
#  1.7.10 draws it: a side face's texture upright and unmirrored to one
#  facing it, the top's and the bottom's along x and z.
_FACE_POINT = {
  'down': lambda u, v: (u, 0.0, v), 'up': lambda u, v: (u, 1.0, v),
  'north': lambda u, v: (1.0 - u, 1.0 - v, 0.0),
  'south': lambda u, v: (u, 1.0 - v, 1.0),
  'west': lambda u, v: (0.0, 1.0 - v, u),
  'east': lambda u, v: (1.0, 1.0 - v, 1.0 - u)}
#  Whether an eye at (x, y, z) from the block's least corner is on the
#  face's outer side, where the face can be seen from
_FACE_SEEN = {
  'down': lambda x, y, z: y < 0.0, 'up': lambda x, y, z: y > 1.0,
  'north': lambda x, y, z: z < 0.0, 'south': lambda x, y, z: z > 1.0,
  'west': lambda x, y, z: x < 0.0, 'east': lambda x, y, z: x > 1.0}


def _onFace(corners: list) -> Callable:
  """
  Where a texel (u, v) of a face is, from the block's least corner, by
  the face's quad's corners as 26.3's block.faces gives them ([x, y, z,
  u, v] each, in order around it): a mirrored or turned texture is drawn
  as its corners say.

  Raises
  ------
  ValueError
    Not four corners of five numbers, or the texture has no area on them.
  """
  if len(corners) != 4 or any(len(each) != 5 for each in corners):
    raise ValueError('a face\'s corners are four [x, y, z, u, v], not %r' % (
      corners,))
  first, second, _, last = [[float(n) for n in each] for each in corners]
  du1, dv1 = second[3] - first[3], second[4] - first[4]
  du3, dv3 = last[3] - first[3], last[4] - first[4]
  det = du1 * dv3 - du3 * dv1
  if abs(det) < 1e-9:
    raise ValueError('the corners %r are no face: the texture has no area '
                     'on them' % (corners,))

  def at(u: float, v: float) -> tuple:
    #  (u, v) from the first corner, along the second's and the last's
    a = ((u - first[3]) * dv3 - (v - first[4]) * du3) / det
    b = (du1 * (v - first[4]) - dv1 * (u - first[3])) / det
    return tuple(first[i] + a * (second[i] - first[i]) +
                 b * (last[i] - first[i]) for i in range(3))

  return at


def _apply(matrix: list, vector: list) -> list:
  """A column-major 4 by 4 matrix times a column of four."""
  return [sum(matrix[c * 4 + r] * vector[c] for c in range(4))
          for r in range(4)]


def _times(a: list, b: list) -> list:
  """Two column-major 4 by 4 matrices' product, a times b."""
  return [sum(a[k * 4 + r] * b[c * 4 + k] for k in range(4))
          for c in range(4) for r in range(4)]


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
  #  the block's pixels, once read from the frame; the frame, once read
  __pixels__: tuple = None
  __frame__: tuple = None

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
  answer = Field()

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

  @answer.GET
  def _getAnswer(self) -> dict:
    """view.block's answer the view was made from, as it came."""
    return dict(self.__answer__)

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

  def project(self, x: float, y: float, z: float) -> Optional[tuple]:
    """
    Where the world's point (x, y, z) falls on the frame, (x, y) in its
    pixels from its top left, by the frame's own camera; None behind it.
    """
    camera = self.__answer__['camera']
    eye = camera['pos']
    clip = _apply(_times(camera['projection'], camera['modelview']),
                  [x - eye[0], y - eye[1], z - eye[2], 1.0])
    if clip[3] <= 1e-9:
      return None
    vx, vy, vw, vh = camera['viewport']
    across = vx + (clip[0] / clip[3] + 1) / 2 * vw
    up = vy + (clip[1] / clip[3] + 1) / 2 * vh
    return across, self.height - up

  def square(self, face: str, size: int = 16,
             corners: Optional[list] = None) -> tuple:
    """
    The face set square (SPEC.md 15.4): for each of a size by size
    texture's texels, row by row from the top as the game draws it, the
    frame's pixel at the texel's middle, (r, g, b), when that pixel is
    the block's; None where it isn't (hidden, or off the frame), and for
    every texel of a face turned away from the eye. The texture lies on
    the face as 1.7.10 draws it, or as its quad's 'corners' say (26.3's
    block.faces: stone drawn mirrored).
    """
    if face not in _FACE_POINT:
      raise ValueError('a face is one of %s, not %r' % (
        ', '.join(_FACE_POINT), face))
    point = _FACE_POINT[face] if corners is None else _onFace(corners)
    pos, eye = self.__pos__, self.__answer__['camera']['pos']
    if not self.__rect__ or not _FACE_SEEN[face](
        eye[0] - pos.x, eye[1] - pos.y, eye[2] - pos.z):
      return (None,) * (size * size)
    width, height, channels, data = self._frame()
    x0, y0, x1, y1 = self.__rect__
    out = []
    for j in range(size):
      for i in range(size):
        dx, dy, dz = point((i + 0.5) / size, (j + 0.5) / size)
        at = self.project(pos.x + dx, pos.y + dy, pos.z + dz)
        if at is None:
          out.append(None)
          continue
        px, py = int(at[0] // 1), int(at[1] // 1)
        if not (x0 <= px < x1 and y0 <= py < y1):
          out.append(None)
          continue
        if self.__mask__[py - y0][px - x0] != '1':
          out.append(None)
          continue
        start = (py * width + px) * channels
        out.append(tuple(data[start:start + 3]))
    return tuple(out)

  def _frame(self) -> tuple:
    """The frame, read once: (width, height, channels, data)."""
    if self.__frame__ is None:
      self.__frame__ = png.read(self.file)
    return self.__frame__

  def _box(self) -> list:
    """Each pixel of the box, with whether it is the block's."""
    if not self.__rect__:
      return []
    width, height, channels, data = self._frame()
    x0, y0, x1, y1 = self.__rect__
    out = []
    for y in range(y0, y1):
      row = self.__mask__[y - y0]
      for x in range(x0, x1):
        at = (y * width + x) * channels
        out.append((tuple(data[at:at + 3]), row[x - x0] == '1'))
    return out

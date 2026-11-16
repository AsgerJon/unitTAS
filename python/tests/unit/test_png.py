"""
PNG frames read and written with the standard library alone (SPEC.md
15.6 step 6): 8-bit RGB and RGBA, each of the five row filters undone,
anything else refused by name.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import random
import shutil
import struct
import tempfile
import unittest
import zlib
from typing import Optional

from unittas import png


def _chunk(kind: bytes, body: bytes) -> bytes:
  crc = zlib.crc32(kind + body) & 0xffffffff
  return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', crc)


def _paeth(a: int, b: int, c: int) -> int:
  p = a + b - c
  pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
  if pa <= pb and pa <= pc:
    return a
  return b if pb <= pc else c


def filtered(width: int, height: int, channels: int, data: bytes,
             kinds: list, colour: Optional[int] = None, depth: int = 8,
             interlace: int = 0) -> bytes:
  """A PNG of the data, each row put through the filter 'kinds' says."""
  stride = width * channels
  out = bytearray()
  previous = bytes(stride)
  for y in range(height):
    row = data[y * stride:(y + 1) * stride]
    kind = kinds[y % len(kinds)]
    line = bytearray()
    for i, value in enumerate(row):
      left = row[i - channels] if i >= channels else 0
      up = previous[i]
      corner = previous[i - channels] if i >= channels else 0
      guess = (0, left, up, (left + up) // 2, _paeth(left, up, corner))[kind]
      line.append((value - guess) & 255)
    out.append(kind)
    out += line
    previous = row
  colour = (2 if channels == 3 else 6) if colour is None else colour
  head = struct.pack('>IIBBBBB', width, height, depth, colour, 0, 0,
                     interlace)
  return (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', head) +
          _chunk(b'IDAT', zlib.compress(bytes(out))) + _chunk(b'IEND', b''))


class PngTests(unittest.TestCase):

  def setUp(self) -> None:
    self.folder = tempfile.mkdtemp(prefix='unittas-png-')
    self.addCleanup(shutil.rmtree, self.folder, True)

  def path(self, data: bytes) -> str:
    path = os.path.join(self.folder, 'frame.png')
    with open(path, 'wb') as file:
      file.write(data)
    return path

  def test_each_filter_undone(self) -> None:
    width, height = 7, 5
    for channels in (3, 4):
      data = bytes((x * 37 + y * 11 + c * 101) & 255
                   for y in range(height) for x in range(width)
                   for c in range(channels))
      for kinds in ([0], [1], [2], [3], [4], [0, 1, 2, 3, 4]):
        with self.subTest(channels=channels, kinds=kinds):
          path = self.path(filtered(width, height, channels, data, kinds))
          self.assertEqual((width, height, channels, data), png.read(path))

  def test_paeth_s_ties(self) -> None:
    """Paeth's guess on ties (left first, then up), over noisy rows."""
    chance = random.Random(5)
    width, height = 16, 12
    for channels in (3, 4):
      data = bytes(chance.randrange(4) * 60 for _ in
                   range(width * height * channels))
      path = self.path(filtered(width, height, channels, data, [4]))
      self.assertEqual((width, height, channels, data), png.read(path))

  def test_written_and_read_back(self) -> None:
    data = bytes(range(2 * 3 * 4))
    path = os.path.join(self.folder, 'made.png')
    png.write(path, 2, 3, 4, data)
    self.assertEqual((2, 3, 4, data), png.read(path))
    png.write(path, 4, 2, 3, data)
    self.assertEqual((4, 2, 3, data), png.read(path))

  def test_refused(self) -> None:
    with self.assertRaisesRegex(ValueError, 'not a PNG'):
      png.read(self.path(b'GIF89a' + bytes(20)))
    grey = filtered(2, 2, 1, bytes(4), [0], colour=0)
    with self.assertRaisesRegex(ValueError, 'colour type 0'):
      png.read(self.path(grey))
    deep = filtered(2, 2, 3, bytes(12), [0], depth=16)
    with self.assertRaisesRegex(ValueError, '16 bits'):
      png.read(self.path(deep))
    laced = filtered(2, 2, 3, bytes(12), [0], interlace=1)
    with self.assertRaisesRegex(ValueError, 'interlaced'):
      png.read(self.path(laced))
    with self.assertRaisesRegex(ValueError, 'channels'):
      png.write(os.path.join(self.folder, 'x.png'), 1, 1, 2, bytes(2))
    with self.assertRaisesRegex(ValueError, 'bytes'):
      png.write(os.path.join(self.folder, 'x.png'), 2, 2, 3, bytes(5))


if __name__ == '__main__':
  unittest.main()

"""
PNG frames read and written with the standard library alone (SPEC.md
15.6 step 6): the game's screenshots are 8-bit RGB, and a view kept for
review is 8-bit RGBA. Anything else is refused by name.

- read(path): (width, height, channels, data), the rows top to bottom.
- write(path, width, height, channels, data).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import struct
import zlib

SIGNATURE = b'\x89PNG\r\n\x1a\n'
#  a PNG's colour types by the channels they carry: RGB and RGBA
CHANNELS = {2: 3, 6: 4}


def _chunk(kind: bytes, body: bytes) -> bytes:
  crc = zlib.crc32(kind + body) & 0xffffffff
  return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', crc)


def _unfilter(kind: int, line: bytearray, previous: bytearray,
              step: int) -> None:
  """A row's filter undone in place: none, sub, up, average or Paeth."""
  if kind == 0:
    return
  size = len(line)
  if kind == 1:
    for i in range(step, size):
      line[i] = (line[i] + line[i - step]) & 255
  elif kind == 2:
    for i in range(size):
      line[i] = (line[i] + previous[i]) & 255
  elif kind == 3:
    for i in range(size):
      left = line[i - step] if i >= step else 0
      line[i] = (line[i] + ((left + previous[i]) >> 1)) & 255
  elif kind == 4:
    for i in range(size):
      a = line[i - step] if i >= step else 0
      b = previous[i]
      c = previous[i - step] if i >= step else 0
      p = a + b - c
      pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
      if pa <= pb and pa <= pc:
        guess = a
      elif pb <= pc:
        guess = b
      else:
        guess = c
      line[i] = (line[i] + guess) & 255
  else:
    raise ValueError('a PNG row has filter %d, not 0 to 4' % kind)


def read(path: str) -> tuple:
  """
  The PNG at 'path' as (width, height, channels, data): 'data' is its
  pixels' bytes, row by row from the top, 3 or 4 a pixel.

  Raises
  ------
  ValueError
    The file isn't a PNG, or is one of a kind the game's frames aren't
    (not 8 bits, not RGB or RGBA, interlaced).
  """
  with open(path, 'rb') as file:
    raw = file.read()
  if raw[:8] != SIGNATURE:
    raise ValueError('%s is not a PNG' % path)
  at, head, parts = 8, None, []
  while at + 8 <= len(raw):
    length, kind = struct.unpack('>I4s', raw[at:at + 8])
    body = raw[at + 8:at + 8 + length]
    at += 12 + length
    if kind == b'IHDR':
      head = struct.unpack('>IIBBBBB', body)
    elif kind == b'IDAT':
      parts.append(body)
    elif kind == b'IEND':
      break
  if head is None:
    raise ValueError('%s has no IHDR' % path)
  width, height, depth, colour, _, _, interlace = head
  if depth != 8:
    raise ValueError('%s has %d bits a channel, not 8' % (path, depth))
  if colour not in CHANNELS:
    raise ValueError('%s has colour type %d, not RGB (2) or RGBA (6)' % (
      path, colour))
  if interlace:
    raise ValueError('%s is interlaced' % path)
  channels = CHANNELS[colour]
  data = zlib.decompress(b''.join(parts))
  stride = width * channels
  out = bytearray()
  previous = bytearray(stride)
  for y in range(height):
    start = y * (stride + 1)
    line = bytearray(data[start + 1:start + 1 + stride])
    _unfilter(data[start], line, previous, channels)
    out += line
    previous = line
  return width, height, channels, bytes(out)


def write(path: str, width: int, height: int, channels: int,
          data: bytes) -> None:
  """'data' (rows from the top, 3 or 4 bytes a pixel) as a PNG at 'path'."""
  if channels not in (3, 4):
    raise ValueError('a PNG here has 3 or 4 channels, not %d' % channels)
  stride = width * channels
  if len(data) != stride * height:
    raise ValueError('%d by %d with %d channels is %d bytes, not %d' % (
      width, height, channels, stride * height, len(data)))
  rows = b''.join(b'\x00' + data[y * stride:(y + 1) * stride]
                  for y in range(height))
  colour = 2 if channels == 3 else 6
  head = struct.pack('>IIBBBBB', width, height, 8, colour, 0, 0, 0)
  with open(path, 'wb') as file:
    file.write(SIGNATURE + _chunk(b'IHDR', head) +
               _chunk(b'IDAT', zlib.compress(rows)) + _chunk(b'IEND', b''))

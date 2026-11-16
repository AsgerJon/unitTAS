"""
How much a block's squared-up face looks like a texture (SPEC.md 15.4's
identify), by what the light doesn't change:

- the correlation of their brightness once a linear gradient across each
  is taken out (a face's shading, the light level, and smooth lighting
  darkening it towards the ground don't change it);
- their colours (the same pattern in red and in blue is two looks);
- their relative contrast, the spread of brightness against its mean
  (1.7.10's bedrock is stone's pattern, darker and four times as stark).

The texture is the game's own, as texture.get gives it (ARGB, Java's
signed ints), times its tint (block.faces: a biome's green for grass).

- likeness(samples, texture, tint): a score, 1 for the same look; None
  when too little of the face was seen to say.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
  from typing import Optional

#  How many texels a face must show to be compared at all
LEAST = 16
#  What a colour's distance costs, against the brightness's correlation
CHROMA = 2.0
#  What a relative contrast's log-ratio costs, at most CONTRAST_MOST
CONTRAST = 0.5
CONTRAST_MOST = 2.0
#  Below this spread of brightness a look is flat: compared by colour alone
FLAT = 2.0


def _rgb(argb: int, tint: int) -> Optional[tuple]:
  """A texel's colour times the tint; None when it is clear."""
  argb &= 0xFFFFFFFF
  if (argb >> 24) < 128:
    return None
  return tuple(((argb >> shift) & 255) * ((tint >> shift) & 255) / 255
               for shift in (16, 8, 0))


def _luma(rgb: tuple) -> float:
  return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def _chromaticity(colours: list) -> tuple:
  """The colours' mean share of red and of green."""
  total = [sum(each[i] for each in colours) for i in range(3)]
  whole = sum(total) or 1.0
  return total[0] / whole, total[1] / whole


def _solve(rows: list) -> list:
  """The three unknowns of three linear equations (each row: a, b, c, =)."""
  rows = [list(row) for row in rows]
  for col in range(3):
    pivot = max(range(col, 3), key=lambda r: abs(rows[r][col]))
    rows[col], rows[pivot] = rows[pivot], rows[col]
    if abs(rows[col][col]) < 1e-12:
      return [sum(row[3] for row in rows) / 3, 0.0, 0.0]
    for r in range(3):
      if r != col:
        factor = rows[r][col] / rows[col][col]
        rows[r] = [x - factor * y for x, y in zip(rows[r], rows[col])]
  return [rows[i][3] / rows[i][i] for i in range(3)]


def _residuals(places: list, values: list) -> list:
  """The values less the plane a + b u + c v fitted to them."""
  n = len(places)
  su = sum(u for u, _ in places)
  sv = sum(v for _, v in places)
  suu = sum(u * u for u, _ in places)
  svv = sum(v * v for _, v in places)
  suv = sum(u * v for u, v in places)
  sy = sum(values)
  suy = sum(u * y for (u, _), y in zip(places, values))
  svy = sum(v * y for (_, v), y in zip(places, values))
  a, b, c = _solve([[n, su, sv, sy], [su, suu, suv, suy],
                    [sv, suv, svv, svy]])
  return [y - (a + b * u + c * v) for (u, v), y in zip(places, values)]


def _spread(values: list) -> float:
  return math.sqrt(sum(x * x for x in values) / len(values))


def likeness(samples: tuple, texture: tuple,
             tint: int = 0xFFFFFF) -> Optional[float]:
  """
  How much the face 'samples' show (a squared-up face: (r, g, b) or None
  for each texel, row by row) looks like 'texture' (ARGB for each texel,
  the same count, square) tinted by 'tint' (0xRRGGBB): 1 for the same
  look. None when fewer than LEAST texels were seen.

  Raises
  ------
  ValueError
    The samples and the texture are of different sizes.
  """
  if len(samples) != len(texture):
    raise ValueError('a face of %d texels compared with a texture of %d '
                     'texels' % (len(samples), len(texture)))
  size = max(1, int(math.isqrt(len(texture))))
  places, seen, look, pairs = [], [], [], []
  for at, (sample, argb) in enumerate(zip(samples, texture)):
    if sample is None:
      continue
    colour = _rgb(argb, tint)
    if colour is None:
      continue
    places.append(((at % size) / size, (at // size) / size))
    seen.append(_luma(sample))
    look.append(_luma(colour))
    pairs.append((sample, colour))
  if len(pairs) < LEAST:
    return None
  restSeen, restLook = _residuals(places, seen), _residuals(places, look)
  spreadSeen, spreadLook = _spread(restSeen), _spread(restLook)
  flatSeen, flatLook = spreadSeen < FLAT, spreadLook < FLAT
  if flatSeen and flatLook:
    correlation, contrast = 1.0, 0.0
  elif flatSeen or flatLook:
    correlation, contrast = 0.0, CONTRAST_MOST
  else:
    together = sum(s * t for s, t in zip(restSeen, restLook)) / len(seen)
    correlation = together / (spreadSeen * spreadLook)
    meanSeen = max(sum(seen) / len(seen), 1e-6)
    meanLook = max(sum(look) / len(look), 1e-6)
    contrast = min(CONTRAST_MOST, abs(math.log(
      (spreadSeen / meanSeen) / (spreadLook / meanLook))))
  a = _chromaticity([sample for sample, _ in pairs])
  b = _chromaticity([colour for _, colour in pairs])
  return (correlation - CHROMA * math.hypot(a[0] - b[0], a[1] - b[1]) -
          CONTRAST * contrast)

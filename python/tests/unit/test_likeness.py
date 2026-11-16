"""
How much a squared-up face looks like a texture (SPEC.md 15.4): by a
measure a face's shading and light level don't change (the correlation
of their brightness), less how far apart their colours are. The same
look scores about 1 in any light; another pattern, or the same pattern
in another colour, scores less; a tint (a biome's green) is the game's
and counts; what the view hides is left out, and too little seen says
nothing.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import random
import unittest

from unittas.likeness import likeness


def pattern(seed: int, colour: tuple) -> tuple:
  """A 16 by 16 texture, ARGB as the game gives it, the pattern by 'seed'."""
  chance = random.Random(seed)
  out = []
  for _ in range(256):
    shade = 0.5 + chance.random() / 2
    r, g, b = (int(c * shade) for c in colour)
    out.append((0xFF << 24) | (r << 16) | (g << 8) | b)
  return tuple(out)


def seen(texture: tuple, light: float = 1.0, offset: int = 0) -> tuple:
  """The texture as a view shows it: in a light, (r, g, b) each."""
  out = []
  for argb in texture:
    r, g, b = (argb >> 16) & 255, (argb >> 8) & 255, argb & 255
    out.append(tuple(min(255, int(c * light) + offset) for c in (r, g, b)))
  return tuple(out)


STONE = pattern(1, (128, 128, 128))
RED = pattern(2, (180, 40, 40))
BLUE = pattern(2, (40, 40, 180))


class LikenessTests(unittest.TestCase):

  def test_the_same_look(self) -> None:
    self.assertAlmostEqual(1.0, likeness(seen(STONE), STONE), places=6)

  def test_in_another_light(self) -> None:
    self.assertGreater(likeness(seen(STONE, 0.55, 6), STONE), 0.9)

  def test_a_gradient_of_light_across_it(self) -> None:
    """Smooth lighting darkens a face towards the ground: still the look."""
    view = []
    for at, colour in enumerate(seen(STONE)):
      fade = 1.0 - 0.5 * (at // 16) / 16
      view.append(tuple(int(c * fade) for c in colour))
    self.assertGreater(likeness(tuple(view), STONE), 0.9)

  def test_the_same_pattern_in_another_contrast(self) -> None:
    """1.7.10's bedrock: stone's pattern, darker and four times as stark."""
    stark = []
    for argb in STONE:
      grey = (argb >> 16) & 255
      level = max(0, min(255, int((grey - 100) * 4 + 60)))
      stark.append((0xFF << 24) | (level << 16) | (level << 8) | level)
    stark = tuple(stark)
    same = likeness(seen(STONE), STONE)
    other = likeness(seen(STONE), stark)
    self.assertGreater(same - other, 0.3, (same, other))
    #  and the stark one in its own light is still itself
    self.assertGreater(likeness(seen(stark, 0.6), stark), 0.9)

  def test_another_pattern(self) -> None:
    other = pattern(7, (128, 128, 128))
    self.assertLess(likeness(seen(other), STONE), 0.3)

  def test_the_same_pattern_in_another_colour(self) -> None:
    same = likeness(seen(RED), RED)
    other = likeness(seen(RED), BLUE)
    self.assertGreater(same - other, 0.3, (same, other))

  def test_a_tint(self) -> None:
    grass = pattern(3, (150, 150, 150))
    green = 0x79C05A
    tinted = []
    for argb in grass:
      r, g, b = (argb >> 16) & 255, (argb >> 8) & 255, argb & 255
      tinted.append((r * 0x79 // 255, g * 0xC0 // 255, b * 0x5A // 255))
    self.assertGreater(likeness(tuple(tinted), grass, green), 0.95)
    self.assertLess(likeness(tuple(tinted), grass),
                    likeness(tuple(tinted), grass, green) - 0.2)

  def test_what_is_hidden_is_left_out(self) -> None:
    view = list(seen(STONE))
    for i in range(0, 256, 2):
      view[i] = None
    self.assertAlmostEqual(1.0, likeness(tuple(view), STONE), places=6)

  def test_too_little_seen(self) -> None:
    view = [None] * 256
    for i in range(15):
      view[i] = seen(STONE)[i]
    self.assertIsNone(likeness(tuple(view), STONE))

  def test_flat_looks(self) -> None:
    flat = tuple([(0xFF << 24) | (90 << 16) | (90 << 8) | 90] * 256)
    self.assertAlmostEqual(1.0, likeness(seen(flat, 0.8), flat))
    self.assertLess(likeness(seen(STONE), flat), 0.1)

  def test_java_s_signed_pixels_and_clear_ones(self) -> None:
    signed = tuple(argb - (1 << 32) for argb in STONE)
    self.assertAlmostEqual(1.0, likeness(seen(STONE), signed), places=6)
    #  a clear texel's colour is nothing to go by: left out
    clear = list(STONE)
    for i in range(0, 256, 3):
      clear[i] = 0
    self.assertAlmostEqual(1.0, likeness(seen(STONE), tuple(clear)),
                           places=6)

  def test_mismatched_sizes_are_refused(self) -> None:
    with self.assertRaisesRegex(ValueError, '256 texels'):
      likeness(seen(STONE)[:100], STONE)


if __name__ == '__main__':
  unittest.main()

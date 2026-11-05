"""
The test display (unittas.display), without a display: what goes in front of a game's command, as unittas-display.sh
decides it. nested: inside gamescope's own window on a Wayland desktop, which never takes focus; headless: gamescope
with no window at all; plain: straight on the desktop. Without gamescope, or without Wayland for nested, the game goes
straight on the desktop, and the reason is said.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import unittest

from unittas.display import DisplayError, prefix

GAMESCOPE = '/usr/bin/gamescope'


def found(name: str):
  return GAMESCOPE if name == 'gamescope' else None


class DisplayTests(unittest.TestCase):

  def test_nested_on_wayland(self) -> None:
    words, why = prefix('nested', 854, 480, environ={'WAYLAND_DISPLAY': 'wayland-0'}, which=found)
    self.assertEqual([GAMESCOPE, '--backend', 'wayland', '-w', '854', '-h', '480', '-W', '854', '-H', '480', '--'],
                     words)
    self.assertIsNone(why)

  def test_headless(self) -> None:
    words, why = prefix('headless', 1280, 720, environ={}, which=found)
    self.assertEqual([GAMESCOPE, '--backend', 'headless', '-w', '1280', '-h', '720', '-W', '1280', '-H', '720', '--'],
                     words)

  def test_plain(self) -> None:
    self.assertEqual(([], None), prefix('plain', 854, 480, environ={'WAYLAND_DISPLAY': 'wayland-0'}, which=found))

  def test_nested_without_wayland_or_gamescope_says_why(self) -> None:
    words, why = prefix('nested', 854, 480, environ={}, which=found)
    self.assertEqual([], words)
    self.assertIn('Wayland', why)
    words, why = prefix('nested', 854, 480, environ={'WAYLAND_DISPLAY': 'wayland-0'}, which=lambda name: None)
    self.assertEqual([], words)
    self.assertIn('gamescope', why)

  def test_the_environment_a_game_starts_with(self) -> None:
    #  as unittas-display.sh: no activation token, so the window can't take focus
    from unittas.display import environment
    env = environment({'XDG_ACTIVATION_TOKEN': 't', 'DESKTOP_STARTUP_ID': 'd', 'HOME': '/home/x'})
    self.assertEqual({'HOME': '/home/x'}, env)

  def test_an_unknown_mode(self) -> None:
    with self.assertRaises(DisplayError):
      prefix('wide', 854, 480, environ={}, which=found)


if __name__ == '__main__':
  unittest.main()

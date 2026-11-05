"""
The 'display' module says what goes in front of a game's command so that its
window behaves as a test game's should (SPEC.md 9.3, step 6b): what
unittas-display.sh does, in the package, so a mod's repository needs no
unitTAS script.

- nested (the default): inside gamescope's own window on a Wayland desktop.
  It's a Wayland window started without an activation token, so it shows
  without taking focus, and the game's own X11 focus requests stay inside
  gamescope;
- headless: gamescope with no window at all;
- plain: straight on the desktop.

Without gamescope, or with nested and no Wayland desktop, the game goes
straight on the desktop, and the reason is given (it may take focus).

- prefix: the words in front of the game's command, and why it's plain if so.
- environment: the environment a game starts with.
- DisplayError: a mode that isn't one.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
  from typing import Callable, Mapping, Optional

MODES = ('nested', 'headless', 'plain')


class DisplayError(ValueError):
  """A display mode that isn't one of MODES."""


def prefix(mode: str, width: int, height: int, environ: Optional[Mapping[str, str]] = None,
           which: Callable[[str], Optional[str]] = shutil.which) -> tuple:
  """
  The words in front of the game's command for the mode, and None; or no
  words and why the game goes straight on the desktop instead.
  """
  if mode not in MODES:
    raise DisplayError('the display is one of %s, not %r' % (', '.join(MODES), mode))
  if mode == 'plain':
    return [], None
  environ = os.environ if environ is None else environ
  gamescope = which('gamescope')
  if gamescope is None:
    return [], 'no gamescope, so the game goes straight on the desktop (it may take focus)'
  backend = 'headless'
  if mode == 'nested':
    if not environ.get('WAYLAND_DISPLAY'):
      return [], 'not a Wayland desktop, so the game goes straight on it (it may take focus)'
    backend = 'wayland'
  size = [str(width), str(height)]
  return [gamescope, '--backend', backend, '-w', size[0], '-h', size[1], '-W', size[0], '-H', size[1], '--'], None


def environment(environ: Optional[Mapping[str, str]] = None) -> dict:
  """The environment a game starts with: the caller's, less the activation tokens that would let it take focus."""
  base = dict(os.environ if environ is None else environ)
  for key in ('XDG_ACTIVATION_TOKEN', 'DESKTOP_STARTUP_ID'):
    base.pop(key, None)
  return base

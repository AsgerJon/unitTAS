"""
The 'gameoutput' module reads a launched game's output as it grows, for
the wait for its hello (unittas.game.LaunchedGame.accept): whether it grew,
the sign of life a game must give, and which watched phrases it has said.

- GameOutput: a game's output file, read on as it grows.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os


class GameOutput:
  """
  A game's output file as it grows: whether it grew since the last look,
  and which of the phrases watched for a line of it has said so far (read
  on from where the last look ended, a line not yet whole kept for the
  next).
  """

  def __init__(self, path: str, watched: tuple) -> None:
    self.path = path
    self.watched = watched
    self.found = set()
    self.read = 0
    self.size = -1
    self.rest = ''

  def grew(self) -> bool:
    try:
      size = os.path.getsize(self.path)
    except OSError:
      size = -1
    grown = size != self.size
    self.size = size
    if grown and size > self.read:
      with open(self.path, 'rb') as file:
        file.seek(self.read)
        data = file.read()
      self.read += len(data)
      text = self.rest + data.decode('utf-8', 'replace')
      whole, _, self.rest = text.rpartition('\n')
      for line in whole.split('\n') if whole else ():
        self.found.update(what for what in self.watched if what in line)
    return grown

  def said(self, what: str) -> bool:
    return what in self.found

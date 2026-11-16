"""
A save's level.dat, read for what unitTAS needs of it: the version that
saved it (Data.Version.Name, written since 1.9), for a saved map's
sanity check (SPEC.md 17.4). Gzipped binary NBT, read by the standard
library alone.

- savedBy: the version that saved a save, or '' for one that doesn't say.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import gzip
import os
import struct
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any


def savedBy(folder: str) -> str:
  """
  The version that saved the save in 'folder', by its level.dat: '' for
  a save that doesn't say (one older than 1.9).

  Raises
  ------
  FileNotFoundError
    The folder has no level.dat.
  ValueError
    Its level.dat isn't gzipped NBT.
  """
  path = os.path.join(folder, 'level.dat')
  if not os.path.isfile(path):
    raise FileNotFoundError('%s has no level.dat: no save is there' % folder)
  try:
    with gzip.open(path, 'rb') as file:
      data = file.read()
  except (OSError, EOFError) as error:
    raise ValueError('%s is no gzipped level.dat: %s' % (path, error))
  root = _Reader(data, path).root()
  level = root.get('Data')
  version = level.get('Version') if isinstance(level, dict) else None
  name = version.get('Name') if isinstance(version, dict) else None
  return name if isinstance(name, str) else ''


class _Reader:
  """Binary NBT, big-endian, as the game writes it."""

  _FIXED = {1: '>b', 2: '>h', 3: '>i', 4: '>q', 5: '>f', 6: '>d'}
  _ARRAYS = {7: '>b', 11: '>i', 12: '>q'}

  def __init__(self, data: bytes, path: str) -> None:
    self.data = data
    self.path = path
    self.at = 0

  def take(self, count: int) -> bytes:
    if self.at + count > len(self.data):
      raise ValueError('%s ends inside its NBT' % self.path)
    out = self.data[self.at:self.at + count]
    self.at += count
    return out

  def unpack(self, form: str) -> Any:
    return struct.unpack(form, self.take(struct.calcsize(form)))[0]

  def text(self) -> str:
    return self.take(self.unpack('>H')).decode('utf-8', 'replace')

  def root(self) -> dict:
    """The root compound: its type (10), its name, its contents."""
    if self.unpack('>b') != 10:
      raise ValueError('%s holds no NBT compound' % self.path)
    self.text()
    return self.payload(10)

  def payload(self, kind: int) -> Any:
    if kind in self._FIXED:
      return self.unpack(self._FIXED[kind])
    if kind in self._ARRAYS:
      return [self.unpack(self._ARRAYS[kind])
              for _ in range(self.unpack('>i'))]
    if kind == 8:
      return self.text()
    if kind == 9:
      inner = self.unpack('>b')
      return [self.payload(inner) for _ in range(self.unpack('>i'))]
    if kind == 10:
      out = {}
      while True:
        inner = self.unpack('>b')
        if inner == 0:
          return out
        name = self.text()
        out[name] = self.payload(inner)
    raise ValueError('%s holds an NBT tag of type %d' % (self.path, kind))

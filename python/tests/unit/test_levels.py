"""
A save's level.dat, read for the version that saved it (unittas.levels),
without a game: gzipped binary NBT as the game writes it, read by the
standard library alone.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import gzip
import os
import shutil
import struct
import tempfile
import unittest

from unittas.levels import savedBy


def _name(text: str) -> bytes:
  data = text.encode('utf-8')
  return struct.pack('>H', len(data)) + data


def writeLevel(folder: str, version: str = '') -> str:
  """
  A level.dat as the game writes one: Data with a few tags of other kinds
  around it, and Data.Version.Name when 'version' is given (since 1.9).
  """
  data = (b'\x08' + _name('LevelName') + _name('a map')
          + b'\x04' + _name('RandomSeed') + struct.pack('>q', 8675309)
          + b'\x09' + _name('Players') + b'\x01' + struct.pack('>i', 2)
          + b'\x05\x07'
          + b'\x0b' + _name('Spots') + struct.pack('>i', 1)
          + struct.pack('>i', 64))
  if version:
    data += (b'\x0a' + _name('Version') + b'\x08' + _name('Name')
             + _name(version) + b'\x03' + _name('Id')
             + struct.pack('>i', 1343) + b'\x00')
  root = b'\x0a' + _name('') + b'\x0a' + _name('Data') + data + b'\x00\x00'
  os.makedirs(folder, exist_ok=True)
  path = os.path.join(folder, 'level.dat')
  with gzip.open(path, 'wb') as file:
    file.write(root)
  return path


class SavedByTests(unittest.TestCase):

  def setUp(self) -> None:
    self.folder = tempfile.mkdtemp(prefix='unittas-levels-')
    self.addCleanup(shutil.rmtree, self.folder, True)

  def test_a_save_since_1_9_names_its_version(self) -> None:
    writeLevel(self.folder, '1.12.2')
    self.assertEqual('1.12.2', savedBy(self.folder))

  def test_an_older_save_says_nothing(self) -> None:
    """1.7.10 writes no Version: ''."""
    writeLevel(self.folder)
    self.assertEqual('', savedBy(self.folder))

  def test_a_level_that_isn_t_one_is_refused(self) -> None:
    with open(os.path.join(self.folder, 'level.dat'), 'wb') as file:
      file.write(b'not gzip at all')
    with self.assertRaises(ValueError):
      savedBy(self.folder)
    with self.assertRaises(FileNotFoundError):
      savedBy(os.path.join(self.folder, 'nowhere'))


if __name__ == '__main__':
  unittest.main()

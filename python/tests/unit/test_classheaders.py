"""
A jar's classes' supertypes (SPEC.md 19.7 step 6d), read from their
class files' headers alone, without Java: the class, its superclass and
its interfaces by their internal names, the constant pool read entry by
entry (a long or a double two entries); a file that isn't a class file
refused, saying which.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import struct
import tempfile
import unittest
import zipfile

from unittas.classheaders import header, supertypes


def utf8(text: str) -> bytes:
  data = text.encode('utf-8')
  return b'\x01' + struct.pack('>H', len(data)) + data


def classFile(name: str, superName: str, interfaces: tuple) -> bytes:
  """A class file's header: its pool (a long in it), it, its supertypes."""
  pool = [utf8(name), b'\x07' + struct.pack('>H', 1), utf8(superName),
          b'\x07' + struct.pack('>H', 3), b'\x05' + struct.pack('>q', 7)]
  # the long takes entries 5 and 6: the next is 7
  entries = 7
  faces = []
  for face in interfaces:
    pool.append(utf8(face))
    pool.append(b'\x07' + struct.pack('>H', entries))
    faces.append(entries + 1)
    entries += 2
  out = b'\xca\xfe\xba\xbe' + struct.pack('>HHH', 0, 65, entries)
  out += b''.join(pool)
  out += struct.pack('>HHHH', 0x21, 2, 4, len(faces))
  out += b''.join(struct.pack('>H', face) for face in faces)
  return out + struct.pack('>HHH', 0, 0, 0)


class HeaderTests(unittest.TestCase):

  def test_a_class_s_supertypes(self) -> None:
    self.assertEqual(('gkx', 'bvh', ('fyk', 'dsr')),
                     header(classFile('gkx', 'bvh', ('fyk', 'dsr'))))
    self.assertEqual(('a', 'java/lang/Object', ()),
                     header(classFile('a', 'java/lang/Object', ())))

  def test_not_a_class_file_is_refused(self) -> None:
    with self.assertRaises(ValueError):
      header(b'PK\x03\x04 a zip, not a class')

  def test_a_jar_s_classes(self) -> None:
    folder = tempfile.mkdtemp(prefix='unittas-classheaders-')
    self.addCleanup(shutil.rmtree, folder, True)
    path = os.path.join(folder, 'client.jar')
    with zipfile.ZipFile(path, 'w') as jar:
      jar.writestr('gkx.class', classFile('gkx', 'bvh', ('fyk',)))
      jar.writestr('bvh.class', classFile('bvh', 'java/lang/Object', ()))
      jar.writestr('assets/minecraft/lang/en_us.json', '{}')
    self.assertEqual({'gkx': ('bvh', ('fyk',)),
                      'bvh': ('java/lang/Object', ())}, supertypes(path))


if __name__ == '__main__':
  unittest.main()

"""
The 'classheaders' module reads a jar's classes' supertypes from their
class files' headers (SPEC.md 19.7 step 6d; the format is JVMS chapter
4), without Java: what composing Mojang's names through intermediary
needs, since intermediary names an overriding method only on the class
that first declares it, and an override takes that root's name.

- header: one class file's name, superclass and interfaces.
- supertypes: every class of a jar, by its internal name.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import struct
import zipfile

#  each constant pool tag's size after the tag, but Utf8's (its length
#  first): JVMS 4.4
_SIZES = {3: 4, 4: 4, 5: 8, 6: 8, 7: 2, 8: 2, 9: 4, 10: 4, 11: 4, 12: 4,
          15: 3, 16: 2, 17: 4, 18: 4, 19: 2, 20: 2}


def header(data: bytes) -> tuple:
  """
  A class file's (name, superclass, interfaces), internal names, the
  superclass '' for java/lang/Object's own; ValueError for bytes that
  aren't a class file.
  """
  if data[:4] != b'\xca\xfe\xba\xbe':
    raise ValueError('not a class file')
  count = struct.unpack_from('>H', data, 8)[0]
  at = 10
  texts, classes = {}, {}
  index = 1
  while index < count:
    tag = data[at]
    if tag == 1:
      length = struct.unpack_from('>H', data, at + 1)[0]
      texts[index] = data[at + 3:at + 3 + length].decode('utf-8', 'replace')
      at += 3 + length
    elif tag in _SIZES:
      if tag == 7:
        classes[index] = struct.unpack_from('>H', data, at + 1)[0]
      at += 1 + _SIZES[tag]
    else:
      raise ValueError('an unknown constant pool tag %d at entry %d'
                       % (tag, index))
    index += 2 if tag in (5, 6) else 1
  this, superclass, faces = struct.unpack_from('>HHH', data, at + 2)
  interfaces = struct.unpack_from('>%dH' % faces, data, at + 8)

  def name(entry: int) -> str:
    return texts[classes[entry]] if entry else ''

  return (name(this), name(superclass),
          tuple(name(each) for each in interfaces))


def supertypes(path: str) -> dict:
  """Each class of the jar by its internal name: (superclass, interfaces)."""
  found = {}
  with zipfile.ZipFile(path) as jar:
    for entry in jar.namelist():
      if entry.endswith('.class'):
        name, superclass, interfaces = header(jar.read(entry))
        found[name] = (superclass, interfaces)
  return found

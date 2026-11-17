"""
The 'intermediary' module reads Fabric's intermediary names for an
obfuscated version (SPEC.md 19.7 step 6d): Fabric Loader runs such a
version under them (net.minecraft.class_310 for 1.21.1's fgo, Mojang's
Minecraft), from the jar its profile names among its libraries
(net.fabricmc:intermediary:VERSION), whose mappings/mappings.tiny maps
the official (obfuscated) names to intermediary's. It lists what
intermediary renames: a member it hasn't keeps its official name.

Mojang's names composed through them (MojangNames.through) are the table
the agent renames its probe by beside Fabric.

- Intermediary: the names read from the tiny file or its jar.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import zipfile

#  the tiny file's first line, the one format read here
_HEADER = 'v1\tofficial\tintermediary'


class Intermediary:
  """
  Intermediary's names: 'classes' maps an official (obfuscated) internal
  name to intermediary's; 'fields' and 'methods' map (official owner,
  official name, the official descriptor) to intermediary's name.
  """

  def __init__(self, classes: dict, fields: dict, methods: dict) -> None:
    self.classes = classes
    self.fields = fields
    self.methods = methods

  @classmethod
  def fromText(cls, text: str) -> Intermediary:
    """
    The names in a tiny v1 file's text; ValueError for another format, or
    naming the line it can't read.
    """
    lines = text.splitlines()
    if not lines or lines[0].rstrip('\t') != _HEADER:
      raise ValueError('not a tiny v1 file of official to intermediary '
                       'names: its first line is %r'
                       % (lines[0] if lines else ''))
    classes, fields, methods = {}, {}, {}
    for number, line in enumerate(lines[1:], 2):
      if not line.strip() or line.startswith('#'):
        continue
      parts = line.split('\t')
      if parts[0] == 'CLASS' and len(parts) == 3:
        classes[parts[1]] = parts[2]
      elif parts[0] in ('FIELD', 'METHOD') and len(parts) == 5:
        owner, descriptor, name, renamed = parts[1:]
        into = fields if parts[0] == 'FIELD' else methods
        into[(owner, name, descriptor)] = renamed
      else:
        raise ValueError('line %d of the tiny file can\'t be read: %r'
                         % (number, line))
    return cls(classes, fields, methods)

  @classmethod
  def fromJar(cls, path: str) -> Intermediary:
    """The names in an intermediary jar's mappings/mappings.tiny."""
    with zipfile.ZipFile(path) as archive:
      return cls.fromText(
        archive.read('mappings/mappings.tiny').decode('utf-8'))

"""
The 'srgnames' module reads Forge's SRG names for an obfuscated version
(SPEC.md 19.7 step 8): Forge 1.20.1 runs the game with Mojang's class names
and SRG field and method names (f_91076_, m_91398_), its install renaming
the client jar by the MCP config's names merged with Mojang's for classes
only. The names are the MCP config's config/joined.tsrg, which Forge's
install keeps (its MAPPINGS): tsrg2, obfuscated to SRG, each class on a
line of its own and each of its members on a line under it, a method with
its obfuscated descriptor; an override is listed on its own class by its
root's name.

Before 1.17 (SPEC.md 19.7 step 11e: Forge 32.0.108 for 1.16.1) the MCP
config's joined.tsrg is tsrg v1: no header, a class as "obf srg", a field
as a tab and "obf srg", a method as a tab and "obf descriptor srg"; and
Forge ran MCP's class names too (net/minecraft/entity/player/PlayerEntity),
its install renaming the client jar by this file alone.

Mojang's names composed through them (MojangNames.onSrg) are the table the
agent renames its probe by beside Forge.

- SrgNames: the names read from a tsrg2 or tsrg v1 file's text or its file.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io

#  the tsrg2 file's first line, the one format read here
_HEADER = 'tsrg2 obf srg id'


class SrgNames:
  """
  SRG's names: 'fields' maps (the obfuscated owner, its obfuscated name)
  to SRG's; 'methods' maps (the obfuscated owner, its obfuscated name, its
  obfuscated descriptor) to SRG's; 'classes' maps an obfuscated class to
  the file's name for it. 'renamesClasses' says whether the game runs
  those: a tsrg v1 file's (MCP's class names, before 1.17), not a tsrg2
  file's (Forge runs the game by Mojang's class names from 1.17 on).
  """

  def __init__(self, fields: dict, methods: dict, classes: dict,
               renamesClasses: bool) -> None:
    self.fields = fields
    self.methods = methods
    self.classes = classes
    self.renamesClasses = renamesClasses

  @classmethod
  def fromText(cls, text: str) -> SrgNames:
    """
    The names in a tsrg2 file's text, or a tsrg v1 file's (no header);
    ValueError for another format, or naming the line it can't read.
    """
    lines = text.splitlines()
    if lines and lines[0].strip() != _HEADER and not lines[0].startswith(
        'tsrg'):
      return cls._fromTsrgOne(lines)
    if not lines or lines[0].strip() != _HEADER:
      raise ValueError('not a tsrg2 file of obfuscated to SRG names, nor '
                       'the headerless tsrg of MCP before 1.17: its first '
                       'line is %r' % (lines[0] if lines else ''))
    fields, methods, classes = {}, {}, {}
    owner = None
    for number, line in enumerate(lines[1:], 2):
      if not line.strip() or line.startswith('\t\t'):
        #  a parameter's line, or a method's 'static' mark: no member
        continue
      parts = line.strip().split(' ')
      if not line.startswith('\t') and len(parts) == 3:
        owner = parts[0]
        classes[owner] = parts[1]
      elif owner is not None and len(parts) == 3:
        fields[(owner, parts[0])] = parts[1]
      elif (owner is not None and len(parts) == 4
            and parts[1].startswith('(')):
        methods[(owner, parts[0], parts[1])] = parts[2]
      elif owner is not None and len(parts) == 4:
        #  a field with its descriptor
        fields[(owner, parts[0])] = parts[2]
      else:
        raise ValueError('line %d of the tsrg2 file can\'t be read: %r'
                         % (number, line))
    return cls(fields, methods, classes, False)

  @classmethod
  def _fromTsrgOne(cls, lines: list) -> SrgNames:
    """A tsrg v1 file's names (MCP's before 1.17): its classes the game's."""
    fields, methods, classes = {}, {}, {}
    owner = None
    for number, line in enumerate(lines, 1):
      if not line.strip():
        continue
      parts = line.strip().split(' ')
      if not line.startswith('\t') and len(parts) == 2:
        owner = parts[0]
        classes[owner] = parts[1]
      elif owner is not None and line.startswith('\t') and len(parts) == 2:
        fields[(owner, parts[0])] = parts[1]
      elif (owner is not None and line.startswith('\t') and len(parts) == 3
            and parts[1].startswith('(')):
        methods[(owner, parts[0], parts[1])] = parts[2]
      else:
        raise ValueError('line %d of the tsrg file can\'t be read: %r'
                         % (number, line))
    return cls(fields, methods, classes, True)

  @classmethod
  def fromFile(cls, path: str) -> SrgNames:
    """The names in a tsrg2 or tsrg v1 file (the MCP config's, as Forge keeps it)."""
    with io.open(path, encoding='utf-8') as file:
      return cls.fromText(file.read())

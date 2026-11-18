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

Mojang's names composed through them (MojangNames.onSrg) are the table the
agent renames its probe by beside Forge.

- SrgNames: the names read from a tsrg2 file's text or its file.
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
  obfuscated descriptor) to SRG's. Its classes aren't kept: Forge runs the
  game by Mojang's class names.
  """

  def __init__(self, fields: dict, methods: dict) -> None:
    self.fields = fields
    self.methods = methods

  @classmethod
  def fromText(cls, text: str) -> SrgNames:
    """
    The names in a tsrg2 file's text; ValueError for another format, or
    naming the line it can't read.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != _HEADER:
      raise ValueError('not a tsrg2 file of obfuscated to SRG names: its '
                       'first line is %r' % (lines[0] if lines else ''))
    fields, methods = {}, {}
    owner = None
    for number, line in enumerate(lines[1:], 2):
      if not line.strip() or line.startswith('\t\t'):
        #  a parameter's line, or a method's 'static' mark: no member
        continue
      parts = line.strip().split(' ')
      if not line.startswith('\t') and len(parts) == 3:
        owner = parts[0]
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
    return cls(fields, methods)

  @classmethod
  def fromFile(cls, path: str) -> SrgNames:
    """The names in a tsrg2 file (the MCP config's, as Forge keeps it)."""
    with io.open(path, encoding='utf-8') as file:
      return cls.fromText(file.read())

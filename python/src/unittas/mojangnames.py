"""
The 'mojangnames' module reads Mojang's names for an obfuscated version
(SPEC.md 19.7 step 6b): its obfuscation log, the version JSON's
client_mappings (ProGuard's), which gives every class, field and method
of the client jar by Mojang's name and by the obfuscated one the game
runs under in vanilla (net.minecraft.client.Minecraft is fgo).

The agent's probe for such a version is written in Mojang's names and
renamed as it loads to the running game's, by a table this module writes
(MojangNames.write): one line per class, field and method, in the JVM's
own terms (internal names, descriptors in Mojang's names). The log is
fetched once into the download cache, held to the sha1 its version JSON
gives; it is never shipped (its licence allows use in development, not
handing it on whole).

- MojangNames: the names read, a descriptor as the game runs it, the
  table written, the log loaded by version.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
  from .intermediary import Intermediary
  from .launcher import Sources
  from .srgnames import SrgNames

#  the table's format (the agent's Names reads this one), and its first line:
#  the format, what the names run under, the game
TABLE_FORMAT = '1'
TABLE_HEADER = 'unittas-names\t' + TABLE_FORMAT + '\t%s\t%s'

_PRIMITIVES = {'void': 'V', 'boolean': 'Z', 'byte': 'B', 'char': 'C',
               'short': 'S', 'int': 'I', 'long': 'J', 'float': 'F',
               'double': 'D'}
_NAME = r'[A-Za-z_$<][\w$<>]*'
_TYPE = r'[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*(?:\[\])*'
#  a class may be a package's own (com.mojang.blaze3d.audio.package-info)
_CLASS = r'[A-Za-z_$][\w$-]*(?:\.[A-Za-z_$][\w$-]*)*'
_CLASS_LINE = re.compile(r'^(%s) -> (%s):$' % (_CLASS, _CLASS))
_FIELD_LINE = re.compile(r'^    (%s) (%s) -> (%s)$' % (_TYPE, _NAME, _NAME))
_METHOD_LINE = re.compile(r'^    (?:\d+:\d+:)?(%s) (%s)\(((?:%s(?:,%s)*)?)'
                          r'\) -> (%s)$' % (_TYPE, _NAME, _TYPE, _TYPE,
                                            _NAME))
_CLASS_IN_DESCRIPTOR = re.compile(r'L([^;]+);')


def _internal(name: str) -> str:
  """A class's name as the JVM writes it: net/minecraft/client/Minecraft."""
  return name.replace('.', '/')


def _descriptor(typeName: str) -> str:
  """A type as the log writes it (int[], a.b.C) as a descriptor."""
  dimensions = 0
  while typeName.endswith('[]'):
    typeName = typeName[:-2]
    dimensions += 1
  base = _PRIMITIVES.get(typeName)
  if base is None:
    base = 'L%s;' % _internal(typeName)
  return '[' * dimensions + base


class MojangNames:
  """
  One version's names: 'classes' maps Mojang's internal name to the one
  the game runs under; 'fields' and 'methods' map (Mojang's owner,
  Mojang's name, the descriptor in Mojang's names) to the running name.
  A name the game keeps is in them as itself. 'kind' says what the names
  run under: obfuscated (vanilla), intermediary (beside Fabric: through)
  or srg (beside Forge: onSrg).
  """

  def __init__(self, classes: dict, fields: dict, methods: dict,
               kind: str = 'obfuscated') -> None:
    self.classes = classes
    self.fields = fields
    self.methods = methods
    self.kind = kind

  @classmethod
  def fromText(cls, text: str) -> MojangNames:
    """
    The names in a log's text; ValueError naming the line it can't read,
    or a name given two ways.
    """
    classes, fields, methods = {}, {}, {}
    owner = ''
    for number, line in enumerate(text.splitlines(), 1):
      if not line.strip() or line.lstrip().startswith('#'):
        continue
      found = _CLASS_LINE.match(line)
      if found:
        owner = _internal(found.group(1))
        _put(classes, owner, _internal(found.group(2)), number)
        continue
      if not owner:
        raise ValueError('line %d of the log is a member with no class '
                         'before it: %r' % (number, line))
      found = _METHOD_LINE.match(line)
      if found:
        returned, name, parameters, obfuscated = found.groups()
        descriptor = '(%s)%s' % (''.join(
          _descriptor(each) for each in parameters.split(',') if each),
          _descriptor(returned))
        _put(methods, (owner, name, descriptor), obfuscated, number)
        continue
      found = _FIELD_LINE.match(line)
      if found:
        typeName, name, obfuscated = found.groups()
        _put(fields, (owner, name, _descriptor(typeName)), obfuscated,
             number)
        continue
      raise ValueError('line %d of the log can\'t be read: %r'
                       % (number, line))
    return cls(classes, fields, methods)

  @classmethod
  def load(cls, sources: Sources, minecraft: str) -> MojangNames:
    """
    The version's names from its log: fetched by its version JSON into
    the download cache once, held to its sha1. Missing when the version
    has no log (26.1 and later run under Mojang's own names) or it can't
    be had.
    """
    from .launcher import Missing, _fetched, _versionJson
    vanilla = _versionJson(sources, minecraft)
    entry = vanilla.get('downloads', {}).get('client_mappings')
    if not entry:
      raise Missing('the %s version JSON names no client_mappings: no '
                    'obfuscation log (26.1 and later run under Mojang\'s '
                    'own names)' % minecraft)
    path = _fetched(sources, 'versions/%s/client.txt' % minecraft,
                    entry['url'], 'the %s client\'s obfuscation log'
                    % minecraft, [entry['sha1']])
    with open(path, encoding='utf-8') as file:
      return cls.fromText(file.read())

  def through(self, intermediary: Intermediary,
              supertypes: dict) -> MojangNames:
    """
    The names as Fabric runs the game (SPEC.md 19.7 step 6d): each
    obfuscated name on to intermediary's where it has one; a method it
    names only on the class that first declares it (an override, as
    LocalPlayer's isShiftKeyDown is Entity's) by that class's, found up
    'supertypes' (the obfuscated jar's: classheaders.supertypes); kept
    where none names it (a constructor, a JDK method's override).
    """
    classes = {mojang: intermediary.classes.get(obfuscated, obfuscated)
               for mojang, obfuscated in self.classes.items()}
    fields = {}
    for (owner, name, descriptor), obfuscated in self.fields.items():
      key = (self.classes.get(owner, owner), obfuscated,
             self.running(descriptor))
      fields[(owner, name, descriptor)] = intermediary.fields.get(
        key, obfuscated)
    methods = {}
    for (owner, name, descriptor), obfuscated in self.methods.items():
      methods[(owner, name, descriptor)] = _inherited(
        intermediary, supertypes, self.classes.get(owner, owner),
        obfuscated, self.running(descriptor))
    return MojangNames(classes, fields, methods, 'intermediary')

  def onSrg(self, srg: SrgNames) -> MojangNames:
    """
    The names as Forge runs the game (SPEC.md 19.7 step 8): every class by
    Mojang's name (Forge's install merges Mojang's for classes), each
    field and method on from its obfuscated name to SRG's where the MCP
    config has a line for it (an override's on its own class), kept where
    none does (a constructor, a JDK method's override).
    """
    classes = {mojang: mojang for mojang in self.classes}
    fields = {}
    for (owner, name, descriptor), obfuscated in self.fields.items():
      fields[(owner, name, descriptor)] = srg.fields.get(
        (self.classes.get(owner, owner), obfuscated), obfuscated)
    methods = {}
    for (owner, name, descriptor), obfuscated in self.methods.items():
      key = (self.classes.get(owner, owner), obfuscated,
             self.running(descriptor))
      methods[(owner, name, descriptor)] = srg.methods.get(key, obfuscated)
    return MojangNames(classes, fields, methods, 'srg')

  def running(self, descriptor: str) -> str:
    """A descriptor in Mojang's names as the game runs it."""
    return _CLASS_IN_DESCRIPTOR.sub(
      lambda found: 'L%s;' % self.classes.get(found.group(1),
                                               found.group(1)), descriptor)

  def write(self, path: str, minecraft: str) -> str:
    """
    The agent's table at 'path': its header, then a line per class
    ("c", Mojang's name, the running one), field and method ("f" or "m",
    Mojang's owner, name and descriptor, the running name), tab apart, in
    a fixed order. Written apart and renamed into place.
    """
    lines = ['c\t%s\t%s' % pair for pair in self.classes.items()]
    lines += ['f\t%s\t%s\t%s\t%s' % (key + (name,))
              for key, name in self.fields.items()]
    lines += ['m\t%s\t%s\t%s\t%s' % (key + (name,))
              for key, name in self.methods.items()]
    text = '\n'.join([TABLE_HEADER % (self.kind, minecraft)]
                     + sorted(lines)) + '\n'
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    part = '%s.part-%d' % (path, os.getpid())
    try:
      with open(part, 'w', encoding='utf-8', newline='\n') as file:
        file.write(text)
      os.replace(part, path)
    finally:
      if os.path.exists(part):
        os.remove(part)
    return path


def _put(into: dict, key: object, value: str, number: int) -> None:
  """A name into its map; ValueError if the log gave it another before."""
  known = into.get(key)
  if known is not None and known != value:
    raise ValueError('line %d of the log gives %s as %s, an earlier line '
                     'as %s' % (number, key, value, known))
  into[key] = value


def _inherited(intermediary: Intermediary, supertypes: dict, owner: str,
               name: str, descriptor: str) -> str:
  """
  A method's intermediary name: its class's, else the nearest of its
  supertypes that names it (a level at a time: the superclass and the
  interfaces, then theirs); its obfuscated name where none does.
  """
  seen = set()
  todo = [owner]
  while todo:
    at = todo.pop(0)
    if at in seen or not at:
      continue
    seen.add(at)
    found = intermediary.methods.get((at, name, descriptor))
    if found is not None:
      return found
    superclass, interfaces = supertypes.get(at, ('', ()))
    todo.append(superclass)
    todo.extend(interfaces)
  return name

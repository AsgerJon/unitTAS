"""
The 'mappings' module turns the readable names a test writes in a
reflection path into the running game's (SPEC.md 9.3, step 4; PROTOCOL.md
5.9). For 1.7.10 that is MCP stable_12: its fields.csv and methods.csv
give each Searge name (field_71071_by, func_110143_aJ) its MCP name
(inventory, getHealth).

A readable name can stand for several Searge names, on different classes:
'getHealth' is func_110143_aJ (EntityLivingBase) and func_149332_c. The
orchestrator doesn't know the class a path step lands on, so it sends a
step's candidates, the readable name itself first, and the probe takes the
one the object's class chain has. With the name itself among them, the same
path works in a development client (MCP names), in a real one (Searge
names), and for a mod's own member of that name. A name with no mapping
goes as it is.

The files come from the project's Gradle cache (the CSVs Unimined unpacked,
or the mappings' zip in modules-2), else from Forge's maven into the
download cache, held to the maven's sha1. They are never shipped in the
package (SPEC.md 9.6, decision 7).

- Mappings: the names; 'load' finds the files, 'translate' does a path.
- MappingsMissing: the files are in neither place.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import csv
import glob
import io
import os
import zipfile
from typing import TYPE_CHECKING

from .cache import CacheError

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Optional

  from .launcher import Sources

MAPPINGS = 'de.oceanlabs.mcp:mcp_stable:12-1.7.10'
MAPPINGS_PATH = 'de/oceanlabs/mcp/mcp_stable/12-1.7.10/mcp_stable-12-1.7.10.zip'
MAPPINGS_URL = 'https://maven.minecraftforge.net/' + MAPPINGS_PATH


class MappingsMissing(Exception):
  """MCP stable_12's files are in neither the Gradle cache nor (or not fetched into) the download cache."""


def _read(text: str) -> dict:
  """A CSV's readable names, each to its Searge names in the file's order."""
  names = {}
  for row in csv.DictReader(io.StringIO(text)):
    searge, name = row.get('searge'), row.get('name')
    if searge and name:
      names.setdefault(name, [])
      if searge not in names[name]:
        names[name].append(searge)
  return names


class Mappings:
  """The readable names of fields and of methods, each to its Searge names."""

  def __init__(self, fields: dict, methods: dict) -> None:
    self.__fields__ = fields
    self.__methods__ = methods

  @classmethod
  def fromTexts(cls, fieldsCsv: str, methodsCsv: str) -> Mappings:
    return cls(_read(fieldsCsv), _read(methodsCsv))

  @classmethod
  def load(cls, sources: Sources) -> Mappings:
    """The mappings from the first place that has them; MappingsMissing naming where they were looked for."""
    home = sources.gradleHome
    if home is not None:
      folder = os.path.join(home, 'caches', 'minecraft', 'de', 'oceanlabs', 'mcp', 'mcp_stable', '12')
      fields, methods = os.path.join(folder, 'fields.csv'), os.path.join(folder, 'methods.csv')
      if os.path.isfile(fields) and os.path.isfile(methods):
        with open(fields, encoding='utf-8') as one, open(methods, encoding='utf-8') as two:
          return cls.fromTexts(one.read(), two.read())
      archives = sorted(glob.glob(os.path.join(home, 'caches', 'modules-2', 'files-2.1', 'de.oceanlabs.mcp',
                                               'mcp_stable', '12-1.7.10', '*', 'mcp_stable-12-1.7.10.zip')))
      if archives:
        return cls._fromZip(archives[0])
    if sources.cache is None:
      raise MappingsMissing('MCP\'s mcp_stable 12 (%s) is not in the Gradle cache%s, and no download cache was given'
                            % (MAPPINGS, '' if home else ' (there is none)'))
    try:
      archive = sources.cache.get('libraries/' + MAPPINGS_PATH, MAPPINGS_URL, sha1Url=MAPPINGS_URL + '.sha1',
                                  what=MAPPINGS)
    except CacheError as error:
      raise MappingsMissing(str(error)) from None
    return cls._fromZip(archive)

  @classmethod
  def _fromZip(cls, path: str) -> Mappings:
    with zipfile.ZipFile(path) as archive:
      return cls.fromTexts(archive.read('fields.csv').decode('utf-8'), archive.read('methods.csv').decode('utf-8'))

  def names(self, name: str) -> tuple:
    """A name step's candidates (a field, or else a method with no arguments): the name, then its Searge names."""
    return (name,) + tuple(self.__fields__.get(name, ())) + tuple(
      each for each in self.__methods__.get(name, ()) if each not in self.__fields__.get(name, ()))

  def methods(self, name: str) -> tuple:
    """A call step's candidates: the name, then its methods' Searge names."""
    return (name,) + tuple(self.__methods__.get(name, ()))

  def translate(self, path: list) -> list:
    """
    The path with each readable name given its candidates: a name step as
    {"name": [...]}, a call's {"call": [...]}. Steps with nothing to translate
    (indexes, keys, a name with no mapping, candidates already given) stay as
    they are. The path given isn't changed.
    """
    out = []
    for step in path:
      if isinstance(step, str):
        candidates = self.names(step)
        out.append({'name': list(candidates)} if len(candidates) > 1 else step)
      elif isinstance(step, dict) and isinstance(step.get('call'), str):
        candidates = self.methods(step['call'])
        out.append(dict(step, call=list(candidates)) if len(candidates) > 1 else dict(step))
      else:
        out.append(step)
    return out

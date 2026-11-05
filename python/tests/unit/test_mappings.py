"""
Readable names to the game's (unittas.mappings), without a game: MCP stable_12's fields.csv and methods.csv (Searge's
name to MCP's), read from the Gradle cache's files, from the mappings' zip, or fetched into the download cache. A
readable name in a reflection path becomes the list of its candidates, itself first, so the same path works in a
development client (MCP names) and a real one (Searge names); a mod's own name passes through as it is.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import hashlib
import io
import os
import shutil
import tempfile
import unittest
import zipfile

from unittas.cache import Cache
from unittas.launcher import Sources
from unittas.mappings import MAPPINGS_URL, Mappings, MappingsMissing

FIELDS = """searge,name,side,desc
field_71071_by,inventory,2,Inventory of the player
field_75224_c,inventory,2,The inventory we want to extract a slot from.
field_70461_c,currentItem,2,The index of the currently held item (0-8).
"""
METHODS = """searge,name,side,desc
func_110143_aJ,getHealth,2,
func_149332_c,getHealth,0,
func_70448_g,getCurrentItem,2,Returns the item stack currently held by the player.
func_71071_by,inventory,2,a method sharing a field's readable name (not in 1.7.10: here to check both are kept)
"""


def zipped() -> bytes:
  out = io.BytesIO()
  with zipfile.ZipFile(out, 'w') as archive:
    archive.writestr('fields.csv', FIELDS)
    archive.writestr('methods.csv', METHODS)
    archive.writestr('params.csv', 'param,name,side\n')
  return out.getvalue()


class MappingsTests(unittest.TestCase):

  def setUp(self) -> None:
    self.scratch = tempfile.mkdtemp(prefix='unittas-mappings-')
    self.addCleanup(shutil.rmtree, self.scratch)

  def gradleHome(self, csvs: bool = True, archive: bool = False) -> str:
    home = os.path.join(self.scratch, 'gradle-home')
    if csvs:
      folder = os.path.join(home, 'caches', 'minecraft', 'de', 'oceanlabs', 'mcp', 'mcp_stable', '12')
      os.makedirs(folder)
      for name, text in (('fields.csv', FIELDS), ('methods.csv', METHODS)):
        with open(os.path.join(folder, name), 'w', encoding='utf-8') as file:
          file.write(text)
    if archive:
      folder = os.path.join(home, 'caches', 'modules-2', 'files-2.1', 'de.oceanlabs.mcp', 'mcp_stable', '12-1.7.10',
                            'abc123')
      os.makedirs(folder)
      with open(os.path.join(folder, 'mcp_stable-12-1.7.10.zip'), 'wb') as file:
        file.write(zipped())
    os.makedirs(home, exist_ok=True)
    return home

  def test_candidates(self) -> None:
    mappings = Mappings.load(Sources(gradleHome=self.gradleHome()))
    self.assertEqual(('inventory', 'field_71071_by', 'field_75224_c', 'func_71071_by'), mappings.names('inventory'))
    self.assertEqual(('getHealth', 'func_110143_aJ', 'func_149332_c'), mappings.methods('getHealth'))
    self.assertEqual(('inventory', 'func_71071_by'), mappings.methods('inventory'))
    self.assertEqual(('myModsOwn',), mappings.names('myModsOwn'), 'a name with no mapping is itself only')

  def test_a_path_translated(self) -> None:
    mappings = Mappings.load(Sources(gradleHome=self.gradleHome()))
    path = ['inventory', {'call': 'getCurrentItem'}, {'index': 0}, {'key': 'x'}, 'myModsOwn',
            {'call': 'getHealth', 'args': [1], 'sig': '(I)F'}]
    self.assertEqual([
      {'name': ['inventory', 'field_71071_by', 'field_75224_c', 'func_71071_by']},
      {'call': ['getCurrentItem', 'func_70448_g']},
      {'index': 0}, {'key': 'x'},
      'myModsOwn',
      {'call': ['getHealth', 'func_110143_aJ', 'func_149332_c'], 'args': [1], 'sig': '(I)F'},
    ], mappings.translate(path))
    self.assertEqual({'call': 'getCurrentItem'}, path[1], 'the path given is left as it was')
    self.assertEqual([{'name': ['x', 'y']}], mappings.translate([{'name': ['x', 'y']}]), 'candidates given stay')

  def test_from_the_zip_in_the_gradle_cache(self) -> None:
    mappings = Mappings.load(Sources(gradleHome=self.gradleHome(csvs=False, archive=True)))
    self.assertEqual(('getHealth', 'func_110143_aJ', 'func_149332_c'), mappings.methods('getHealth'))

  def test_fetched_into_the_download_cache(self) -> None:
    data = zipped()
    asked = []
    served = {MAPPINGS_URL: data, MAPPINGS_URL + '.sha1': hashlib.sha1(data).hexdigest().encode('ascii')}

    def fetch(url: str) -> bytes:
      asked.append(url)
      return served[url]

    cache = Cache(os.path.join(self.scratch, 'cache'), fetch=fetch)
    mappings = Mappings.load(Sources(gradleHome=None, cache=cache))
    self.assertEqual(('currentItem', 'field_70461_c'), mappings.names('currentItem'))
    self.assertTrue(MAPPINGS_URL.startswith('https://maven.minecraftforge.net/'))
    Mappings.load(Sources(gradleHome=None, cache=cache))
    self.assertEqual(2, len(asked), 'the second load fetches nothing')

  def test_none_to_be_had(self) -> None:
    with self.assertRaises(MappingsMissing) as missing:
      Mappings.load(Sources(gradleHome=None, cache=None))
    self.assertIn('mcp_stable', str(missing.exception))


if __name__ == '__main__':
  unittest.main()

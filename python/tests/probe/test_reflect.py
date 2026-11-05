"""
Step 7 of phase 2 (SPEC.md section 8.3): SNBT and reflection. NBT through an item, a chest and a pig, every type of
it round-tripped through the game; reflect.get and reflect.set with each kind of from and each kind of step, refs and
their release, the warning for a ref used on the other side, overloads (ambiguous ones naming their candidates), and
screen.open by class. One launch, in a world of its own; each test starts from a reset.

  python -m unittas.selftest test_reflect.      (through the watcher: "probe test_reflect.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from probegame import READY_SECONDS, ROOT, results
from unittas.dev import DevGame
from unittas.errors import BadRequest, NotFound
from unittas.launcher import Sources
from unittas.mappings import Mappings
from unittas.reset import reset
from unittas.snbt import Byte, Float, Short, dumps, loads

EVERY_TYPE = ('{b:1b,s:2s,i:3,l:4L,f:5.5f,d:6.25d,str:"seven",list:[1,2,3],bytes:[B;1b,2b],ints:[I;1,2],'
              'comp:{x:1},"odd key":"v"}')


class ReflectTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.game = DevGame(ROOT, results(), 'reflect')
    shutil.rmtree(os.path.join(cls.game.gameDir, 'saves', 'unittas'), ignore_errors=True)
    cls.connection = cls.game.start()
    cls.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    cls.connection.request('world.create', {}, timeout=240)
    cls.connection.request('world.rules.set', {'rules': {'doDaylightCycle': False, 'doMobSpawning': False}})

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop()

  def setUp(self) -> None:
    reset(self.connection)

  def request(self, op, args=None, side=None, timeout=60.0):
    return self.connection.request(op, args, side=side, timeout=timeout)

  def reflect(self, args, side='server', op='reflect.get'):
    return self.request(op, args, side=side)

  # ---------------------------------------------------------------- SNBT

  def test_01_every_type_through_an_item(self) -> None:
    self.request('inventory.set', {'slot': 'held', 'item': {'id': 'minecraft:stick', 'nbt': EVERY_TYPE}})
    held = self.request('inventory.get', {'slot': 'held'})
    self.assertEqual(loads(EVERY_TYPE), loads(held['nbt']))
    tree = loads(held['nbt'])
    self.assertIs(Byte, type(tree['b']))
    self.assertIs(Float, type(tree['f']))

  def test_02_an_enchanted_name(self) -> None:
    nbt = '{display:{Name:"Red"},ench:[{id:16s,lvl:5s}]}'
    self.request('inventory.set', {'slot': 'held', 'item': {'id': 'minecraft:diamond_sword', 'nbt': nbt}})
    tree = loads(self.request('inventory.get', {'slot': 'held'})['nbt'])
    self.assertEqual('Red', tree['display']['Name'])
    self.assertIs(Short, type(tree['ench'][0]['lvl']))
    seen = self.request('wait.until', {'side': 'client', 'op': 'inventory.get', 'args': {'slot': 'held'},
                                       'max_ticks': 40, 'test': {'path': ['nbt'], 'contains': 'Red'}})
    self.assertTrue(seen['held'], 'the client has the tag too')

  def test_03_a_chest_s_tile(self) -> None:
    self.request('block.set', {'pos': [3, 4, 3], 'block': {'id': 'minecraft:chest'},
                               'tile': '{Items:[{Slot:0b,id:264s,Count:7b,Damage:0s}]}'})
    chest = self.request('block.get', {'pos': [3, 4, 3], 'tile': True})
    self.assertEqual('minecraft:chest', chest['id'])
    items = loads(chest['tile'])['Items']
    self.assertEqual(1, len(items))
    self.assertEqual(7, items[0]['Count'])
    self.assertIsNone(self.request('block.get', {'pos': [0, 3, 0], 'tile': True}).get('tile'), 'grass has no tile')

  def test_04_a_pig_s_nbt(self) -> None:
    pig = self.request('entity.spawn', {'type': 'Pig', 'pos': [5.5, 4.0, 5.5], 'nbt': '{Saddle:1b}'})
    tree = loads(self.request('entity.get', {'entity': pig['entity'], 'nbt': True})['nbt'])
    self.assertEqual(1, tree['Saddle'])
    self.assertIn('Health', tree)
    with self.assertRaises(BadRequest):
      self.request('inventory.set', {'slot': 'held', 'item': {'id': 'minecraft:stick', 'nbt': '{broken'}})

  # ---------------------------------------------------------------- reflection

  def test_05_a_field_set_and_read(self) -> None:
    self.assertEqual(0, self.reflect({'from': 'player', 'path': ['inventory', 'currentItem']}))
    self.reflect({'from': 'player', 'path': ['inventory', 'currentItem'], 'value': 3}, op='reflect.set')
    self.assertEqual(3, self.reflect({'from': 'player', 'path': ['inventory', 'currentItem']}))
    self.assertEqual(3, self.request('inventory.get')['selected'])

  def test_06_methods_and_the_kinds_of_value(self) -> None:
    self.assertEqual(20.0, self.reflect({'from': 'player', 'path': [{'call': 'getHealth'}]}))
    self.assertEqual(self.request('player.get')['name'], self.reflect({'from': 'player', 'path': ['getCommandSenderName']}))
    self.assertIsNone(self.reflect({'from': 'player', 'path': ['inventory', 'mainInventory', {'index': 0}]}))
    self.assertEqual('EASY', self.reflect({'from': 'world', 'path': ['difficultySetting']}), 'an enum by its name')
    self.assertEqual(36, len(self.reflect({'from': 'player', 'path': ['inventory', 'mainInventory']})))
    text = self.reflect({'from': 'player', 'path': [], 'as': 'text'})
    self.assertIn('EntityPlayerMP', text)
    me = self.reflect({'from': 'player', 'path': []})
    self.assertEqual(self.request('player.get')['entity'], me['entity'], 'an entity comes as its summary')

  def test_07_refs_from_a_class_and_new(self) -> None:
    diamond = self.reflect({'from': {'class': 'net.minecraft.init.Items'}, 'path': ['diamond']})
    self.assertIn('ref', diamond)
    self.assertTrue(diamond['class'].endswith('Item'))
    self.assertEqual('item.diamond', self.reflect({'from': {'ref': diamond['ref']}, 'path': ['getUnlocalizedName']}))
    stack = self.reflect({'from': {'new': 'net.minecraft.item.ItemStack', 'args': [{'ref': diamond['ref']}, 2]},
                          'path': []})
    self.assertEqual({'id': 'minecraft:diamond', 'count': 2, 'meta': 0}, stack)
    self.assertIn('ref', self.reflect({'from': 'player', 'path': ['inventory'], 'as': 'ref'}))

  def test_08_overloads(self) -> None:
    with self.assertRaises(BadRequest) as caught:
      self.reflect({'from': {'class': 'java.lang.Math'}, 'path': [{'call': 'max', 'args': [1, 2]}]})
    self.assertIn('max', caught.exception.message)
    self.assertIn('(II)I', caught.exception.message, 'the candidates are named, by their signatures')
    self.assertEqual(2, self.reflect({'from': {'class': 'java.lang.Math'},
                                      'path': [{'call': 'max', 'args': [1, 2], 'sig': '(II)I'}]}))

  def test_09_not_found_says_what(self) -> None:
    with self.assertRaises(NotFound) as caught:
      self.reflect({'from': 'player', 'path': ['wobble']})
    self.assertIn('wobble', caught.exception.message)
    with self.assertRaises(NotFound):
      self.reflect({'from': {'class': 'com.example.Nothing'}, 'path': []})
    with self.assertRaises(BadRequest):
      self.request('reflect.get', {'from': 'player', 'path': []})

  def test_10_a_ref_on_the_other_side(self) -> None:
    inventory = self.reflect({'from': 'player', 'path': ['inventory'], 'as': 'ref'})
    pending = self.connection.send('reflect.get', {'from': {'ref': inventory['ref']}, 'path': ['currentItem']},
                                   side='client')
    self.assertEqual(0, pending.result(30))
    self.assertTrue(pending.warnings, 'a server ref read on the client thread is warned of')

  def test_11_refs_released(self) -> None:
    kept = self.reflect({'from': 'player', 'path': ['inventory'], 'as': 'ref'})
    self.request('refs.release', {'refs': [kept['ref']]})
    with self.assertRaises(NotFound):
      self.reflect({'from': {'ref': kept['ref']}, 'path': []})
    again = self.reflect({'from': 'player', 'path': ['inventory'], 'as': 'ref'})
    self.request('refs.clear')
    with self.assertRaises(NotFound):
      self.reflect({'from': {'ref': again['ref']}, 'path': []})

  def test_12_screen_by_class(self) -> None:
    self.request('screen.open', {'screen': {'class': 'net.minecraft.client.gui.GuiIngameMenu'}})
    self.assertTrue(self.request('screen.get')['class'].endswith('GuiIngameMenu'))
    self.request('screen.close')

  def test_13_refs_go_with_their_world(self) -> None:
    kept = self.reflect({'from': 'player', 'path': ['inventory'], 'as': 'ref'})
    self.request('world.close', timeout=240)
    self.request('world.open', {'folder': 'unittas'}, timeout=240)
    with self.assertRaises(NotFound) as caught:
      self.reflect({'from': {'ref': kept['ref']}, 'path': []})
    self.assertIn('closed', caught.exception.message)

  # ---------------------------------------------------------------- candidate names (phase 3, step 4)

  def test_13a_the_candidate_the_class_has(self) -> None:
    path = [{'name': ['noSuchField', 'inventory', 'field_71071_by']}, 'currentItem']
    self.assertEqual(0, self.reflect({'from': 'player', 'path': path}))
    self.assertEqual(20.0, self.reflect({'from': 'player', 'path': [{'call': ['func_110143_aJ', 'getHealth']}]}))

  def test_13b_several_fit_or_none(self) -> None:
    with self.assertRaises(BadRequest) as several:
      self.reflect({'from': 'player', 'path': [{'name': ['inventory', 'inventoryContainer']}]})
    self.assertIn('inventoryContainer', several.exception.message)
    with self.assertRaises(NotFound) as none:
      self.reflect({'from': 'player', 'path': [{'name': ['noSuchField', 'norThisOne']}]})
    self.assertIn('norThisOne', none.exception.message)
    with self.assertRaises(NotFound):
      self.reflect({'from': 'player', 'path': [{'call': ['noSuchMethod', 'norThisOne']}]})

  def test_13c_set_by_candidates(self) -> None:
    path = [{'name': ['inventory', 'field_71071_by']}, {'name': ['currentItem', 'field_70461_c']}]
    self.reflect({'from': 'player', 'path': path, 'value': 4}, op='reflect.set')
    self.assertEqual(4, self.reflect({'from': 'player', 'path': ['inventory', 'currentItem']}))

  def test_13d_a_path_translated_from_the_mappings(self) -> None:
    mappings = Mappings.load(Sources(gradleHome=os.path.join(ROOT, '.gradle-home')))
    self.assertEqual(0, self.reflect({'from': 'player', 'path': mappings.translate(['inventory', 'currentItem'])}))
    self.assertEqual(20.0, self.reflect({'from': 'player', 'path': mappings.translate([{'call': 'getHealth'}])}))

  def test_14_quit(self) -> None:
    self.assertEqual({}, self.request('quit', {'reason': 'test_14'}))
    self.assertTrue(self.game.ended(120))


if __name__ == '__main__':
  unittest.main()

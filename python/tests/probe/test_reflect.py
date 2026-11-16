"""
SNBT and reflection on the run's port (SPEC.md 8.3, 19.7 step 4). NBT through an item (26.3: its custom data
component), a chest and a pig, every type of it round-tripped through the game; reflect.get and reflect.set with each
kind of from and each kind of step, refs and their release, the warning for a ref used on the other side, overloads
(ambiguous ones naming their candidates), candidate names, and screen.open by class. Each member is named as the port's
version names it (1.7.10's MCP in its development client, 26.3's Mojang's): the NAMES table. One launch, in a world of
its own; each test starts from a reset.

  python -m unittas.selftest test_reflect.
  (through the watcher: "probe test_reflect.", "probe test_reflect on 26.3-fabric")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from mcdex import MCEntities

from ports import FABRIC_26_3, FORGE_1_7_10, at, onlyOn, point, port, probeGame, start
from probegame import READY_SECONDS, ROOT
from unittas.api import Game
from unittas.errors import BadRequest, NotFound
from unittas.launcher import Sources
from unittas.mappings import Mappings
from unittas.reset import reset
from unittas.snbt import Byte, Float, Short, loads
from unittas.things import entityOf
from unittas.codec import toJson

EVERY_TYPE = ('{b:1b,s:2s,i:3,l:4L,f:5.5f,d:6.25d,str:"seven",list:[1,2,3],bytes:[B;1b,2b],ints:[I;1,2],'
              'comp:{x:1},"odd key":"v"}')
#  what the tests reach, as each version names it
NAMES = {
  'inventory': {FORGE_1_7_10: 'inventory', FABRIC_26_3: 'inventory'},
  'selected slot': {FORGE_1_7_10: 'currentItem', FABRIC_26_3: 'selected'},
  'main slots': {FORGE_1_7_10: 'mainInventory', FABRIC_26_3: 'items'},
  'player name': {FORGE_1_7_10: 'getCommandSenderName', FABRIC_26_3: 'getScoreboardName'},
  'difficulty': {FORGE_1_7_10: 'difficultySetting', FABRIC_26_3: {'call': 'getDifficulty'}},
  'server player': {FORGE_1_7_10: 'EntityPlayerMP', FABRIC_26_3: 'ServerPlayer'},
  'items': {FORGE_1_7_10: 'net.minecraft.init.Items', FABRIC_26_3: 'net.minecraft.world.item.Items'},
  'diamond': {FORGE_1_7_10: 'diamond', FABRIC_26_3: 'DIAMOND'},
  'translation key': {FORGE_1_7_10: 'getUnlocalizedName', FABRIC_26_3: 'getDescriptionId'},
  "diamond's key": {FORGE_1_7_10: 'item.diamond', FABRIC_26_3: 'item.minecraft.diamond'},
  'item stack': {FORGE_1_7_10: 'net.minecraft.item.ItemStack', FABRIC_26_3: 'net.minecraft.world.item.ItemStack'},
  'two diamonds': {FORGE_1_7_10: {'id': 'minecraft:diamond', 'count': 2, 'meta': 0},
                   FABRIC_26_3: {'id': 'minecraft:diamond', 'count': 2}},
  #  a pause screen's class and its constructor's arguments
  'pause screen': {FORGE_1_7_10: ('net.minecraft.client.gui.GuiIngameMenu', []),
                   FABRIC_26_3: ('net.minecraft.client.gui.screens.PauseScreen', [True])},
  "the player's other inventory": {FORGE_1_7_10: 'inventoryContainer', FABRIC_26_3: 'inventoryMenu'},
  #  as the orchestrator sends a readable name with its Searge names (1.7.10), or with a name no class has (26.3)
  'inventory or else': {FORGE_1_7_10: ['noSuchField', 'inventory', 'field_71071_by'],
                        FABRIC_26_3: ['noSuchField', 'inventory']},
  'getHealth or else': {FORGE_1_7_10: ['func_110143_aJ', 'getHealth'], FABRIC_26_3: ['noSuchMethod', 'getHealth']},
  'selected slot or else': {FORGE_1_7_10: ['currentItem', 'field_70461_c'], FABRIC_26_3: ['selected', 'noSuchField']},
  #  a chest of seven diamonds, as each version writes its items; their count's name
  'seven diamonds': {FORGE_1_7_10: ('{Items:[{Slot:0b,id:264s,Count:7b,Damage:0s}]}', 'Count'),
                     FABRIC_26_3: ('{Items:[{Slot:0b,id:"minecraft:diamond",count:7}]}', 'count')},
  #  a pig's tag that each version keeps
  "a pig's tag": {FORGE_1_7_10: ('{Saddle:1b}', 'Saddle'), FABRIC_26_3: ('{Invulnerable:1b}', 'Invulnerable')},
}


def name(what: str):
  return NAMES[what][port()]


class ReflectTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.game = probeGame('reflect')
    shutil.rmtree(os.path.join(cls.game.gameDir, 'saves', 'unittas'), ignore_errors=True)
    cls.connection = cls.game.start(READY_SECONDS)
    cls.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    cls.connection.request('world.create', {}, timeout=240)
    cls.connection.request('world.prepare')

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop()

  def setUp(self) -> None:
    reset(self.connection, at=start())

  def request(self, op, args=None, side=None, timeout=60.0):
    return self.connection.request(op, args, side=side, timeout=timeout)

  def reflect(self, args, side='server', op='reflect.get'):
    return self.request(op, args, side=side)

  # ---------------------------------------------------------------- SNBT

  def test_01_every_type_through_an_item(self) -> None:
    """1.7.10: the item's NBT; 26.3: its custom data component, NBT as any other."""
    if port() == FORGE_1_7_10:
      self.request('inventory.set', {'slot': 'held', 'item': {'id': 'minecraft:stick', 'nbt': EVERY_TYPE}})
      tree = loads(self.request('inventory.get', {'slot': 'held'})['nbt'])
    else:
      components = '{"minecraft:custom_data":%s}' % EVERY_TYPE
      self.request('inventory.set', {'slot': 'held', 'item': {'id': 'minecraft:stick', 'components': components}})
      tree = loads(self.request('inventory.get', {'slot': 'held'})['components'])['minecraft:custom_data']
    self.assertEqual(loads(EVERY_TYPE), tree)
    self.assertIs(Byte, type(tree['b']))
    self.assertIs(Float, type(tree['f']))

  @onlyOn(FORGE_1_7_10, why="26.3's names and enchantments are components (test_values has an item's name)")
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
    tile, count = name('seven diamonds')
    self.request('block.set', {'pos': toJson(at(3, 4, 3)), 'block': {'id': 'minecraft:chest'}, 'tile': tile})
    chest = self.request('block.get', {'pos': toJson(at(3, 4, 3)), 'tile': True})
    self.assertEqual('minecraft:chest', chest['id'])
    items = loads(chest['tile'])['Items']
    self.assertEqual(1, len(items))
    self.assertEqual(7, items[0][count])
    self.assertIsNone(self.request('block.get', {'pos': toJson(at(0, 3, 0)), 'tile': True}).get('tile'),
                      'grass has no tile')

  def test_04_a_pig_s_nbt(self) -> None:
    kind, _ = entityOf(MCEntities.Pig, Game(self.connection).version)
    nbt, key = name("a pig's tag")
    pig = self.request('entity.spawn', {'type': kind, 'pos': toJson(point(5.5, 4.0, 5.5)), 'nbt': nbt})
    tree = loads(self.request('entity.get', {'entity': pig['entity'], 'nbt': True})['nbt'])
    self.assertEqual(1, tree[key])
    self.assertIn('Health', tree)
    data = 'nbt' if port() == FORGE_1_7_10 else 'components'
    with self.assertRaises(BadRequest):
      self.request('inventory.set', {'slot': 'held', 'item': {'id': 'minecraft:stick', data: '{broken'}})

  # ---------------------------------------------------------------- reflection

  def test_05_a_field_set_and_read(self) -> None:
    slot = [name('inventory'), name('selected slot')]
    self.assertEqual(0, self.reflect({'from': 'player', 'path': slot}))
    self.reflect({'from': 'player', 'path': slot, 'value': 3}, op='reflect.set')
    self.assertEqual(3, self.reflect({'from': 'player', 'path': slot}))
    self.assertEqual(3, self.request('inventory.get')['selected'])

  def test_06_methods_and_the_kinds_of_value(self) -> None:
    self.assertEqual(20.0, self.reflect({'from': 'player', 'path': [{'call': 'getHealth'}]}))
    self.assertEqual(self.request('player.get')['name'], self.reflect({'from': 'player', 'path': [name('player name')]}))
    self.assertIsNone(self.reflect({'from': 'player', 'path': [name('inventory'), name('main slots'), {'index': 0}]}))
    self.assertEqual(self.request('world.get')['difficulty'].upper(),
                     self.reflect({'from': 'world', 'path': [name('difficulty')]}), 'an enum by its name')
    self.assertEqual(36, len(self.reflect({'from': 'player', 'path': [name('inventory'), name('main slots')]})))
    text = self.reflect({'from': 'player', 'path': [], 'as': 'text'})
    self.assertIn(name('server player'), text)
    me = self.reflect({'from': 'player', 'path': []})
    self.assertEqual(self.request('player.get')['entity'], me['entity'], 'an entity comes as its summary')

  def test_07_refs_from_a_class_and_new(self) -> None:
    diamond = self.reflect({'from': {'class': name('items')}, 'path': [name('diamond')]})
    self.assertIn('ref', diamond)
    self.assertTrue(diamond['class'].endswith('Item'))
    self.assertEqual(name("diamond's key"),
                     self.reflect({'from': {'ref': diamond['ref']}, 'path': [name('translation key')]}))
    stack = self.reflect({'from': {'new': name('item stack'), 'args': [{'ref': diamond['ref']}, 2]}, 'path': []})
    self.assertEqual(name('two diamonds'), stack)
    self.assertIn('ref', self.reflect({'from': 'player', 'path': [name('inventory')], 'as': 'ref'}))

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
    inventory = self.reflect({'from': 'player', 'path': [name('inventory')], 'as': 'ref'})
    pending = self.connection.send('reflect.get', {'from': {'ref': inventory['ref']}, 'path': [name('selected slot')]},
                                   side='client')
    self.assertEqual(0, pending.result(30))
    self.assertTrue(pending.warnings, 'a server ref read on the client thread is warned of')

  def test_11_refs_released(self) -> None:
    kept = self.reflect({'from': 'player', 'path': [name('inventory')], 'as': 'ref'})
    self.request('refs.release', {'refs': [kept['ref']]})
    with self.assertRaises(NotFound):
      self.reflect({'from': {'ref': kept['ref']}, 'path': []})
    again = self.reflect({'from': 'player', 'path': [name('inventory')], 'as': 'ref'})
    self.request('refs.clear')
    with self.assertRaises(NotFound):
      self.reflect({'from': {'ref': again['ref']}, 'path': []})

  def test_12_screen_by_class(self) -> None:
    screen, args = name('pause screen')
    self.request('screen.open', {'screen': {'class': screen, 'args': args}})
    self.assertEqual(screen, self.request('screen.get')['class'])
    self.request('screen.close')

  def test_13_refs_go_with_their_world(self) -> None:
    kept = self.reflect({'from': 'player', 'path': [name('inventory')], 'as': 'ref'})
    self.request('world.close', timeout=240)
    self.request('world.open', {'folder': 'unittas'}, timeout=240)
    with self.assertRaises(NotFound) as caught:
      self.reflect({'from': {'ref': kept['ref']}, 'path': []})
    self.assertIn('closed', caught.exception.message)

  # ---------------------------------------------------------------- candidate names (phase 3, step 4)

  def test_13a_the_candidate_the_class_has(self) -> None:
    path = [{'name': name('inventory or else')}, name('selected slot')]
    self.assertEqual(0, self.reflect({'from': 'player', 'path': path}))
    self.assertEqual(20.0, self.reflect({'from': 'player', 'path': [{'call': name('getHealth or else')}]}))

  def test_13b_several_fit_or_none(self) -> None:
    other = name("the player's other inventory")
    with self.assertRaises(BadRequest) as several:
      self.reflect({'from': 'player', 'path': [{'name': [name('inventory'), other]}]})
    self.assertIn(other, several.exception.message)
    with self.assertRaises(NotFound) as none:
      self.reflect({'from': 'player', 'path': [{'name': ['noSuchField', 'norThisOne']}]})
    self.assertIn('norThisOne', none.exception.message)
    with self.assertRaises(NotFound):
      self.reflect({'from': 'player', 'path': [{'call': ['noSuchMethod', 'norThisOne']}]})

  def test_13c_set_by_candidates(self) -> None:
    path = [{'name': name('inventory or else')}, {'name': name('selected slot or else')}]
    self.reflect({'from': 'player', 'path': path, 'value': 4}, op='reflect.set')
    self.assertEqual(4, self.reflect({'from': 'player', 'path': [name('inventory'), name('selected slot')]}))

  @onlyOn(FORGE_1_7_10, why='26.3 is unobfuscated: its names are the game\'s own, nothing is translated')
  def test_13d_a_path_translated_from_the_mappings(self) -> None:
    mappings = Mappings.load(Sources(gradleHome=os.path.join(ROOT, '.gradle-home')))
    self.assertEqual(0, self.reflect({'from': 'player', 'path': mappings.translate(['inventory', 'currentItem'])}))
    self.assertEqual(20.0, self.reflect({'from': 'player', 'path': mappings.translate([{'call': 'getHealth'}])}))

  def test_14_quit(self) -> None:
    self.assertEqual({}, self.request('quit', {'reason': 'test_14'}))
    self.assertTrue(self.game.ended(120))


if __name__ == '__main__':
  unittest.main()

"""
Step 9 of phase 2 (SPEC.md section 8.3): the real client. The release jar, as a player has it, beside UniMixins in a
real 1.7.10 Forge client that unitTAS's own launcher starts in run/release. Its probe says hello naming Minecraft by
Searge's names, all nine mixins are in, and the core works there: a world, a command, the inventory, the reset,
reflection by SRG names (an MCP name is NotFound), and java.run (the jar holds no suites: Ran 0 tests, OK). One launch,
its tests in order.

  python -m unittas.selftest test_realclient.      (through the watcher: "probe test_realclient.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import unittest

from probegame import GONE_SECONDS, MIXINS, READY_SECONDS, ROOT, modVersion, results
from unittas.errors import NotFound
from unittas.release import ReleaseGame
from unittas.reset import reset
from unittas.wire import Role

WOOL = {'id': 'minecraft:wool', 'count': 3, 'meta': 14}
#  Searge's names of the members the reflection tests use (MCP stable_12's fields.csv and methods.csv)
INVENTORY = 'field_71071_by'  # EntityPlayer.inventory
CURRENT_ITEM = 'field_70461_c'  # InventoryPlayer.currentItem
CAPABILITIES = 'field_71075_bZ'  # EntityPlayer.capabilities
IS_CREATIVE = 'field_75098_d'  # PlayerCapabilities.isCreativeMode
GET_HEALTH = 'func_110143_aJ'  # EntityLivingBase.getHealth
GET_CURRENT_ITEM = 'func_70448_g'  # InventoryPlayer.getCurrentItem
GET_DISPLAY_NAME = 'func_82833_r'  # ItemStack.getDisplayName


class RealClientTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.game = ReleaseGame(ROOT, results(), 'realclient')
    shutil.rmtree(os.path.join(cls.game.gameDir, 'saves', 'unittas'), ignore_errors=True)
    cls.connection = cls.game.start()
    cls.ready = cls.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop()

  def request(self, op, args=None, side=None, timeout=60.0):
    return self.connection.request(op, args, side=side, timeout=timeout)

  def reflect(self, path, side='server'):
    return self.request('reflect.get', {'from': 'player', 'path': path}, side=side)

  def test_01_the_hello(self) -> None:
    hello = self.connection.hello
    self.assertEqual('srg', hello.names, 'a real client names Minecraft by Searge')
    self.assertFalse(hello.development)
    self.assertEqual(modVersion(), hello.probeVersion)
    self.assertEqual('1.7.10-forge', hello.probePort)
    self.assertEqual(('forge', '10.13.4.1614'), (hello.loaderName, hello.loaderVersion))
    self.assertIs(Role.CLIENT, hello.role)
    self.assertRegex(hello.javaVersion, r'^1\.8\.')
    self.assertTrue(hello.gameDir.endswith('run/release'), hello.gameDir)
    self.assertIn('java.run', hello.ops)

  def test_02_ready_with_every_mixin(self) -> None:
    self.assertEqual(sorted(MIXINS), sorted(self.ready['mixins']['applied']))
    self.assertEqual([], self.ready['mixins']['missing'])
    unittas = [mod for mod in self.ready['mods'] if mod['id'] == 'unittas']
    self.assertEqual(1, len(unittas), self.ready['mods'])
    self.assertEqual(modVersion(), unittas[0]['version'])
    jars = self.game.mods()
    self.assertTrue(any(jar.startswith('unittas-') for jar in jars), jars)
    self.assertTrue(any(jar.startswith('unimixins-') for jar in jars), jars)

  def test_03_a_world(self) -> None:
    made = self.request('world.create', {}, timeout=240)
    self.assertEqual('unittas', made['folder'])
    self.assertEqual('world', self.request('status')['state'])

  def test_04_a_command(self) -> None:
    said = self.request('command.run', {'command': '/time set 6000'})
    self.assertEqual(1, said['result'])
    self.assertTrue(any('6000' in line for line in said['lines']), said)

  def test_05_the_inventory(self) -> None:
    self.request('inventory.set', {'slot': 'held', 'item': WOOL})
    self.assertEqual(WOOL, self.request('inventory.get', {'slot': 'held'}))

  def test_06_reflection_by_srg_names(self) -> None:
    self.assertEqual(0, self.reflect([INVENTORY, CURRENT_ITEM]))
    self.assertEqual(20.0, self.reflect([{'call': GET_HEALTH}]))
    self.assertIs(True, self.reflect([CAPABILITIES, IS_CREATIVE]))
    self.assertEqual('Red Wool', self.reflect([INVENTORY, {'call': GET_CURRENT_ITEM}, {'call': GET_DISPLAY_NAME}]))
    self.assertEqual('Red Wool', self.reflect([INVENTORY, {'call': GET_CURRENT_ITEM}, {'call': GET_DISPLAY_NAME}],
                                              side='client'))

  def test_07_an_mcp_name_is_not_found(self) -> None:
    with self.assertRaises(NotFound):
      self.reflect(['inventory'])
    with self.assertRaises(NotFound):
      self.reflect([{'call': 'getHealth'}])

  def test_08_the_reset(self) -> None:
    self.request('player.teleport', {'pos': [20.5, 4.0, 20.5]})
    reset(self.connection)
    self.assertIsNone(self.request('inventory.get', {'slot': 'held'}))
    self.assertEqual([0.5, 4.0, 0.5], self.request('player.get')['pos'])

  def test_09_java_run_finds_no_suites(self) -> None:
    self.request('world.close', timeout=240)
    folder = os.path.join(self.game.results, 'java')
    value = self.request('java.run', {'results': folder}, timeout=600)
    self.assertTrue(value['ok'], value)
    self.assertEqual(0, value['counts']['ran'])
    with open(value['report'], encoding='utf-8') as report:
      lines = [line for line in report.read().split('\n') if line.strip()]
    self.assertTrue(lines[-2].startswith('Ran 0 tests'), lines[-2:])
    self.assertEqual('OK', lines[-1])
    self.assertEqual('menu', self.request('status')['state'])

  def test_10_quit(self) -> None:
    self.assertEqual({}, self.request('quit', {'reason': 'test_10'}))
    self.assertTrue(self.game.ended(GONE_SECONDS))


if __name__ == '__main__':
  unittest.main()

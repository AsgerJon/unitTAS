"""
The game's API (unittas.api.Game), without a game: a fake probe answers. Each helper sends the request PROTOCOL.md
names, and gives back the typed value (unittas.values); errors come as the package's exceptions; reflection by
readable names is translated in a real client (names: srg) and not in a development one; events are read per test
from a mark.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest

from fakeprobe import FakeError, FakeProbe, inThread
from unittas.api import CommandResult, Game
from unittas.errors import NotFound
from unittas.link import Listener
from unittas.mappings import Mappings
from unittas.values import Block, BlockPos, ChatLine, Entity, Inventory, Item, Look, Player, Screen, Sound, Vec3
from unittas.wire import Role
from test_values import PIG, PLAYER

WOOL = {'id': 'minecraft:wool', 'count': 3, 'meta': 14}
INVENTORY = {'selected': 0, 'main': [WOOL] + [None] * 35,
             'armor': {'feet': None, 'legs': None, 'chest': None, 'head': None}, 'cursor': None}
MAPPINGS = Mappings({'inventory': ['field_71071_by'], 'currentItem': ['field_70461_c']}, {'getHealth': ['func_110143_aJ']})


class GameTests(unittest.TestCase):

  def setUp(self) -> None:
    self.folder = tempfile.mkdtemp(prefix='unittas-api-')
    self.addCleanup(shutil.rmtree, self.folder, True)
    self.listener = Listener()
    self.addCleanup(self.listener.close)

  def game(self, handlers: dict, names: str = 'mcp') -> Game:
    expected = self.listener.prepare(self.folder, 'alice', Role.CLIENT)
    fake = FakeProbe(expected.startFile, extra={'names': names})
    thread, box = inThread(fake.connect)
    connection = self.listener.accept(timeout=10)
    thread.join(10)
    self.addCleanup(connection.close)
    self.addCleanup(fake.close)
    self.fake = fake
    self.asked = fake.serve(handlers)
    return Game(connection, mappings=MAPPINGS)

  def sent(self) -> list:
    """The requests the fake was sent: (op, side, args)."""
    return [(request['op'], request.get('side'), request.get('args') or {}) for request in self.asked]

  def test_command(self) -> None:
    game = self.game({'command.run': lambda args, side: {'result': 1, 'lines': ['Given [Red Wool] * 1'], 'errors': []}})
    said = game.command('/give @p wool 1 14')
    self.assertEqual(CommandResult(1, ('Given [Red Wool] * 1',), ()), said)
    self.assertEqual([('command.run', None, {'command': '/give @p wool 1 14'})], self.sent())

  def test_the_player_and_the_inventory(self) -> None:
    game = self.game({
      'player.get': lambda args, side: dict(PLAYER, camera=0) if side == 'client' else PLAYER,
      'inventory.get': lambda args, side: WOOL if args.get('slot') == 'held' else INVENTORY,
      'inventory.set': lambda args, side: {},
      'player.teleport': lambda args, side: {},
      'player.look': lambda args, side: {},
    })
    self.assertIsInstance(game.player(), Player)
    self.assertEqual(0, game.player(side='client').camera)
    self.assertEqual(Item('minecraft:wool', 3, 14), game.held())
    self.assertIsInstance(game.inventory(), Inventory)
    game.setSlot('armor.feet', Item('minecraft:leather_boots', 1, 0))
    game.setSlot('held', Item.EMPTY)
    game.teleport(Vec3(5.5, 4, 5.5), look=Look(90, 0))
    game.teleport((0.5, 70, 0.5), dimension='minecraft:the_end')
    game.look(45, 10)
    self.assertEqual([
      ('player.get', None, {}),
      ('player.get', 'client', {}),
      ('inventory.get', None, {'slot': 'held'}),
      ('inventory.get', None, {}),
      ('inventory.set', None, {'slot': 'armor.feet', 'item': {'id': 'minecraft:leather_boots', 'count': 1, 'meta': 0}}),
      ('inventory.set', None, {'slot': 'held', 'item': None}),
      ('player.teleport', None, {'pos': [5.5, 4.0, 5.5], 'look': {'yaw': 90.0, 'pitch': 0.0}}),
      ('player.teleport', None, {'pos': [0.5, 70.0, 0.5], 'dimension': 'minecraft:the_end'}),
      ('player.look', None, {'yaw': 45.0, 'pitch': 10.0}),
    ], self.sent())

  def test_blocks_and_entities(self) -> None:
    game = self.game({
      'block.get': lambda args, side: {'id': 'minecraft:wool', 'meta': 14},
      'block.set': lambda args, side: {},
      'entity.spawn': lambda args, side: PIG,
      'entity.get': lambda args, side: PIG,
      'entity.list': lambda args, side: [PIG, PIG],
      'entity.remove': lambda args, side: {},
    })
    self.assertEqual(Block('minecraft:wool', 14), game.block((3, 4, 3)))
    game.setBlock(BlockPos(3, 4, 3), 'minecraft:gold_block')
    game.setBlock((3, 5, 3), Block('minecraft:wool', 14))
    pig = game.spawn('Pig', (4.5, 4, 4.5))
    self.assertIsInstance(pig, Entity)
    self.assertEqual(pig, game.entity(pig.entity))
    self.assertEqual((pig, pig), game.entities(type='Pig'))
    game.remove(pig)
    self.assertEqual([
      ('block.get', None, {'pos': [3, 4, 3]}),
      ('block.set', None, {'pos': [3, 4, 3], 'block': {'id': 'minecraft:gold_block', 'meta': 0}}),
      ('block.set', None, {'pos': [3, 5, 3], 'block': {'id': 'minecraft:wool', 'meta': 14}}),
      ('entity.spawn', None, {'type': 'Pig', 'pos': [4.5, 4.0, 4.5]}),
      ('entity.get', None, {'entity': 412}),
      ('entity.list', None, {'near': {'pos': 'player', 'radius': 16}, 'type': 'Pig'}),
      ('entity.remove', None, {'entity': 412}),
    ], self.sent())

  def test_screens_keys_and_ticks(self) -> None:
    game = self.game({
      'screen.get': lambda args, side: None,
      'screen.open': lambda args, side: {},
      'screen.close': lambda args, side: {},
      'key.tap': lambda args, side: {},
      'ticks.wait': lambda args, side: {'waited_ms': 50, 'from': 10, 'tick': 11},
    })
    self.assertIsNone(game.screen())
    game.openScreen('inventory')
    game.closeScreen()
    game.tap('key.jump')
    self.assertEqual(11, game.ticks(1))
    self.assertEqual([('screen.get', None, {}), ('screen.open', None, {'screen': 'inventory'}),
                      ('screen.close', None, {}), ('key.tap', None, {'key': 'key.jump'}),
                      ('ticks.wait', None, {'side': 'client', 'n': 1})], self.sent())

  def test_reflection_in_a_development_client_isn_t_translated(self) -> None:
    game = self.game({'reflect.get': lambda args, side: 0, 'reflect.set': lambda args, side: {}})
    self.assertEqual(0, game.reflect(['inventory', 'currentItem']))
    game.reflectSet(['inventory', 'currentItem'], 3)
    self.assertEqual([('reflect.get', 'server', {'from': 'player', 'path': ['inventory', 'currentItem']}),
                      ('reflect.set', 'server', {'from': 'player', 'path': ['inventory', 'currentItem'], 'value': 3})],
                     self.sent())

  def test_reflection_in_a_real_client_is_translated(self) -> None:
    game = self.game({'reflect.get': lambda args, side: 20.0}, names='srg')
    self.assertEqual(20.0, game.reflect([{'call': 'getHealth'}], side='client'))
    game.reflect(['inventory', 'currentItem'], raw=True)
    self.assertEqual([
      ('reflect.get', 'client', {'from': 'player', 'path': [{'call': ['getHealth', 'func_110143_aJ']}]}),
      ('reflect.get', 'server', {'from': 'player', 'path': ['inventory', 'currentItem']}),
    ], self.sent())

  def test_errors_are_the_package_s(self) -> None:
    def missing(args, side):
      raise FakeError('NotFound', 'no entity 9 in the world', what=9)

    game = self.game({'entity.get': missing})
    with self.assertRaises(NotFound) as caught:
      game.entity(9)
    self.assertEqual(9, caught.exception.fields['what'])

  def test_events_from_a_mark(self) -> None:
    game = self.game({})
    self.fake.event('chat', plain='before', formatted='before', json='{}')
    time.sleep(0.2)
    mark = game.mark()
    self.fake.event('chat', plain='Given', formatted='Given', json='{}')
    self.fake.event('sound', id='minecraft:random.pop', known=True, **{'from': None}, volume=1.0, pitch=1.0,
                    pos=[0.5, 4.0, 0.5])
    deadline = time.monotonic() + 5
    while len(game.sounds(mark)) < 1 and time.monotonic() < deadline:
      time.sleep(0.05)
    self.assertEqual((ChatLine('Given', 'Given', '{}', ''),), game.chat(mark))
    self.assertEqual(('minecraft:random.pop',), tuple(sound.id for sound in game.sounds(mark)))
    self.assertIsInstance(game.sounds(mark)[0], Sound)


if __name__ == '__main__':
  unittest.main()

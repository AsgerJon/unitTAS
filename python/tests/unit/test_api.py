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

import mcdex
from mcdex import (MCBlocks, MCDimensions, MCEntities, MCItems,
                   Version)

from fakeprobe import HELLO, FakeError, FakeProbe, inThread
from unittas.api import CommandResult, Game
from unittas.codec import toJson
from unittas.errors import Missing, NoResult, NotFound, UnknownVersion
from unittas.link import Listener
from unittas.mappings import Mappings
from unittas.values import Block, BlockPos, ChatLine, Entity, Inventory, Item, Look, Player, Screen, Sound, Vec3
from unittas.wire import Role
from worktoy.waitaminute.desc import ReadOnlyError
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

  def game(self, handlers: dict, names: str = 'mcp',
           minecraft: str = '1.7.10', ops: tuple = ()) -> Game:
    expected = self.listener.prepare(self.folder, 'alice', Role.CLIENT)
    extra = {'names': names, 'minecraft': minecraft}
    if ops:
      extra['ops'] = list(ops)
    fake = FakeProbe(expected.startFile, extra=extra)
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

  def test_version_is_mcdexs(self) -> None:
    """The version the hello names, as mcdex's own Version member."""
    for text, member in (('1.7.10', Version.V1_7_10),
                         ('26.3', Version.V26_3),
                         ('1.8', Version.V1_8)):
      with self.subTest(minecraft=text):
        self.assertIs(member, self.game({}, minecraft=text).version)

  def test_a_version_mcdex_lacks_is_refused(self) -> None:
    """A snapshot, a version never released, or none: UnknownVersion."""
    for text in ('26.4-snapshot-7', '1.2', ''):
      with self.subTest(minecraft=text):
        game = self.game({}, minecraft=text)
        with self.assertRaises(UnknownVersion) as raised:
          _ = game.version
        #  a NoResult, so a test naming an mcdex thing there is NO RESULT
        self.assertIsInstance(raised.exception, NoResult)
        self.assertEqual(text, raised.exception.minecraft)
        self.assertIn(repr(text), str(raised.exception))
        self.assertIn('mcdex %s' % mcdex.__version__,
                      str(raised.exception))

  def test_version_is_read_only(self) -> None:
    """The version is the hello's, a worktoy Field no test can write."""
    game = self.game({})
    with self.assertRaises(ReadOnlyError):
      game.version = Version.V26_3
    self.assertIs(Version.V1_7_10, game.version)

  def things(self, minecraft: str) -> Game:
    """A game of that version that takes things and answers plainly."""
    return self.game({'inventory.set': lambda args, side: {},
                      'block.set': lambda args, side: {},
                      'entity.spawn': lambda args, side: dict(PIG),
                      'player.teleport': lambda args, side: {},
                      'entity.list': lambda args, side: []},
                     minecraft=minecraft)

  def args(self, op: str) -> list:
    """The arguments of each request of that op, in order."""
    return [args for name, side, args in self.sent() if name == op]

  def test_things_by_mcdex_member_in_1_7_10(self) -> None:
    """Each member as 1.7.10 has it (SPEC.md 14.4)."""
    game = self.things('1.7.10')
    game.setSlot('chest', MCItems.PinkWool, 3)
    game.setBlock((1, 4, 1), MCBlocks.RedWool)
    game.setBlock((2, 4, 2), MCBlocks.WitherSkeletonSkull)
    game.spawn(MCEntities.WitherSkeleton, (0, 4, 0))
    game.teleport((0, 64, 0), dimension=MCDimensions.TheNether)
    game.entities(type=MCEntities.Zombie)
    self.assertEqual(toJson(Item('minecraft:wool', 3, 6)),
                     self.args('inventory.set')[0]['item'])
    plain, skull = self.args('block.set')
    self.assertEqual(toJson(Block('minecraft:wool', 14)), plain['block'])
    self.assertNotIn('tile', plain)
    self.assertEqual(toJson(Block('minecraft:skull', 1)), skull['block'])
    self.assertEqual('{SkullType:1b}', skull['tile'])
    spawned = self.args('entity.spawn')[0]
    self.assertEqual(('Skeleton', '{SkeletonType:1}'),
                     (spawned['type'], spawned['nbt']))
    self.assertEqual(-1, self.args('player.teleport')[0]['dimension'])
    self.assertEqual('Zombie', self.args('entity.list')[0]['type'])

  def test_things_by_mcdex_member_in_26_3(self) -> None:
    """The same members as 26.3 has them."""
    game = self.things('26.3')
    game.setSlot('chest', MCItems.PinkWool)
    game.setBlock((1, 4, 1), MCBlocks.RedWool)
    game.spawn(MCEntities.WitherSkeleton, (0, 4, 0))
    game.teleport((0, 64, 0), dimension=MCDimensions.TheNether)
    self.assertEqual(toJson(Item('minecraft:pink_wool', 1, 0)),
                     self.args('inventory.set')[0]['item'])
    self.assertEqual(toJson(Block('minecraft:red_wool', 0)),
                     self.args('block.set')[0]['block'])
    spawned = self.args('entity.spawn')[0]
    self.assertEqual('minecraft:wither_skeleton', spawned['type'])
    self.assertNotIn('nbt', spawned)
    self.assertEqual('minecraft:the_nether',
                     self.args('player.teleport')[0]['dimension'])

  def test_a_member_vanilla_lacks_is_missing_and_nothing_is_sent(
      self) -> None:
    """A FAIL with mcdex's reason, before the game is asked."""
    game = self.things('1.7.10')
    with self.assertRaises(Missing) as raised:
      game.setSlot('chest', MCItems.Elytra)
    self.assertIn("Vanilla 1.7.10 has no 'elytra'", str(raised.exception))
    self.assertEqual([], self.args('inventory.set'))

  def test_strings_and_values_go_through_as_before(self) -> None:
    """The version-bound way stays (M1)."""
    game = self.things('1.7.10')
    game.setSlot('held', Item('minecraft:stone', 2, 0))
    game.setBlock((0, 4, 0), 'minecraft:gold_block')
    game.spawn('Pig', (0, 4, 0), nbt='{Saddle:1b}')
    game.teleport((0, 64, 0), dimension='minecraft:the_end')
    self.assertEqual(toJson(Item('minecraft:stone', 2, 0)),
                     self.args('inventory.set')[0]['item'])
    self.assertEqual(('Pig', '{Saddle:1b}'),
                     (self.args('entity.spawn')[0]['type'],
                      self.args('entity.spawn')[0]['nbt']))
    self.assertEqual('minecraft:the_end',
                     self.args('player.teleport')[0]['dimension'])

  def test_mistakes_with_members_are_refused(self) -> None:
    """Loudly, before the game is asked."""
    game = self.things('1.7.10')
    with self.assertRaises(TypeError):
      game.setSlot('held', Item('minecraft:stone', 1, 0), 3)
    with self.assertRaises(TypeError):
      game.setSlot('held', MCBlocks.RedWool)
    with self.assertRaises(TypeError):
      game.spawn(MCEntities.WitherSkeleton, (0, 4, 0), nbt='{Health:1f}')
    self.assertEqual([], self.sent())

  def declaring(self, plugins: list) -> Game:
    """A 1.7.10 game whose mods declare things (hooks.things)."""
    return self.game({'inventory.set': lambda args, side: {},
                      'hooks.things': lambda args, side: {
                        'plugins': plugins}},
                     ops=tuple(HELLO['ops']) + ('hooks.things',))

  def test_a_mod_declares_what_vanilla_lacks(self) -> None:
    """Robert's elytra is MCItems.Elytra on his 1.7.10 (SPEC.md 14.4)."""
    game = self.declaring([{'class': 'robert.Hooks', 'ok': True,
                            'things': {'items/elytra': 'etfuturum:elytra'}}])
    game.setSlot('armor.chest', MCItems.Elytra)
    self.assertEqual(toJson(Item('etfuturum:elytra', 1, 0)),
                     self.args('inventory.set')[0]['item'])
    self.assertEqual({MCItems.Elytra},
                     game.membersOf(Item('etfuturum:elytra', 1, 0)))
    #  asked once, then kept
    self.assertEqual(1, len(self.args('hooks.things')))

  def test_declarations_are_checked_loudly(self) -> None:
    """Nothing a mod declares is guessed at or quietly dropped."""
    cases = {
      'two plugins disagree': [
        {'class': 'a.Hooks', 'ok': True,
         'things': {'items/elytra': 'a:elytra'}},
        {'class': 'b.Hooks', 'ok': True,
         'things': {'items/elytra': 'b:elytra'}}],
      'no such member': [{'class': 'a.Hooks', 'ok': True,
                          'things': {'items/no_such_thing': 'a:x'}}],
      'no such catalogue': [{'class': 'a.Hooks', 'ok': True,
                             'things': {'gizmos/elytra': 'a:x'}}],
      'vanilla has it': [{'class': 'a.Hooks', 'ok': True,
                          'things': {'items/pink_wool': 'a:wool'}}],
      'no mcdex id': [{'class': 'a.Hooks', 'ok': True,
                       'things': {'items/elytra': 'a:b:c'}}],
      'its things() threw': [{'class': 'a.Hooks', 'ok': False,
                              'error': {'type': 'GameError',
                                        'message': 'a.Hooks.things threw'}}],
    }
    for case, plugins in cases.items():
      with self.subTest(case=case):
        game = self.declaring(plugins)
        with self.assertRaises(ValueError) as raised:
          game.declared()
        self.assertIn('a.Hooks', str(raised.exception))

  def test_a_port_without_plugins_declares_nothing(self) -> None:
    """No hooks.things in the hello's ops: nothing declared, nothing asked."""
    game = self.things('1.7.10')
    self.assertEqual({}, game.declared())
    with self.assertRaises(Missing) as raised:
      game.setSlot('armor.chest', MCItems.Elytra)
    self.assertIn('no mod declares it', str(raised.exception))
    self.assertEqual([], self.args('hooks.things'))

  def test_an_entity_s_data_and_its_members(self) -> None:
    """Read with its data when asked; a member told apart by data found."""
    skeletons = [dict(PIG, entity=1, type='Skeleton'),
                 dict(PIG, entity=2, type='Skeleton')]
    data = {1: '{SkeletonType:0b}', 2: '{SkeletonType:1b}'}

    def get(args, side):
      found = dict(skeletons[args['entity'] - 1])
      if args.get('nbt'):
        found['nbt'] = data[args['entity']]
      return found

    game = self.game({'entity.list': lambda args, side: skeletons,
                      'entity.get': get}, minecraft='1.7.10')
    read = game.entity(2, nbt=True)
    self.assertTrue(read.nbtAsked)
    self.assertEqual(1, read.nbt['SkeletonType'])
    self.assertFalse(game.entity(2).nbtAsked)
    #  the summary alone can't tell a wither skeleton: its data is read
    self.assertEqual({MCEntities.WitherSkeleton},
                     game.membersOf(game.entity(2)))
    found = game.entities(type=MCEntities.WitherSkeleton)
    self.assertEqual([2], [each.entity for each in found])
    self.assertEqual('Skeleton', self.args('entity.list')[-1]['type'])

  def test_command(self) -> None:
    game = self.game({'command.run': lambda args, side: {'result': 1, 'lines': ['Given [Red Wool] * 1'], 'errors': []}})
    said = game.command('/give @p wool 1 14')
    self.assertEqual(CommandResult(1, ('Given [Red Wool] * 1',), ()), said)
    self.assertEqual([('command.run', None, {'command': '/give @p wool 1 14'})], self.sent())

  def test_joining_and_leaving_a_server(self) -> None:
    """server.join on 127.0.0.1 at the port given, its wait long enough for the join's own limit; server.leave."""
    game = self.game({'server.join': lambda args, side: {'load_ms': 900},
                      'server.leave': lambda args, side: {'leave_ms': 40}})
    self.assertEqual(900, game.join(41300))
    self.assertEqual(40, game.leave())
    self.assertEqual([('server.join', None, {'address': '127.0.0.1', 'port': 41300, 'settle_ticks': 40, 'max_seconds': 180}),
                      ('server.leave', None, {})], self.sent())
    from unittas.errors import Disconnected
    refused = self.game({'server.join': lambda args, side: (_ for _ in ()).throw(FakeError(
      'Disconnected', "couldn't join 127.0.0.1:41301: Failed to connect to the server: Connection refused",
      reason='Failed to connect to the server: Connection refused'))})
    with self.assertRaises(Disconnected) as raised:
      refused.join(41301, settleTicks=10)
    self.assertIn('Connection refused', str(raised.exception))

  def test_players_by_name_on_a_server(self) -> None:
    """players.list, player.kick, a command as a player or the console, a player named (SPEC.md 11.3, step 4)."""
    alice = dict(PLAYER, name='alice')
    listed = [{'name': 'alice', 'uuid': 'a-uuid', 'entity': 7, 'dimension': 'minecraft:overworld', 'pos': [0.5, 4, 0.5]}]
    game = self.game({'players.list': lambda args, side: listed, 'player.kick': lambda args, side: {},
                      'player.get': lambda args, side: alice,
                      'command.run': lambda args, side: {'result': 1, 'lines': [], 'errors': []}})
    self.assertEqual(('alice',), tuple(each['name'] for each in game.players()))
    game.kick('bob', 'the test is done with bob')
    self.assertEqual('alice', game.player(name='alice').name)
    game.command('/say hi', as_='server')
    game.command('/say hi', as_='bob')
    game.command('/say hi')
    self.assertEqual([('players.list', None, {}), ('player.kick', None, {'player': 'bob', 'reason': 'the test is done with bob'}),
                      ('player.get', None, {'player': 'alice'}),
                      ('command.run', None, {'command': '/say hi', 'as': 'server'}),
                      ('command.run', None, {'command': '/say hi', 'as': {'player': 'bob'}}),
                      ('command.run', None, {'command': '/say hi'})], self.sent())

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

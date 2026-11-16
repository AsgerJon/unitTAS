"""
Step 1 of phase 3 (SPEC.md section 9.3), on the run's port (19.7): the protocol's values against the probe's real
answers. Every value an answer or an event carries reads (unittas.codec.fromJson) and writes back as the JSON it came
as; values written by the codec are taken by the operations; and the answers seen are saved as
<results>/values/answers.json, the unit tests' fixtures (python/tests/unit/fixtures/answers.json for 1.7.10,
answers-26.3.json for 26.3, copied from a run). Things by mcdex member, places from the port's start; an item's name
in its NBT before 1.20.5 and in a component from it. One launch, in a world of its own.

  python -m unittas.selftest test_values      (through the watcher: "probe test_values",
                                               "probe test_values on 26.3-fabric")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import json
import os
import shutil
import unittest

from mcdex import MCBlocks, MCEntities, MCItems, MCSounds, Version

from ports import command, probeGame, start
from probegame import READY_SECONDS
from unittas.api import Game
from unittas.codec import fromJson, toJson
from unittas.reset import reset
from unittas.things import blockOf, entityOf, itemOf, resolve
from unittas.values import Block, ChatLine, Entity, Inventory, Item, LogLine, Player, Screen, Sound, Vec3


class ValuesTests(unittest.TestCase):
  """Its tests in order; each records what it saw under the value's kind."""

  @classmethod
  def setUpClass(cls) -> None:
    cls.launched = probeGame('values')
    shutil.rmtree(os.path.join(cls.launched.gameDir, 'saves', 'unittas'), ignore_errors=True)
    cls.connection = cls.launched.start(READY_SECONDS)
    cls.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    cls.connection.request('world.create', {}, timeout=240)
    cls.connection.request('world.prepare')
    reset(cls.connection, at=start())
    cls.game = Game(cls.connection)
    cls.here = Vec3(*start())
    cls.recorded = {}

  @classmethod
  def tearDownClass(cls) -> None:
    try:
      folder = os.path.join(cls.launched.results, 'values')
      os.makedirs(folder, exist_ok=True)
      with open(os.path.join(folder, 'answers.json'), 'w', encoding='utf-8') as file:
        json.dump(cls.recorded, file, indent=1, sort_keys=True)
    finally:
      cls.launched.stop()

  def request(self, op, args=None, side=None, timeout=60.0):
    return self.connection.request(op, args, side=side, timeout=timeout)

  def seen(self, kind: type, wire):
    """The answer read as its value, checked to write back as it came, and recorded."""
    value = fromJson(kind, wire)
    self.assertEqual(wire, toJson(value), kind.__name__)
    self.recorded.setdefault(kind.__name__, []).append(wire)
    return value

  def event(self, kind: str, mark: int, test=lambda event: True) -> dict:
    """The event's body, without the envelope ('event', 'at')."""
    found = self.connection.events.waitFor(lambda event: event.get('event') == kind and test(event), 10, since=mark)
    return {key: value for key, value in found.items() if key not in ('event', 'at')}

  def named(self) -> Item:
    """Three red wool named 'Red': the name in its NBT before 1.20.5, a component from 1.20.5 on."""
    wool = itemOf(MCItems.RedWool, self.game.version, 3)
    if self.game.version >= Version.V1_20_5:
      return Item(wool.id, wool.count, wool.meta, '', '{"minecraft:custom_name":"Red"}')
    return Item(wool.id, wool.count, wool.meta, '{display:{Name:"Red"}}')

  def test_01_items(self) -> None:
    named = self.named()
    self.request('inventory.set', {'slot': 'held', 'item': toJson(named)})
    held = self.seen(Item, self.request('inventory.get', {'slot': 'held'}))
    self.assertEqual((named.id, named.count, named.meta), (held.id, held.count, held.meta))
    #  the name as the game keeps it, in its own words
    self.assertIn('Red', held.snbt or held.components)
    self.assertIn(MCItems.RedWool, self.game.membersOf(held))
    self.assertIs(Item.EMPTY, self.seen(Item, self.request('inventory.get', {'slot': 'main.20'})))
    boots = itemOf(MCItems.LeatherBoots, self.game.version)
    self.request('inventory.set', {'slot': 'armor.feet', 'item': toJson(boots)})
    inventory = self.seen(Inventory, self.request('inventory.get'))
    self.assertEqual(held, inventory.held)
    self.assertEqual(boots, inventory.feet)
    self.seen(Inventory, self.request('inventory.get', side='client'))

  def test_02_blocks(self) -> None:
    wool = self.here.block().offset(3, 0, 3)
    block, _ = blockOf(MCBlocks.RedWool, self.game.version)
    self.request('block.set', {'pos': toJson(wool), 'block': toJson(block)})
    self.assertEqual(block, self.seen(Block, self.request('block.get', {'pos': toJson(wool)})))
    self.assertIsNone(self.seen(Block, self.request('block.get', {'pos': toJson(wool), 'tile': True})).tile)
    chest = self.here.block().offset(5, 0, 3)
    self.request('block.set', {'pos': toJson(chest), 'block': {'id': 'minecraft:chest'}})
    found = self.seen(Block, self.request('block.get', {'pos': toJson(chest), 'tile': True}))
    self.assertIsNotNone(found.tile, 'a chest has its block entity')
    self.assertEqual({MCBlocks.Chest}, self.game.membersOf(found))

  def test_03_entities(self) -> None:
    pigType, _ = entityOf(MCEntities.Pig, self.game.version)
    pig = self.seen(Entity, self.request('entity.spawn', {'type': pigType,
                                                          'pos': toJson(self.here.offset(4.0, 0, 4.0))}))
    self.assertIn(MCEntities.Pig, self.game.membersOf(pig))
    self.assertTrue(pig.living)
    self.assertGreater(pig.health, 0.0)
    self.seen(Entity, self.request('entity.get', {'entity': pig.entity}))
    arrowType, _ = entityOf(MCEntities.Arrow, self.game.version)
    arrow = self.seen(Entity, self.request('entity.spawn', {'type': arrowType,
                                                            'pos': toJson(self.here.offset(6.0, 2.0, 6.0))}))
    self.assertFalse(arrow.living, 'an arrow is not living')
    self.assertEqual(0.0, arrow.health)
    for each in self.request('entity.list', {'near': {'pos': 'player', 'radius': 16}}):
      self.seen(Entity, each)

  def test_04_players(self) -> None:
    server = self.seen(Player, self.request('player.get'))
    client = self.seen(Player, self.request('player.get', side='client'))
    self.assertEqual(server.entity, client.entity)
    self.assertEqual(-1, server.camera, 'the server side has no camera')
    self.assertEqual(0, client.camera)
    self.request('command.run', {'command': command('speed for 30 s, level 2')})
    self.assertTrue(self.seen(Player, self.request('player.get')).effects)

  def test_05_events(self) -> None:
    mark = self.connection.events.mark()
    self.request('command.run', {'command': '/say the values'})
    self.seen(ChatLine, self.event('chat', mark, lambda event: 'the values' in event.get('plain', '')))
    button = resolve(MCSounds.UiButtonClick, self.game.version).name
    self.request('sound.play', {'id': button})
    heard = self.seen(Sound, self.event('sound', mark, lambda event: event.get('id') == button))
    self.assertTrue(heard.known)
    self.request('sound.play', {'id': 'minecraft:wobble.nothing'})
    unknown = self.seen(Sound, self.event('sound', mark, lambda event: not event.get('known')))
    self.assertTrue(unknown.callers, 'a sound the game lacks names who asked for it')
    self.request('events.set', {'log': 'info'})
    self.request('log.write', {'message': 'a line for the values'})
    self.seen(LogLine, self.event('log', mark, lambda event: event.get('message') == 'a line for the values'))
    self.request('events.set', {'log': 'warn'})

  def test_06_screens(self) -> None:
    self.assertIsNone(fromJson(Screen, self.request('screen.get')))
    self.request('screen.open', {'screen': 'inventory'})
    self.seen(Screen, self.request('screen.get'))
    self.request('screen.close')


if __name__ == '__main__':
  unittest.main()

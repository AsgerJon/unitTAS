"""
Step 1 of phase 3 (SPEC.md section 9.3): the protocol's values against the probe's real answers. Every value an
answer or an event carries reads (unittas.codec.fromJson) and writes back as the JSON it came as; values written by
the codec are taken by the operations; and the answers seen are saved as <results>/values/answers.json, the unit
tests' fixtures (python/tests/unit/fixtures/answers.json, copied from a run). One launch, in a world of its own.

  python -m unittas.selftest test_values.      (through the watcher: "probe test_values.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import json
import os
import shutil
import unittest

from probegame import READY_SECONDS, ROOT, results
from unittas.codec import fromJson, toJson
from unittas.dev import DevGame
from unittas.reset import reset
from unittas.values import Block, BlockPos, ChatLine, Entity, Inventory, Item, LogLine, Player, Screen, Sound, Vec3

NAMED_WOOL = Item('minecraft:wool', 3, 14, '{display:{Name:"Red"}}')


class ValuesTests(unittest.TestCase):
  """Its tests in order; each records what it saw under the value's kind."""

  @classmethod
  def setUpClass(cls) -> None:
    cls.game = DevGame(ROOT, results(), 'values')
    shutil.rmtree(os.path.join(cls.game.gameDir, 'saves', 'unittas'), ignore_errors=True)
    cls.connection = cls.game.start()
    cls.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    cls.connection.request('world.create', {}, timeout=240)
    reset(cls.connection)
    cls.recorded = {}

  @classmethod
  def tearDownClass(cls) -> None:
    try:
      folder = os.path.join(cls.game.results, 'values')
      os.makedirs(folder, exist_ok=True)
      with open(os.path.join(folder, 'answers.json'), 'w', encoding='utf-8') as file:
        json.dump(cls.recorded, file, indent=1, sort_keys=True)
    finally:
      cls.game.stop()

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

  def test_01_items(self) -> None:
    self.request('inventory.set', {'slot': 'held', 'item': toJson(NAMED_WOOL)})
    held = self.seen(Item, self.request('inventory.get', {'slot': 'held'}))
    self.assertEqual(NAMED_WOOL, held)
    self.assertEqual('Red', held.nbt['display']['Name'])
    self.assertIs(Item.EMPTY, self.seen(Item, self.request('inventory.get', {'slot': 'main.20'})))
    self.request('inventory.set', {'slot': 'armor.feet', 'item': toJson(Item('minecraft:leather_boots', 1, 0))})
    inventory = self.seen(Inventory, self.request('inventory.get'))
    self.assertEqual(NAMED_WOOL, inventory.held)
    self.assertEqual(Item('minecraft:leather_boots', 1, 0), inventory.feet)
    self.seen(Inventory, self.request('inventory.get', side='client'))

  def test_02_blocks(self) -> None:
    wool = BlockPos(3, 4, 3)
    self.request('block.set', {'pos': toJson(wool), 'block': toJson(Block('minecraft:wool', 14))})
    self.assertEqual(Block('minecraft:wool', 14), self.seen(Block, self.request('block.get', {'pos': toJson(wool)})))
    self.assertIsNone(self.seen(Block, self.request('block.get', {'pos': toJson(wool), 'tile': True})).tile)
    chest = BlockPos(5, 4, 3)
    self.request('block.set', {'pos': toJson(chest), 'block': {'id': 'minecraft:chest'}})
    found = self.seen(Block, self.request('block.get', {'pos': toJson(chest), 'tile': True}))
    self.assertEqual('Chest', found.tile['id'])

  def test_03_entities(self) -> None:
    pig = self.seen(Entity, self.request('entity.spawn', {'type': 'Pig', 'pos': toJson(Vec3(4.5, 4.0, 4.5))}))
    self.assertEqual('Pig', pig.type)
    self.assertTrue(pig.living)
    self.assertGreater(pig.health, 0.0)
    self.seen(Entity, self.request('entity.get', {'entity': pig.entity}))
    arrow = self.seen(Entity, self.request('entity.spawn', {'type': 'Arrow', 'pos': [6.5, 6.0, 6.5]}))
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
    self.request('command.run', {'command': '/effect @p 1 30 1'})
    self.assertTrue(self.seen(Player, self.request('player.get')).effects)

  def test_05_events(self) -> None:
    mark = self.connection.events.mark()
    self.request('command.run', {'command': '/say the values'})
    self.seen(ChatLine, self.event('chat', mark, lambda event: 'the values' in event.get('plain', '')))
    self.request('sound.play', {'id': 'minecraft:gui.button.press'})
    self.seen(Sound, self.event('sound', mark, lambda event: event.get('known')))
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

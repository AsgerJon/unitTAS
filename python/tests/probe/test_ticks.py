"""
Step 3 of phase 2 (SPEC.md section 8.3): ticks and waiting, on the client side (the server side needs a world, which
step 4 makes; its waits are tested there). ticks.wait and its stall rule, batch, cancel, wait.until and its tests, and
debug.lag for a slow game. One launch, its tests in order.

  python -m unittas.selftest ticks      (through the watcher: "probe ticks")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import time
import unittest

from probegame import READY_SECONDS, ROOT, results
from unittas.dev import DevGame
from unittas.errors import BadRequest, Cancelled, NotReady, Stalled


class TicksTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.game = DevGame(ROOT, results(), 'ticks')
    cls.connection = cls.game.start()

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop()

  def request(self, op, args=None, side=None, timeout=60.0):
    return self.connection.request(op, args, side=side, timeout=timeout)

  def clientTicks(self) -> int:
    return self.request('status')['ticks']['client']

  def test_00_not_ready_while_the_game_loads(self) -> None:
    with self.assertRaises(NotReady) as caught:
      self.request('ticks.wait', {'side': 'client', 'n': 1})
    self.assertEqual('loading', caught.exception.fields['state'])

  def test_01_ready(self) -> None:
    self.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)

  def test_02_counts_are_exact(self) -> None:
    before = self.clientTicks()
    pending = self.connection.send('ticks.wait', {'side': 'client', 'n': 20})
    value = pending.result(30)
    self.assertGreaterEqual(value['from'], before, 'it counts from when it began')
    self.assertEqual(20, value['tick'] - value['from'])
    self.assertGreaterEqual(pending.at.client, value['tick'], 'answered once the tick was there')
    self.assertGreater(value['waited_ms'], 700)
    self.assertLess(value['waited_ms'], 5000)

  def test_03_until_a_tick(self) -> None:
    target = self.clientTicks() + 10
    pending = self.connection.send('ticks.wait', {'side': 'client', 'until': {'client': target}})
    self.assertEqual(target, pending.result(30)['tick'])
    self.assertGreaterEqual(pending.at.client, target)

  def test_04_none_at_all(self) -> None:
    started = time.monotonic()
    self.assertLess(self.request('ticks.wait', {'side': 'client', 'n': 0})['waited_ms'], 200)
    self.assertLess(time.monotonic() - started, 1.0)

  def test_05_wrong_arguments(self) -> None:
    for args, field in (({'side': 'client', 'n': -1}, 'n'), ({'side': 'sideways', 'n': 1}, 'side'),
                        ({'side': 'client', 'n': 'many'}, 'n'), ({'side': 'client', 'n': 1, 'stall_seconds': 0}, 'stall_seconds')):
      with self.subTest(args=args):
        with self.assertRaises(BadRequest) as caught:
          self.request('ticks.wait', args)
        self.assertEqual(field, caught.exception.fields.get('field'))
    with self.assertRaises(BadRequest):
      self.request('ticks.wait', {'n': 1}, side='client')

  def test_06_no_server_without_a_world(self) -> None:
    with self.assertRaises(NotReady):
      self.request('ticks.wait', {'side': 'server', 'n': 1})

  def test_07_screen_get(self) -> None:
    screen = self.request('screen.get', side='client')
    self.assertTrue(screen['class'].endswith('GuiMainMenu'), screen)
    self.assertEqual((False, False, False), (screen['chat'], screen['container'], screen['pauses']))
    self.assertEqual(screen, self.request('screen.get'), 'the client is screen.get\'s own side')
    with self.assertRaises(BadRequest) as caught:
      self.request('screen.get', side='server')
    self.assertEqual('side', caught.exception.fields.get('field'))

  def test_08_a_batch_runs_in_one_tick(self) -> None:
    entries = self.request('batch', {'ops': [{'op': 'screen.get'}] * 3}, side='client')
    self.assertEqual(3, len(entries))
    self.assertTrue(all(entry['ok'] for entry in entries), entries)
    self.assertEqual(1, len({entry['at']['client'] for entry in entries}), entries)

  def test_09_a_batch_takes_instant_operations_only(self) -> None:
    for ops in ([{'op': 'screen.get'}, {'op': 'ticks.wait', 'args': {'side': 'client', 'n': 1}}],
                [{'op': 'wobble.about'}],
                [{'op': 'batch', 'args': {'ops': []}}],
                [{'args': {}}]):
      with self.subTest(ops=ops):
        with self.assertRaises(BadRequest) as caught:
          self.request('batch', {'ops': ops}, side='client')
        self.assertEqual('ops', caught.exception.fields.get('field'))
    with self.assertRaises(BadRequest) as caught:
      self.request('batch', {'ops': [{'op': 'screen.get'}]})
    self.assertEqual('side', caught.exception.fields.get('field'))

  def test_10_a_batch_stops_at_an_error(self) -> None:
    ops = [{'op': 'debug.lag', 'args': {'ms': -5, 'ticks': 1}}, {'op': 'screen.get'}]
    stopped = self.request('batch', {'ops': ops}, side='client')
    self.assertEqual('BadRequest', stopped[0]['error']['type'])
    self.assertEqual('Cancelled', stopped[1]['error']['type'])
    goneOn = self.request('batch', {'ops': ops, 'stop_on_error': False}, side='client')
    self.assertEqual('BadRequest', goneOn[0]['error']['type'])
    self.assertTrue(goneOn[1]['ok'], goneOn)

  def test_11_cancel_a_wait(self) -> None:
    waiting = self.connection.send('ticks.wait', {'side': 'client', 'n': 100000})
    time.sleep(0.3)
    self.assertTrue(self.connection.cancel(waiting))
    with self.assertRaises(Cancelled):
      waiting.result(10)

  def test_12_cancel_what_isnt_there(self) -> None:
    pending = self.connection.send('status')
    pending.result(10)
    self.assertFalse(self.connection.cancel(pending), 'answered already: nothing to cancel')
    self.assertFalse(self.request('cancel', {'id': 987654321})['cancelled'])

  def until(self, test, maxTicks=5, op='screen.get') -> dict:
    return self.request('wait.until', {'side': 'client', 'op': op, 'args': {}, 'test': test, 'max_ticks': maxTicks})

  def test_13_wait_until_holds_at_once(self) -> None:
    found = self.until({'path': ['class'], 'contains': 'GuiMainMenu'})
    self.assertTrue(found['held'])
    self.assertEqual(1, found['checks'])
    self.assertTrue(found['value']['class'].endswith('GuiMainMenu'))
    self.assertIsInstance(found['tick'], int)

  def test_14_wait_until_never_holds(self) -> None:
    started = time.monotonic()
    found = self.until({'path': ['pauses'], 'eq': True}, maxTicks=10)
    self.assertFalse(found['held'])
    self.assertEqual(10, found['checks'], 'one check a tick, for max_ticks ticks')
    self.assertFalse(found['value']['pauses'])
    self.assertGreater(time.monotonic() - started, 0.3)

  def test_15_the_tests(self) -> None:
    menu = 'net.minecraft.client.gui.GuiMainMenu'
    cases = [
      ({'path': ['class'], 'eq': menu}, True),
      ({'path': ['class'], 'ne': menu}, False),
      ({'path': ['class'], 'in': ['a', menu]}, True),
      ({'path': ['class'], 'contains': 'Main'}, True),
      ({'path': ['class'], 'len': {'gt': 10}}, True),
      ({'path': ['class'], 'len': {'lt': 10}}, False),
      ({'path': ['nothing'], 'exists': False}, True),
      ({'path': ['class'], 'exists': True}, True),
      ({'path': ['pauses'], 'eq': False}, True),
      ({'all': [{'path': ['chat'], 'eq': False}, {'path': ['container'], 'eq': False}]}, True),
      ({'any': [{'path': ['chat'], 'eq': True}, {'path': ['pauses'], 'eq': True}]}, False),
      ({'not': {'path': ['chat'], 'eq': True}}, True),
    ]
    for test, held in cases:
      with self.subTest(test=test):
        self.assertIs(held, self.until(test, maxTicks=1)['held'])

  def test_16_wait_until_takes_instant_reads_only(self) -> None:
    for op in ('ticks.wait', 'debug.lag', 'wobble.about'):
      with self.subTest(op=op):
        with self.assertRaises(BadRequest) as caught:
          self.until({'path': [], 'exists': True}, op=op)
        self.assertEqual('op', caught.exception.fields.get('field'))
    with self.assertRaises(BadRequest) as caught:
      self.until({'path': ['class'], 'wobbles': 1})
    self.assertEqual('test', caught.exception.fields.get('field'))

  def test_17_cancel_a_wait_until(self) -> None:
    waiting = self.connection.send('wait.until', {'side': 'client', 'op': 'screen.get', 'args': {},
                                                  'test': {'path': ['pauses'], 'eq': True}, 'max_ticks': 100000})
    time.sleep(0.3)
    self.assertTrue(self.connection.cancel(waiting))
    with self.assertRaises(Cancelled):
      waiting.result(10)

  def test_18_slow_but_ticking_is_waited_for(self) -> None:
    #  a tick every 0.8 s: 22 ticks take about 18 s, longer than the stall rule's 15, and that's fine: it ticks
    self.request('debug.lag', {'ms': 800, 'ticks': 25}, side='client')
    waited = self.request('ticks.wait', {'side': 'client', 'n': 22}, timeout=90)['waited_ms']
    self.assertGreater(waited, 15000)
    self.request('ticks.wait', {'side': 'client', 'n': 5}, timeout=30)

  def test_19_a_stall_of_its_own_length(self) -> None:
    self.request('debug.lag', {'ms': 5000, 'ticks': 1}, side='client')
    with self.assertRaises(Stalled) as caught:
      self.request('ticks.wait', {'side': 'client', 'n': 2, 'stall_seconds': 2}, timeout=30)
    self.assertEqual('client', caught.exception.fields['side'])
    self.assertGreaterEqual(caught.exception.fields['since_tick_ms'], 2000)
    self.request('ticks.wait', {'side': 'client', 'n': 2}, timeout=30)

  def test_20_the_stall_rule(self) -> None:
    self.request('debug.lag', {'ms': 17000, 'ticks': 1}, side='client')
    started = time.monotonic()
    with self.assertRaises(Stalled) as caught:
      self.request('ticks.wait', {'side': 'client', 'n': 2}, timeout=60)
    self.assertGreaterEqual(caught.exception.fields['since_tick_ms'], 15000)
    self.assertLess(time.monotonic() - started, 17.0, 'it gave up at 15 s without a tick, not later')
    self.assertEqual('menu', self.request('status')['state'], 'status answers through a stall')
    self.request('ticks.wait', {'side': 'client', 'n': 2}, timeout=30)

  def test_21_quit(self) -> None:
    self.assertEqual({}, self.request('quit', {'reason': 'test_21'}))
    self.assertTrue(self.game.ended(120))


if __name__ == '__main__':
  unittest.main()

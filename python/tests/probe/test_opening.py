"""
The opening guard (SPEC.md, after step 9; Asger: "EVERY TIME the game instance open, I want some screenshots or
something to be used to confirm that the game is not just hanging"), in the development client. 1.7.10's login race is
made to happen on purpose (debug.drop_login: the server drops its next local connections as the race does):
- one dropped login: the opening is pictured, left and opened again, and answers with a warning saying so;
- two: Disconnected, with the reason and the pictures;
- the Java runner's test world too: java.run with one drop armed still reaches its tests;
- and the Java runner's save mode: java.run on a save with one drop armed runs its tests in it.
Each opening is bounded (max_seconds 60) so that without the guard it fails rather than waits.

  python -m unittas.selftest test_opening.      (through the watcher: "probe test_opening.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import unittest

from probegame import READY_SECONDS, ROOT, results
from unittas.dev import DevGame
from unittas.errors import Disconnected
from unittas.gamefiles import copyExactly, removeTree

FOLDER = 'opening-a'
#  a save of the self-check set (test_oldsaves makes it), for the Java runner's save mode
SAVE = 'selfcheck-gold'
DROPPED = "dropped the client's own connection before it joined"


class OpeningTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.game = DevGame(ROOT, results(), 'opening')
    world = os.path.join(cls.game.gameDir, 'saves', FOLDER)
    if os.path.lexists(world):
      removeTree(world)
    cls.connection = cls.game.start()
    cls.connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    cls.pictures = os.path.join(cls.game.results, 'pictures')
    os.makedirs(cls.pictures, exist_ok=True)

  @classmethod
  def tearDownClass(cls) -> None:
    cls.game.stop()
    world = os.path.join(cls.game.gameDir, 'saves', FOLDER)
    if os.path.lexists(world):
      removeTree(world)

  def tearDown(self) -> None:
    # nothing armed left for the next, and no world (or a stuck server) left open
    self.connection.request('debug.drop_login', {'logins': 0}, timeout=10)
    status = self.connection.request('status', timeout=10)
    if status['state'] == 'world' or 'server' in status['sides']:
      self.connection.request('world.close', timeout=240)

  def dropped(self, mark: int) -> list:
    return [event for event in self.connection.events.since(mark) if event.get('event') == 'world'
            and event.get('state') == 'dropped']

  def test_1_a_dropped_login_is_opened_again(self) -> None:
    self.connection.request('debug.drop_login', {'logins': 1}, timeout=10)
    mark = self.connection.events.mark()
    pending = self.connection.send('world.create', {'folder': FOLDER, 'pictures': self.pictures, 'max_seconds': 60})
    value = pending.result(120)
    self.assertEqual(FOLDER, value['folder'])
    self.assertTrue(any(DROPPED in warning and 'left and opened again' in warning for warning in pending.warnings),
                    pending.warnings)
    events = self.dropped(mark)
    self.assertEqual(1, len(events), events)
    self.assertTrue(os.path.isfile(events[0]['picture']), 'the dropped opening\'s picture: %s' % events[0])
    self.assertEqual('world', self.connection.request('status', timeout=10)['state'])

  def test_2_dropped_twice_is_disconnected(self) -> None:
    self.connection.request('debug.drop_login', {'logins': 2}, timeout=10)
    mark = self.connection.events.mark()
    with self.assertRaises(Disconnected) as raised:
      self.connection.request('world.open', {'folder': FOLDER, 'pictures': self.pictures, 'max_seconds': 60},
                              timeout=180)
    self.assertIn(DROPPED, raised.exception.message)
    self.assertIn('and again after it was opened once more', raised.exception.message)
    self.assertEqual(2, len(self.dropped(mark)))

  def test_3_the_java_runners_test_world_too(self) -> None:
    folder = os.path.join(self.game.results, 'java')
    self.connection.request('debug.drop_login', {'logins': 1}, timeout=10)
    value = self.connection.request('java.run', {'suites': ['self'], 'filter': 'MixinTests', 'results': folder,
                                                 'watched': False}, timeout=600)
    self.assertTrue(value['ok'], value)
    self.assertEqual(3, value['counts']['ran'], value['counts'])
    with open(os.path.join(folder, 'progress.txt'), encoding='utf-8') as file:
      progress = file.read()
    self.assertIn(DROPPED, progress)
    self.assertIn('left and opened again', progress)

  def test_4_the_java_runners_saves_too(self) -> None:
    # found by the full run of 21:06: the race hit the Java runner's save mode (TasRunner.openAndSettle), the one
    # opening the guard didn't watch yet: "selfcheck-far didn't load in 180 s", its picture the title screen
    pristine = os.path.join(ROOT, 'run', 'oldsaves', 'selfcheck')
    if not os.path.isfile(os.path.join(pristine, SAVE, 'level.dat')):
      self.skipTest('no self-check saves yet (test_oldsaves makes them)')
    there = os.path.join(self.game.gameDir, 'saves', SAVE)
    if os.path.lexists(there):
      removeTree(there)
    copyExactly(os.path.join(pristine, SAVE), there)
    self.addCleanup(lambda: removeTree(there) if os.path.lexists(there) else None)
    folder = os.path.join(self.game.results, 'java-saves')
    self.connection.request('debug.drop_login', {'logins': 1}, timeout=10)
    value = self.connection.request('java.run', {'suites': ['oldsaves'], 'saves': [SAVE], 'oldsaves': pristine,
                                                 'results': folder, 'watched': False}, timeout=600)
    self.assertTrue(value['ok'], value)
    self.assertEqual(6, value['counts']['ran'], value['counts'])
    with open(os.path.join(folder, 'progress.txt'), encoding='utf-8') as file:
      progress = file.read()
    self.assertIn('%s: the integrated server %s' % (SAVE, DROPPED), progress)


if __name__ == '__main__':
  unittest.main()

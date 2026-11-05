"""
Step 3 of phase 3 (SPEC.md 9.3), its one live test: the real client from an empty download cache, everything fetched
from Mojang's and Forge's own servers over HTTPS and held to its sha1 (about 150 MB: assets 112, vanilla libraries
30, the client 5, Forge and its libraries), the project's Gradle cache not used. Then the game starts from it and
its probe answers.

It runs only when run/allow-download-test exists (Asger's say, SPEC.md 9.6 decision 6), so an ordinary run of every
probe test never downloads. Then:

  python -m unittas.selftest test_download.      (through the watcher: "probe test_download.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import time
import unittest

from probegame import GONE_SECONDS, MIXINS, READY_SECONDS, ROOT, results
from unittas.cache import Cache
from unittas.launcher import Sources, command, findJava
from unittas.release import ReleaseGame

ALLOWED = os.path.join(ROOT, 'run', 'allow-download-test')


@unittest.skipUnless(os.path.isfile(ALLOWED), 'the live download runs only when %s exists' % ALLOWED)
class DownloadTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    cls.folder = os.path.join(results(), 'download')
    cls.cacheRoot = os.path.join(cls.folder, 'cache')
    shutil.rmtree(cls.cacheRoot, ignore_errors=True)
    os.makedirs(cls.cacheRoot)

  def test_1_everything_fetched_into_an_empty_cache(self) -> None:
    asked = []

    def fetch(url: str) -> bytes:
      asked.append(url)
      return Cache(self.cacheRoot).fetch(url)

    started = time.monotonic()
    launch = command(os.path.join(self.folder, 'game'), findJava(), Sources(gradleHome=None,
                                                                           cache=Cache(self.cacheRoot, fetch=fetch)))
    seconds = time.monotonic() - started
    classPath = launch.java[launch.java.index('-cp') + 1].split(os.pathsep)
    self.assertTrue(all(path.startswith(self.cacheRoot) for path in classPath), classPath)
    self.assertTrue(launch.assets.startswith(self.cacheRoot))
    self.assertTrue(all(url.startswith('https://') for url in asked))
    size = sum(os.path.getsize(os.path.join(where, name)) for where, _, names in os.walk(self.cacheRoot)
               for name in names)
    with open(os.path.join(self.folder, 'fetched.txt'), 'w', encoding='utf-8') as note:
      note.write('%d requests, %.1f MB, %.0f s\n' % (len(asked), size / 1e6, seconds))
      note.write('\n'.join(asked) + '\n')
    self.assertGreater(size, 100e6, 'about 150 MB is fetched')

  def test_2_the_game_starts_from_it(self) -> None:
    game = ReleaseGame(ROOT, self.folder, 'game', cache=self.cacheRoot, gradleCache=False)
    shutil.rmtree(os.path.join(game.gameDir, 'saves', 'unittas'), ignore_errors=True)
    connection = game.start()
    try:
      ready = connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
      self.assertEqual('srg', connection.hello.names)
      self.assertEqual(sorted(MIXINS), sorted(ready['mixins']['applied']))
      self.assertEqual('unittas', connection.request('world.create', {}, timeout=240)['folder'])
      self.assertEqual({}, connection.request('quit', {'reason': 'the download test is done'}))
      self.assertTrue(game.ended(GONE_SECONDS))
    finally:
      game.stop()


if __name__ == '__main__':
  unittest.main()

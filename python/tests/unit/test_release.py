"""
The real client's preparation, without a game: the release jar a build made, found by its name and checked to be
that build's, and a game folder's mods/ made exactly the jars asked for, what was there kept aside (unittas.release).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import tempfile
import time
import unittest

from unittas.release import ReleaseGame, putMods, releaseJarIn


def touch(path: str, text: str = '', age: float = 0.0) -> str:
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, 'w', encoding='utf-8') as file:
    file.write(text)
  when = time.time() - age
  os.utime(path, (when, when))
  return path


class ReleaseJarTests(unittest.TestCase):
  """The release jar is remapJar's: by its name, and no older than the dev jar it is remapped from."""

  def setUp(self) -> None:
    self.scratch = tempfile.TemporaryDirectory()
    self.libs = os.path.join(self.scratch.name, 'libs')

  def tearDown(self) -> None:
    self.scratch.cleanup()

  def test_this_version_s_jar_by_its_name(self) -> None:
    touch(os.path.join(self.libs, 'unittas-1.0-dev.jar'), age=60)
    release = touch(os.path.join(self.libs, 'unittas-1.0.jar'), age=50)
    #  newer, but another version's or not a release jar: not it
    touch(os.path.join(self.libs, 'unittas-0.9.jar'))
    touch(os.path.join(self.libs, 'unittas-1.0-sources.jar'))
    self.assertEqual(release, releaseJarIn(self.libs, '1.0'))

  def test_none_says_which(self) -> None:
    touch(os.path.join(self.libs, 'unittas-1.0-dev.jar'))
    with self.assertRaises(FileNotFoundError) as missing:
      releaseJarIn(self.libs, '1.0')
    self.assertIn('unittas-1.0.jar', str(missing.exception))

  def test_one_older_than_its_dev_jar_is_stale(self) -> None:
    #  ./gradlew assemble remade only the dev jar: the release jar beside it is an earlier build's
    touch(os.path.join(self.libs, 'unittas-1.0.jar'), age=600)
    touch(os.path.join(self.libs, 'unittas-1.0-dev.jar'), age=10)
    with self.assertRaises(RuntimeError) as stale:
      releaseJarIn(self.libs, '1.0')
    self.assertIn('older than', str(stale.exception))


class PutModsTests(unittest.TestCase):

  def setUp(self) -> None:
    self.scratch = tempfile.TemporaryDirectory()
    self.game = os.path.join(self.scratch.name, 'game')
    self.aside = os.path.join(self.scratch.name, 'results', 'mods-before-this-run')
    self.jars = [touch(os.path.join(self.scratch.name, 'build', name), name) for name in ('unittas-1.jar', 'lib.jar')]

  def tearDown(self) -> None:
    self.scratch.cleanup()

  def test_into_an_empty_folder(self) -> None:
    self.assertEqual(['lib.jar', 'unittas-1.jar'], putMods(self.game, self.jars, self.aside))
    with open(os.path.join(self.game, 'mods', 'unittas-1.jar'), encoding='utf-8') as copied:
      self.assertEqual('unittas-1.jar', copied.read())
    self.assertFalse(os.path.exists(self.aside), 'nothing was there to keep aside')

  def test_what_was_there_goes_aside(self) -> None:
    touch(os.path.join(self.game, 'mods', 'unittas-0.jar'), 'the old one')
    touch(os.path.join(self.game, 'mods', 'lib.jar'), 'the old lib')
    self.assertEqual(['lib.jar', 'unittas-1.jar'], putMods(self.game, self.jars, self.aside))
    self.assertEqual(['lib.jar', 'unittas-0.jar'], sorted(os.listdir(self.aside)))
    with open(os.path.join(self.aside, 'lib.jar'), encoding='utf-8') as kept:
      self.assertEqual('the old lib', kept.read())
    with open(os.path.join(self.game, 'mods', 'lib.jar'), encoding='utf-8') as copied:
      self.assertEqual('lib.jar', copied.read())


class ReleaseGameTests(unittest.TestCase):

  def test_its_folder_and_launch(self) -> None:
    game = ReleaseGame('/repo', '/results', 'real')
    self.assertEqual('/repo/run/release', game.gameDir)
    self.assertEqual('/results/real', game.results)
    command = game.command()
    self.assertEqual('/repo/unittas-display.sh', command[0])
    self.assertEqual(['-I', '/repo/bin/launch_client.py', '--game', '/repo/run/release'], command[2:])

  def test_a_folder_and_a_name_of_its_own(self) -> None:
    """For several clients at once (SPEC.md 11.3, step 4): each its own folder and its own player."""
    game = ReleaseGame('/repo', '/results', 'bob', folder='/results/bob-game', username='bob')
    self.assertEqual('/results/bob-game', game.gameDir)
    self.assertEqual(['-I', '/repo/bin/launch_client.py', '--game', '/results/bob-game', '--username', 'bob'],
                     game.command()[2:])
    with self.assertRaises(ValueError):
      ReleaseGame('/repo', '/results', 'x', username='bob smith')


if __name__ == '__main__':
  unittest.main()

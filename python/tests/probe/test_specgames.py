"""
Step 6b of phase 3 (SPEC.md section 9.3): unitTAS's own game started from an instance spec, both kinds, and
gamesuite.py's GameTestCases run on each: its development client as client = "gradle" (its runClient, the start file in
run/client), and its real client as client = "real" (the release jar the spec's build makes, UniMixins beside it, from
the project's Gradle cache). Each report read back: the same lines in both.

  python -m unittas.selftest test_specgames.      (through the watcher: "probe test_specgames.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import re
import unittest

import gamesuite
from probegame import READY_SECONDS, ROOT, modVersion, results
from unittas.api import Game
from unittas.launcher import Sources
from unittas.mappings import Mappings
from unittas.run import Run
from unittas.spec import InstanceSpec
from unittas.specgame import GradleGame, RealGame, gameFor

RESULT = re.compile(r'^(\S+) \.\.\. (.+?) \(\d+\.\d s\)$')
EXPECTED = [('AFreshTests.test_leaves_a_gold_block', 'ok'), ('BFreshTests.test_finds_it_gone_and_leaves_wool', 'ok'),
            ('CSharedTests.test_finds_the_wool', 'ok'), ('DChatTests.test_a_its_own_chat', 'ok'),
            ('DChatTests.test_b_fails_on_purpose', 'FAIL')]


class SpecGameTests(unittest.TestCase):

  def spec(self, name: str, body: str) -> InstanceSpec:
    folder = os.path.join(results(), 'specs')
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + '.toml')
    with open(path, 'w', encoding='utf-8') as file:
      file.write('minecraft = "1.7.10"\nloader = { forge = "10.13.4.1614" }\n' + body)
    return InstanceSpec.read(path)

  def runSuite(self, launched) -> list:
    """gamesuite on a Run of the launched game; the report's result lines, checked to quit the game."""
    connection = launched.start()
    connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    folder = os.path.join(launched.results, 'run')
    run = Run(Game(connection, mappings=Mappings.load(Sources(gradleHome=os.path.join(ROOT, '.gradle-home')))),
              launched.gameDir, folder, stop=launched.stop)
    Run.current = run
    try:
      run.begin()
      loader = unittest.TestLoader()
      suite = unittest.TestSuite(loader.loadTestsFromTestCase(each) for each in (
        gamesuite.AFreshTests, gamesuite.BFreshTests, gamesuite.CSharedTests, gamesuite.DChatTests))
      unittest.TextTestRunner(stream=io.StringIO(), verbosity=2).run(suite)
    finally:
      Run.current = None
      report = run.finish()
    with open(report, encoding='utf-8') as file:
      lines = file.read().split('\n')
    self.assertTrue(os.path.isfile(os.path.join(folder, 'screenshots', 'DChatTests.test_b_fails_on_purpose.png')))
    self.assertEqual('FAILED (failures=1)', [line for line in lines if line][-1])
    return [(found.group(1), found.group(2)) for found in map(RESULT.match, lines) if found]

  def test_1_the_development_client_from_a_spec(self) -> None:
    spec = self.spec('gradle', '''
client = "gradle"
[gradle]
project = "%s"
task = "runClient"
game = "%s"
''' % (ROOT, os.path.join(ROOT, 'run', 'client')))
    # unitTAS's own Gradle cache, as ./unittas.sh gives its Gradle (a mod's project would use its own)
    os.environ['GRADLE_USER_HOME'] = os.path.join(ROOT, '.gradle-home')
    try:
      game = gameFor(spec, results(), 'spec-gradle')
      self.assertIsInstance(game, GradleGame)
      self.assertEqual(EXPECTED, self.runSuite(game))
    finally:
      os.environ.pop('GRADLE_USER_HOME', None)

  def test_2_the_real_client_from_a_spec(self) -> None:
    jar = os.path.join(ROOT, 'build', 'libs', 'unittas-%s.jar' % modVersion())
    spec = self.spec('real', '''
client = "real"
build = "%s -p %s --no-daemon --console=plain remapJar"
mods = ["%s"]
libraries = ["%s"]
probe = "%s"
game = "%s"
''' % (os.path.join(ROOT, 'gradlew'), ROOT, jar, os.path.join(ROOT, 'run', 'oldsaves', 'mods', 'unimixins-1.7.10-0.3.1.jar'),
       jar, os.path.join(ROOT, 'run', 'release')))
    # the project's Gradle cache for the launcher, as the scripts' launches have it: nothing downloaded
    os.environ['UNITTAS_GRADLE_HOME'] = os.environ['GRADLE_USER_HOME'] = os.path.join(ROOT, '.gradle-home')
    try:
      game = gameFor(spec, results(), 'spec-real')
      self.assertIsInstance(game, RealGame)
      self.assertEqual(EXPECTED, self.runSuite(game))
    finally:
      os.environ.pop('UNITTAS_GRADLE_HOME', None)
      os.environ.pop('GRADLE_USER_HOME', None)


if __name__ == '__main__':
  unittest.main()

"""
The instance spec (unittas.spec), without a game: a small TOML file in a mod's repository that says which game a run
needs. Each key read and checked; each mistake named with the file and its key; paths taken from the spec's own folder;
the mod jars' globs matching exactly one file each.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import tempfile
import textwrap
import unittest

from unittas.spec import InstanceSpec, MavenLibrary, SpecError

REAL = """
minecraft = "1.7.10"
loader = { forge = "10.13.4.1614" }
client = "real"
mods = ["build/libs/mod-*.jar"]
"""


class SpecTests(unittest.TestCase):

  def setUp(self) -> None:
    self.scratch = tempfile.TemporaryDirectory()
    self.folder = self.scratch.name

  def tearDown(self) -> None:
    self.scratch.cleanup()

  def write(self, text: str, name: str = 'unittas.toml') -> str:
    path = os.path.join(self.folder, name)
    with open(path, 'w', encoding='utf-8') as file:
      file.write(textwrap.dedent(text))
    return path

  def touch(self, relative: str) -> str:
    path = os.path.join(self.folder, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8'):
      pass
    return path

  def refused(self, text: str, *said: str) -> SpecError:
    path = self.write(text)
    with self.assertRaises(SpecError) as refusal:
      InstanceSpec.read(path)
    message = str(refusal.exception)
    self.assertIn(path, message)
    for part in said:
      self.assertIn(part, message)
    return refusal.exception

  # ---------------------------------------------------------------- what a spec says

  def test_a_real_client_s_spec(self) -> None:
    spec = InstanceSpec.read(self.write(REAL))
    self.assertEqual('1.7.10', spec.minecraft)
    self.assertEqual(('forge', '10.13.4.1614'), (spec.loaderName, spec.loaderVersion))
    self.assertEqual('real', spec.client)
    self.assertEqual(self.folder, spec.folder)
    self.assertEqual((), spec.libraries)
    self.assertIsNone(spec.build)
    self.assertIsNone(spec.java)
    self.assertEqual('bundled', spec.probe)
    self.assertEqual({}, spec.options)
    self.assertIsNone(spec.config)
    self.assertEqual((854, 480, 'nested'), (spec.width, spec.height, spec.display))

  def test_everything_given(self) -> None:
    self.touch('libs/unimixins-1.7.10-0.3.1.jar')
    os.makedirs(os.path.join(self.folder, 'test-config'))
    spec = InstanceSpec.read(self.write('''
      minecraft = "1.7.10"
      loader = { forge = "10.13.4.1614" }
      java = "/usr/lib/jvm/java-8-openjdk"
      client = "real"
      mods = ["build/libs/mod-1.0.jar"]
      build = "./gradlew reobfJar --offline"
      libraries = ["maven:com.github.GTNewHorizons:GTNHLib:0.11.22", "libs/unimixins-1.7.10-0.3.1.jar"]
      repositories = ["https://nexus.gtnewhorizons.com/repository/public/"]
      config = "test-config"
      options = { autoJump = false, renderDistance = 6, lang = "en_US" }
      probe = "probe/unittas-dev.jar"
      game = "run/tests"
      window = { width = 1280, height = 720, display = "headless" }
    '''))
    self.assertEqual('/usr/lib/jvm/java-8-openjdk', spec.java)
    self.assertEqual(('./gradlew', 'reobfJar', '--offline'), spec.build)
    self.assertEqual((MavenLibrary('com.github.GTNewHorizons', 'GTNHLib', '0.11.22', ''),
                      os.path.join(self.folder, 'libs/unimixins-1.7.10-0.3.1.jar')), spec.libraries)
    self.assertEqual(('https://nexus.gtnewhorizons.com/repository/public/',), spec.repositories)
    self.assertEqual(os.path.join(self.folder, 'test-config'), spec.config)
    self.assertEqual({'autoJump': False, 'renderDistance': 6, 'lang': 'en_US'}, spec.options)
    self.assertEqual(os.path.join(self.folder, 'probe/unittas-dev.jar'), spec.probe)
    self.assertEqual(os.path.join(self.folder, 'run/tests'), spec.game)
    self.assertEqual((1280, 720, 'headless'), (spec.width, spec.height, spec.display))

  def test_a_gradle_client_s_spec(self) -> None:
    spec = InstanceSpec.read(self.write('''
      minecraft = "1.7.10"
      loader = { forge = "10.13.4.1614" }
      client = "gradle"
      [gradle]
      task = "runClient"
      game = "run/client"
    '''))
    self.assertEqual('gradle', spec.client)
    self.assertEqual(self.folder, spec.gradleProject)
    self.assertEqual('runClient', spec.gradleTask)
    self.assertEqual(os.path.join(self.folder, 'run/client'), spec.game)
    self.assertEqual((), spec.mods, 'its Gradle build gives the mods')

  # ---------------------------------------------------------------- the mods' jars

  def test_each_mod_matches_one_file(self) -> None:
    jar = self.touch('build/libs/mod-1.0.jar')
    spec = InstanceSpec.read(self.write(REAL))
    self.assertEqual((jar,), spec.modJars())

  def test_a_glob_matching_none_or_two_is_refused(self) -> None:
    spec = InstanceSpec.read(self.write(REAL))
    with self.assertRaises(SpecError) as none:
      spec.modJars()
    self.assertIn('build/libs/mod-*.jar', str(none.exception))
    self.assertIn('no file', str(none.exception))
    self.touch('build/libs/mod-1.0.jar')
    self.touch('build/libs/mod-1.0-sources.jar')
    with self.assertRaises(SpecError) as two:
      spec.modJars()
    self.assertIn('mod-1.0-sources.jar', str(two.exception))
    self.assertIn('2 files', str(two.exception))

  # ---------------------------------------------------------------- mistakes, each named

  def test_needed_keys(self) -> None:
    self.refused('loader = { forge = "10.13.4.1614" }\nclient = "real"\nmods = []\n', '"minecraft"')
    self.refused('minecraft = "1.7.10"\nloader = { forge = "10.13.4.1614" }\nmods = []\n', '"client"', 'real', 'gradle')
    self.refused('minecraft = "1.7.10"\nclient = "real"\nmods = []\n', '"loader"')

  def test_wrong_kinds(self) -> None:
    self.refused(REAL.replace('client = "real"', 'client = "dev"'), '"client"', '"dev"')
    self.refused(REAL.replace('minecraft = "1.7.10"', 'minecraft = 1.7'), '"minecraft"', 'string')
    self.refused(REAL.replace('mods = ["build/libs/mod-*.jar"]', 'mods = "build/libs/mod.jar"'), '"mods"', 'list')
    self.refused(REAL + 'options = { autoJump = [1] }\n', '"options"', 'autoJump')
    self.refused(REAL + 'window = { display = "wide" }\n', '"window"', 'display', 'nested')
    self.refused(REAL + 'window = { width = 0 }\n', '"window"', 'width')

  def test_this_version_and_loader_only(self) -> None:
    self.refused(REAL.replace('"1.7.10"', '"1.20.1"'), '"minecraft"', '1.20.1', '1.7.10')
    self.refused(REAL.replace('{ forge = "10.13.4.1614" }', '{ fabric = "0.16.0" }'), '"loader"', 'fabric')
    self.refused(REAL.replace('"10.13.4.1614"', '"10.13.2.1291"'), '"loader"', '10.13.2.1291', '10.13.4.1614')

  def test_an_unknown_key_says_which(self) -> None:
    self.refused(REAL.replace('mods =', 'mod ='), 'unknown key "mod"', 'did you mean "mods"')
    self.refused(REAL + '[gradle]\ntask = "runClient"\n', '"gradle"', 'client = "gradle"')

  def test_libraries(self) -> None:
    self.refused(REAL + 'libraries = ["maven:only:two"]\n', '"libraries"', 'maven:only:two')
    self.refused(REAL + 'libraries = ["maven:a:b:1"]\n', '"repositories"', 'maven')
    self.refused(REAL + 'libraries = ["maven:a:b:1"]\nrepositories = ["http://example.com/maven/"]\n',
                 '"repositories"', 'https')

  def test_the_build_is_a_command_not_a_shell_line(self) -> None:
    self.refused(REAL + 'build = ""\n', '"build"')
    self.refused(REAL + 'build = "./gradlew build && rm -rf /"\n', '"build"', 'shell')

  def test_toml_that_isn_t(self) -> None:
    self.refused('minecraft = \n', 'TOML')

  def test_a_spec_that_isn_t_there(self) -> None:
    missing = os.path.join(self.folder, 'nowhere.toml')
    with self.assertRaises(SpecError) as refusal:
      InstanceSpec.read(missing)
    self.assertIn(missing, str(refusal.exception))


if __name__ == '__main__':
  unittest.main()

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
REAL_26 = """
minecraft = "26.3"
loader = { fabric = "0.20.1" }
client = "real"
mods = []
"""
REAL_1_21_1 = REAL_26.replace('"26.3"', '"1.21.1"')
REAL_1_20_1 = REAL_26.replace('"26.3"', '"1.20.1"')


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

  def test_its_fields_are_the_declared_ones(self) -> None:
    """A method or property in InstanceSpec's body is no field of it (worktoy-notes.md 7, as test_values says)."""
    spec = InstanceSpec.read(self.write(REAL))
    names = list(spec.asDict())
    self.assertEqual([], [name for name in names if name.startswith('_')], names)
    self.assertNotIn('cell', repr(spec))
    self.assertEqual(hash(InstanceSpec.read(self.write(REAL))), hash(spec))

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

  def test_the_server_table(self) -> None:
    """[server] (SPEC.md 11.6, D3 and the EULA): its eula, its mods left out, its memory; real clients only."""
    self.touch('build/libs/mod-1.0.jar')
    spec = InstanceSpec.read(self.write(REAL))
    self.assertEqual((False, (), '2G'), (spec.serverEula, spec.serverExclude, spec.serverMemory),
                     'without one: no EULA accepted, nothing left out, 2G')
    spec = InstanceSpec.read(self.write(REAL + '''
      [server]
      eula = true
      exclude = ["client-only-*.jar"]
      memory = "1536M"
      '''))
    self.assertEqual((True, ('client-only-*.jar',), '1536M'), (spec.serverEula, spec.serverExclude, spec.serverMemory))
    self.refused(REAL + '[server]\neula = "yes"\n', '"server.eula"', 'true or false')
    self.refused(REAL + '[server]\nmemory = "lots"\n', '"server.memory"')
    self.refused(REAL + '[server]\neulaa = true\n', 'server.eulaa', 'server.eula')
    self.refused('''
      minecraft = "1.7.10"
      loader = { forge = "10.13.4.1614" }
      client = "gradle"
      [gradle]
      game = "run/client"
      [server]
      eula = true
      ''', '"server"', 'client = "real"')

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
    self.refused(REAL.replace('"1.7.10"', '"1.19.4"'), '"minecraft"', '1.19.4', '1.7.10', '26.3',
                 '1.21.1', '1.20.1')
    self.refused(REAL.replace('{ forge = "10.13.4.1614" }', '{ fabric = "0.16.0" }'), '"loader"', 'fabric')
    self.refused(REAL.replace('"10.13.4.1614"', '"10.13.2.1291"'), '"loader"', '10.13.2.1291', '10.13.4.1614')

  def test_26_3_on_fabric(self) -> None:
    """26.3 with Fabric Loader 0.20.1 (SPEC.md 19.7 step 4): a real client's spec, as 1.7.10's."""
    spec = InstanceSpec.read(self.write(REAL_26))
    self.assertEqual('26.3', spec.minecraft)
    self.assertEqual(('fabric', '0.20.1'), (spec.loaderName, spec.loaderVersion))
    self.assertEqual('real', spec.client)
    self.refused(REAL_26.replace('{ fabric = "0.20.1" }', '{ forge = "10.13.4.1614" }'), '"loader"', '26.3',
                 'fabric')
    self.refused(REAL_26.replace('"0.20.1"', '"0.19.2"'), '"loader"', '0.19.2', '0.20.1')

  def test_26_3_with_no_loader(self) -> None:
    """26.3 as Mojang ships it (SPEC.md 19.7 step 5): the loader is the mod's, and with no mod there is none."""
    spec = InstanceSpec.read(self.write(REAL_26.replace('loader = { fabric = "0.20.1" }\n', '')))
    self.assertEqual(('', ''), (spec.loaderName, spec.loaderVersion))
    self.refused(REAL.replace('loader = { forge = "10.13.4.1614" }\n', ''), '"loader"', 'forge')

  def test_26_3_s_clients(self) -> None:
    """26.3's game is a real client for now: no Gradle run of a Fabric mod's yet, no dedicated server's probe."""
    gradle = REAL_26.replace('client = "real"', 'client = "gradle"') + '[gradle]\ngame = "run"\n'
    self.refused(gradle, '"client"', '26.3', 'real')
    self.refused(REAL_26 + '[server]\neula = true\n', '"server"', '26.3')

  def test_1_21_1_and_1_20_1_on_fabric_or_with_no_loader(self) -> None:
    """
    1.21.1 and 1.20.1 as 26.3 (SPEC.md 19.7 steps 6d and 6e): with Fabric
    Loader 0.20.1, or as Mojang ships them; a real client only for now.
    """
    for minecraft, real in (('1.21.1', REAL_1_21_1), ('1.20.1', REAL_1_20_1)):
      with self.subTest(minecraft=minecraft):
        spec = InstanceSpec.read(self.write(real))
        self.assertEqual(minecraft, spec.minecraft)
        self.assertEqual(('fabric', '0.20.1'),
                         (spec.loaderName, spec.loaderVersion))
        self.refused(real.replace('"0.20.1"', '"0.16.5"'), '"loader"',
                     '0.16.5', '0.20.1')
        spec = InstanceSpec.read(self.write(real.replace(
          'loader = { fabric = "0.20.1" }\n', '')))
        self.assertEqual(('', ''), (spec.loaderName, spec.loaderVersion))
        gradle = (real.replace('client = "real"', 'client = "gradle"')
                  + '[gradle]\ngame = "run"\n')
        self.refused(gradle, '"client"', minecraft, 'real')
        self.refused(real + '[server]\neula = true\n', '"server"',
                     minecraft)

  def test_1_21_1_beside_neoforge(self) -> None:
    """
    1.21.1 with NeoForge 21.1.267 (SPEC.md 19.7 step 7), as with Fabric
    Loader: a version takes either of its loaders, each at its one
    version; another loader, or another version of one, said with both.
    """
    neoforge = REAL_1_21_1.replace('{ fabric = "0.20.1" }',
                                   '{ neoforge = "21.1.267" }')
    spec = InstanceSpec.read(self.write(neoforge))
    self.assertEqual(('neoforge', '21.1.267'),
                     (spec.loaderName, spec.loaderVersion))
    self.refused(neoforge.replace('"21.1.267"', '"21.1.200"'), '"loader"',
                 'NeoForge 21.1.200', '21.1.267')
    self.refused(REAL_1_21_1.replace('{ fabric = "0.20.1" }',
                                     '{ forge = "52.0.1" }'),
                 '"loader"', 'fabric = "0.20.1"', 'neoforge = "21.1.267"')
    self.refused(REAL_1_21_1.replace(
      '{ fabric = "0.20.1" }', '{ fabric = "0.20.1", neoforge = "21.1.267" }'),
      '"loader"', 'one')
    self.refused(REAL_1_20_1.replace('{ fabric = "0.20.1" }',
                                     '{ neoforge = "21.1.267" }'),
                 '"loader"', '1.20.1', 'fabric', 'forge')

  def test_26_3_beside_neoforge(self) -> None:
    """26.3 with NeoForge 26.3.0.110 (SPEC.md 19.7 step 7c), or Fabric."""
    neoforge = REAL_26.replace('{ fabric = "0.20.1" }',
                               '{ neoforge = "26.3.0.110" }')
    spec = InstanceSpec.read(self.write(neoforge))
    self.assertEqual(('neoforge', '26.3.0.110'),
                     (spec.loaderName, spec.loaderVersion))
    self.refused(neoforge.replace('"26.3.0.110"', '"21.1.267"'), '"loader"',
                 'NeoForge 21.1.267', '26.3.0.110')

  def test_1_20_1_beside_forge(self) -> None:
    """1.20.1 with Forge 47.4.28 (SPEC.md 19.7 step 8), or Fabric."""
    forge = REAL_1_20_1.replace('{ fabric = "0.20.1" }',
                                '{ forge = "47.4.28" }')
    spec = InstanceSpec.read(self.write(forge))
    self.assertEqual(('forge', '47.4.28'),
                     (spec.loaderName, spec.loaderVersion))
    self.refused(forge.replace('"47.4.28"', '"47.4.29"'), '"loader"',
                 'Forge 47.4.29', '47.4.28')

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

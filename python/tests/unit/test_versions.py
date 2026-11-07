"""
unittas.versions (SPEC.md 12.3, step 2): a Minecraft version's JSON with a loader's profile on top, resolved for this
system into what a launch needs, for any version. On the real files, recorded once in fixtures/versions/:
- 26.3 with Fabric Loader 0.20.1 (the modern form: structured arguments with rules and features, natives as plain
  classifier jars, Java 25);
- 1.7.10 with Forge 10.13.4.1614 (the old form: one argument string, natives in a map to extract, Java 8).
A library both name is kept once, the profile's, ahead of vanilla's; rules are Mojang's (os, arch, features); a
placeholder with no value is refused by name, never passed on. Nothing in the result is None.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import json
import os
import unittest

from unittas.versions import Library, allowed, fill, resolve

VERSIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'versions')
CUSTOM_SIZE = {'has_custom_resolution': True}


def recorded(name: str) -> dict:
  with open(os.path.join(VERSIONS, name), encoding='utf-8') as file:
    return json.load(file)


def names(libraries) -> list:
  return [library.name for library in libraries]


class RulesTests(unittest.TestCase):

  def test_no_rules_allow(self) -> None:
    self.assertTrue(allowed([], 'linux', 'x86_64', {}))

  def test_the_last_rule_that_applies_decides(self) -> None:
    rules = [{'action': 'allow'}, {'action': 'disallow', 'os': {'name': 'osx'}}]
    self.assertTrue(allowed(rules, 'linux', 'x86_64', {}))
    self.assertFalse(allowed(rules, 'osx', 'x86_64', {}))

  def test_by_arch_and_by_feature(self) -> None:
    self.assertFalse(allowed([{'action': 'allow', 'os': {'arch': 'x86'}}], 'linux', 'x86_64', {}),
                     "Mojang's 'x86' is 32-bit")
    demo = [{'action': 'allow', 'features': {'is_demo_user': True}}]
    self.assertFalse(allowed(demo, 'linux', 'x86_64', {}))
    self.assertTrue(allowed(demo, 'linux', 'x86_64', {'is_demo_user': True}))


class ModernTests(unittest.TestCase):
  """26.3 with Fabric Loader 0.20.1."""

  def setUp(self) -> None:
    self.version = resolve(recorded('26.3.json'), recorded('fabric-loader-0.20.1-26.3.json'), features=CUSTOM_SIZE)

  def test_the_profile_names_the_launch(self) -> None:
    self.assertEqual('fabric-loader-0.20.1-26.3', self.version.id)
    self.assertEqual('net.fabricmc.loader.impl.launch.knot.KnotClient', self.version.mainClass)
    self.assertEqual(25, self.version.javaMajor)

  def test_the_loader_s_libraries_first_then_vanilla_s_for_this_system(self) -> None:
    found = names(self.version.libraries)
    self.assertEqual(['org.ow2.asm:asm:9.10.1', 'org.ow2.asm:asm-analysis:9.10.1', 'org.ow2.asm:asm-commons:9.10.1',
                      'org.ow2.asm:asm-tree:9.10.1', 'org.ow2.asm:asm-util:9.10.1',
                      'net.fabricmc:sponge-mixin:0.17.5+mixin.0.8.7', 'net.fabricmc:fabric-loader:0.20.1'], found[:7])
    self.assertIn('org.lwjgl:lwjgl-sdl:3.4.3', found)
    self.assertIn('org.lwjgl:lwjgl-sdl:3.4.3:natives-linux', found, "the modern natives are jars on the class path")
    for other in ('natives-macos', 'natives-macos-arm64', 'natives-windows', 'natives-windows-arm64'):
      self.assertNotIn('org.lwjgl:lwjgl-sdl:3.4.3:' + other, found)
    self.assertEqual(len(found), len(set(found)), 'each once')
    self.assertEqual((), self.version.natives, 'nothing to extract')

  def test_where_each_library_comes_from(self) -> None:
    byName = {library.name: library for library in self.version.libraries}
    loader = byName['net.fabricmc:fabric-loader:0.20.1']
    self.assertEqual('net/fabricmc/fabric-loader/0.20.1/fabric-loader-0.20.1.jar', loader.path)
    self.assertEqual('https://maven.fabricmc.net/net/fabricmc/fabric-loader/0.20.1/fabric-loader-0.20.1.jar',
                     loader.url)
    self.assertEqual((), loader.sha1s, "Fabric's profile gives none for the loader itself: its maven's .sha1 then")
    self.assertEqual(('ada2141c0cc52ee8f5c48cd5fa4ce0e794f22236',), byName['org.ow2.asm:asm:9.10.1'].sha1s)
    self.assertEqual(126151, byName['org.ow2.asm:asm:9.10.1'].size)
    sdl = byName['org.lwjgl:lwjgl-sdl:3.4.3:natives-linux']
    self.assertEqual('https://libraries.minecraft.net/' + sdl.path, sdl.url)
    self.assertGreater(sdl.size, 0)
    for library in self.version.libraries:
      if library is not loader:
        self.assertTrue(library.sha1s, '%s has no checksum' % library.name)

  def test_the_jvm_arguments_for_this_system(self) -> None:
    jvm = list(self.version.jvm)
    self.assertNotIn('-XstartOnFirstThread', jvm, "macOS's")
    self.assertNotIn('-Xss1M', jvm, "32-bit x86's")
    self.assertIn('-Djava.library.path=${natives_directory}/java', jvm)
    self.assertEqual(['-cp', '${classpath}'], jvm[jvm.index('-cp'):jvm.index('-cp') + 2])
    self.assertEqual('-DFabricMcEmu= net.minecraft.client.main.Main ', jvm[-1], "the loader's after vanilla's")
    self.assertEqual(('-Xms2G', '-Xmx4G', '-XX:+UseCompactObjectHeaders', '-XX:+AlwaysPreTouch',
                      '-XX:+UseStringDeduplication', '-XX:+UseZGC'), self.version.defaultJvm)

  def test_the_game_arguments_with_the_features_asked_for(self) -> None:
    game = list(self.version.game)
    self.assertEqual(['--username', '${auth_player_name}'], game[:2])
    self.assertIn('--width', game)
    self.assertNotIn('--demo', game)
    self.assertFalse([word for word in game if word.startswith('--quickPlay')])
    plain = resolve(recorded('26.3.json'), recorded('fabric-loader-0.20.1-26.3.json'))
    self.assertNotIn('--width', plain.game, 'no custom size unless asked for')

  def test_assets_client_and_logging(self) -> None:
    self.assertEqual('34', self.version.assets)
    self.assertEqual('331e5c80937c9cd79647ab34bdc1cbb5ef09f456', self.version.assetIndex['sha1'])
    self.assertIn('sha1', self.version.client)
    self.assertEqual('-Dlog4j.configurationFile=${path}', self.version.logging['argument'])

  def test_vanilla_alone(self) -> None:
    vanilla = resolve(recorded('26.3.json'))
    self.assertEqual('26.3', vanilla.id)
    self.assertEqual('net.minecraft.client.main.Main', vanilla.mainClass)
    self.assertNotIn('net.fabricmc:fabric-loader:0.20.1', names(vanilla.libraries))


class LegacyTests(unittest.TestCase):
  """1.7.10 with Forge 10.13.4.1614."""

  def setUp(self) -> None:
    self.version = resolve(recorded('1.7.10.json'), recorded('forge-1.7.10-10.13.4.1614.json'))

  def test_the_profile_names_the_launch(self) -> None:
    self.assertEqual('1.7.10-Forge10.13.4.1614-1.7.10', self.version.id)
    self.assertEqual('net.minecraft.launchwrapper.Launch', self.version.mainClass)
    self.assertEqual(8, self.version.javaMajor)

  def test_forge_s_libraries_first_and_a_client_s_only(self) -> None:
    found = names(self.version.libraries)
    self.assertEqual('net.minecraftforge:forge:1.7.10-10.13.4.1614-1.7.10', found[0])
    forge = recorded('forge-1.7.10-10.13.4.1614.json')
    for library in forge['libraries']:
      if library.get('clientreq') is False:
        self.assertNotIn(library['name'], found, "a server's only")
    self.assertEqual(len(found), len(set(name.rsplit(':', 1)[0] for name in found)), 'each once')

  def test_natives_to_extract(self) -> None:
    extracted = [(library.name, exclude) for library, exclude in self.version.natives]
    self.assertIn(('org.lwjgl.lwjgl:lwjgl-platform:2.9.1', ('META-INF/',)), extracted)
    platform = [library for library, _ in self.version.natives if library.name == 'org.lwjgl.lwjgl:lwjgl-platform:2.9.1']
    self.assertTrue(platform[0].path.endswith('-natives-linux.jar'))

  def test_the_arguments(self) -> None:
    self.assertEqual(('-Djava.library.path=${natives_directory}', '-cp', '${classpath}'), self.version.jvm)
    self.assertEqual((), self.version.defaultJvm)
    game = list(self.version.game)
    self.assertEqual(['--tweakClass', 'cpw.mods.fml.common.launcher.FMLTweaker'], game[-2:], "Forge's string")
    self.assertEqual('1.7.10', self.version.assets)

  def test_a_library_without_downloads_from_its_maven(self) -> None:
    byName = {library.name: library for library in self.version.libraries}
    akka = byName['com.typesafe.akka:akka-actor_2.11:2.3.3']
    self.assertEqual('http://files.minecraftforge.net/maven/' + akka.path, akka.url, 'as the JSON names it')
    self.assertTrue(akka.sha1s, "Forge's checksums")
    wrapper = byName['net.minecraft:launchwrapper:1.12']
    self.assertEqual('https://libraries.minecraft.net/' + wrapper.path, wrapper.url, "Mojang's, unnamed")
    self.assertEqual((), wrapper.sha1s, 'none given')
    self.assertEqual(-1, wrapper.size)


class FillTests(unittest.TestCase):

  def test_each_placeholder_filled(self) -> None:
    self.assertEqual(['--username', 'alice', '-Dx=/n/java'],
                     fill(['--username', '${auth_player_name}', '-Dx=${natives_directory}/java'],
                          {'auth_player_name': 'alice', 'natives_directory': '/n'}))

  def test_one_with_no_value_is_refused_by_name(self) -> None:
    with self.assertRaises(ValueError) as refused:
      fill(['--xuid', '${auth_xuid}'], {})
    self.assertIn('auth_xuid', str(refused.exception))

  def test_a_library_is_a_value(self) -> None:
    one = Library('a:b:1', 'a/b/1/b-1.jar', 'https://x/a/b/1/b-1.jar', ('0' * 40,), 3)
    self.assertEqual(one, Library('a:b:1', 'a/b/1/b-1.jar', 'https://x/a/b/1/b-1.jar', ('0' * 40,), 3))
    hash(one)


if __name__ == '__main__':
  unittest.main()

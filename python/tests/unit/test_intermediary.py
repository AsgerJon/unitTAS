"""
Fabric's intermediary names for an obfuscated version (SPEC.md 19.7 step
6d), without a game and without the network: Fabric runs such a version
under them, so the agent's table goes from Mojang's names through the
obfuscated ones on to intermediary's:
- the intermediary jar's mappings.tiny read (tiny v1: official to
  intermediary, a member by its owner, descriptor and name, in the
  official names); a line it can't read, or another format, refused;
- Mojang's names composed through it: a class, field or method renamed
  by intermediary where it has a line, an override by the name of the
  class up its obfuscated hierarchy that has one, its obfuscated name
  kept where none has (constructors, the JDK's methods);
- the table written with its kind, intermediary.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest
import zipfile

from test_mojangnames import LOG, MINECRAFT
from unittas.intermediary import Intermediary
from unittas.mojangnames import MojangNames

TINY = '''\
v1\tofficial\tintermediary
CLASS\tfgo\tnet/minecraft/class_310
CLASS\tfgo$a\tnet/minecraft/class_310$class_5859
CLASS\tbvh\tnet/minecraft/class_1297
CLASS\tgkx\tnet/minecraft/class_746
CLASS\tfod\tnet/minecraft/class_437
CLASS\tfva\tnet/minecraft/class_542
CLASS\tnet/minecraft/client/main/Main\tnet/minecraft/client/main/Main
FIELD\tfgo\tLgkx;\ts\tfield_1724
FIELD\tfgo\tLfgo;\tE\tfield_1700
METHOD\tfgo\t()V\tt\tmethod_1574
METHOD\tfgo\t(Lfod;)V\ta\tmethod_1507
METHOD\tbvh\t()D\tdt\tmethod_23317
METHOD\tbvh\t()Z\tbW\tmethod_5715
'''
#  an override: intermediary names it on the class that first declares it
#  (Entity's), the overriding class (LocalPlayer's) by that root's name
OVERRIDE = '''\
net.minecraft.world.entity.Entity -> bvh:
    boolean isShiftKeyDown() -> bW
net.minecraft.client.player.LocalPlayer -> gkx:
    boolean isShiftKeyDown() -> bW
'''
#  the obfuscated jar's classes' supertypes: LocalPlayer's chain to Entity
SUPERTYPES = {'gkx': ('bvh', ()), 'bvh': ('java/lang/Object', ()),
              'fgo': ('java/lang/Object', ())}


def jar(folder: str, text: str) -> str:
  """An intermediary jar holding that mappings.tiny."""
  path = os.path.join(folder, 'intermediary-1.21.1.jar')
  with zipfile.ZipFile(path, 'w') as archive:
    archive.writestr('mappings/mappings.tiny', text)
  return path


class ReadTests(unittest.TestCase):

  def setUp(self) -> None:
    self.names = Intermediary.fromText(TINY)

  def test_classes_fields_and_methods(self) -> None:
    self.assertEqual('net/minecraft/class_310', self.names.classes['fgo'])
    self.assertEqual('field_1724', self.names.fields[('fgo', 's', 'Lgkx;')])
    self.assertEqual('method_1574', self.names.methods[('fgo', 't', '()V')])
    self.assertEqual(7, len(self.names.classes))

  def test_another_format_or_a_line_it_can_t_read_is_refused(self) -> None:
    with self.assertRaises(ValueError) as said:
      Intermediary.fromText('tiny\t2\t0\tofficial\tintermediary\n')
    self.assertIn('tiny v1', str(said.exception))
    with self.assertRaises(ValueError) as said:
      Intermediary.fromText(TINY + 'METHOD\tfgo\t()V\n')
    self.assertIn('line 15', str(said.exception))

  def test_read_from_its_jar(self) -> None:
    folder = tempfile.mkdtemp(prefix='unittas-intermediary-')
    self.addCleanup(shutil.rmtree, folder, True)
    self.assertEqual('net/minecraft/class_310',
                     Intermediary.fromJar(jar(folder, TINY)).classes['fgo'])


class ComposedTests(unittest.TestCase):

  def setUp(self) -> None:
    self.names = MojangNames.fromText(LOG + OVERRIDE).through(
      Intermediary.fromText(TINY), SUPERTYPES)

  def test_mojang_s_names_to_intermediary_s(self) -> None:
    self.assertEqual('intermediary', self.names.kind)
    self.assertEqual('net/minecraft/class_310',
                     self.names.classes[MINECRAFT])
    self.assertEqual('net/minecraft/class_310$class_5859',
                     self.names.classes[MINECRAFT + '$ChatStatus'])
    self.assertEqual('method_1574',
                     self.names.methods[(MINECRAFT, 'tick', '()V')])
    self.assertEqual('method_1507', self.names.methods[(
      MINECRAFT, 'setScreen',
      '(Lnet/minecraft/client/gui/screens/Screen;)V')])
    self.assertEqual('field_1724', self.names.fields[(
      MINECRAFT, 'player', 'Lnet/minecraft/client/player/LocalPlayer;')])
    self.assertEqual('method_23317', self.names.methods[(
      'net/minecraft/world/entity/Entity', 'getX', '()D')])

  def test_a_name_intermediary_keeps_stays_the_obfuscated_one(self) -> None:
    self.assertEqual('<init>', self.names.methods[(
      MINECRAFT, '<init>', '(Lnet/minecraft/client/main/GameConfig;)V')])
    self.assertEqual('toString', self.names.methods[(
      MINECRAFT, 'toString', '()Ljava/lang/String;')])
    self.assertEqual('bd', self.names.methods[(
      MINECRAFT, 'createTitle', '()Ljava/lang/String;')],
      "not in this fixture's tiny: kept as the jar names it")
    self.assertEqual('net/minecraft/client/main/Main',
                     self.names.classes['net/minecraft/client/main/Main'])

  def test_an_override_by_its_root_s_name(self) -> None:
    self.assertEqual('method_5715', self.names.methods[(
      'net/minecraft/world/entity/Entity', 'isShiftKeyDown', '()Z')])
    self.assertEqual('method_5715', self.names.methods[(
      'net/minecraft/client/player/LocalPlayer', 'isShiftKeyDown', '()Z')],
      'up the obfuscated hierarchy to the class intermediary names it on')

  def test_a_descriptor_as_fabric_runs_it(self) -> None:
    self.assertEqual('(Lnet/minecraft/class_437;)V', self.names.running(
      '(Lnet/minecraft/client/gui/screens/Screen;)V'))

  def test_its_table_says_intermediary(self) -> None:
    folder = tempfile.mkdtemp(prefix='unittas-intermediary-table-')
    self.addCleanup(shutil.rmtree, folder, True)
    path = self.names.write(os.path.join(folder, 'names.txt'), '1.21.1')
    with io.open(path, encoding='utf-8') as file:
      lines = file.read().splitlines()
    self.assertEqual('unittas-names\t1\tintermediary\t1.21.1', lines[0])
    self.assertIn('m\t%s\ttick\t()V\tmethod_1574' % MINECRAFT, lines)


if __name__ == '__main__':
  unittest.main()

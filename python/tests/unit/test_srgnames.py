"""
Forge's names for an obfuscated version (SPEC.md 19.7 step 8b), without a
game and without the network: Forge 1.20.1 runs the game with Mojang's
class names and SRG field and method names (its install merges Mojang's
for classes only), so the agent's table goes from Mojang's names through
the obfuscated ones on to SRG's for members, its classes as they are:
- the MCP config's joined.tsrg read (tsrg2: obf to srg, a class on its own
  line, each of its members on a line under it, a method with its
  obfuscated descriptor, a parameter's line under a method's skipped);
  another format, or a line it can't read, refused, naming the line;
- Mojang's names composed through it: a field or a method by SRG's name
  where it has a line, an override by its own class's line (SRG names it
  on every class by its root's name), its obfuscated name kept where none
  has (constructors, the JDK's methods); every class by Mojang's name;
- the table written with its kind, srg.
Before 1.17 (SPEC.md 19.7 step 11e: Forge 32.0.108 for 1.16.1) the MCP
config's joined.tsrg is tsrg v1 (no header; a class "obf srg", a field
"<tab>obf srg", a method "<tab>obf descriptor srg") and Forge runs MCP's
class names too: the table renames classes by it as well as members.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest

from test_intermediary import OVERRIDE
from test_mojangnames import LOG, MINECRAFT
from unittas.mojangnames import MojangNames
from unittas.srgnames import SrgNames

TSRG = '''\
tsrg2 obf srg id
fgo net/minecraft/src/C_3391_ 3391
\tE f_91074_ 91074
\ts f_91076_ 91076
\tt ()V m_91398_ 91398
\ta (Lfod;)V m_91152_ 91152
\t\t0 o p_91153_ 91153
bvh net/minecraft/src/C_507_ 507
\tdt ()D m_20185_ 20185
\tbW ()Z m_6144_ 6144
gkx net/minecraft/src/C_4105_ 4105
\tbW ()Z m_6144_ 108715
fod net/minecraft/src/C_3218_ 3218
'''
SCREEN = 'net/minecraft/client/gui/screens/Screen'
#  1.16.1's kind: tsrg v1, MCP's class names
TSRG1 = '''\
fgo net/minecraft/client/Minecraft
\tE field_71442_b
\ts field_71439_g
\tt ()V func_71407_l
\ta (Lfod;)V func_147108_a
bvh net/minecraft/entity/Entity
\tdt ()D func_226277_ct_
\tbW ()Z func_225608_bj_
gkx net/minecraft/client/entity/player/ClientPlayerEntity
\tbW ()Z func_225608_bj_
fod net/minecraft/client/gui/screen/Screen
'''
MCP_SCREEN = 'net/minecraft/client/gui/screen/Screen'


class ReadTests(unittest.TestCase):

  def setUp(self) -> None:
    self.names = SrgNames.fromText(TSRG)

  def test_fields_and_methods(self) -> None:
    self.assertEqual('f_91076_', self.names.fields[('fgo', 's')])
    self.assertEqual('m_91398_', self.names.methods[('fgo', 't', '()V')])
    self.assertEqual('m_91152_',
                     self.names.methods[('fgo', 'a', '(Lfod;)V')])
    self.assertEqual('m_6144_', self.names.methods[('gkx', 'bW', '()Z')])
    self.assertEqual((2, 5), (len(self.names.fields),
                              len(self.names.methods)),
                     "a parameter's line is no member")

  def test_another_format_or_a_line_it_can_t_read_is_refused(self) -> None:
    with self.assertRaises(ValueError) as said:
      SrgNames.fromText('tsrg obf srg\n')
    self.assertIn('tsrg2', str(said.exception))
    with self.assertRaises(ValueError) as said:
      SrgNames.fromText(TSRG + '\tlonely\n')
    self.assertIn('line 14', str(said.exception))


class TsrgOneTests(unittest.TestCase):
  """1.16.1's MCP config: tsrg v1, whose class names Forge runs too."""

  def setUp(self) -> None:
    self.read = SrgNames.fromText(TSRG1)
    self.names = MojangNames.fromText(LOG + OVERRIDE).onSrg(self.read)

  def test_read(self) -> None:
    self.assertTrue(self.read.renamesClasses)
    self.assertFalse(SrgNames.fromText(TSRG).renamesClasses,
                     "tsrg2's classes aren't the game's: Forge merges Mojang's")
    self.assertEqual(MCP_SCREEN, self.read.classes['fod'])
    self.assertEqual('field_71439_g', self.read.fields[('fgo', 's')])
    self.assertEqual('func_147108_a',
                     self.read.methods[('fgo', 'a', '(Lfod;)V')])

  def test_classes_by_mcp_members_by_srg(self) -> None:
    self.assertEqual('srg', self.names.kind)
    self.assertEqual(MINECRAFT, self.names.classes[MINECRAFT])
    self.assertEqual(MCP_SCREEN, self.names.classes[SCREEN])
    self.assertEqual('net/minecraft/client/entity/player/ClientPlayerEntity',
                     self.names.classes['net/minecraft/client/player/LocalPlayer'])
    self.assertEqual('func_147108_a', self.names.methods[(
      MINECRAFT, 'setScreen', '(L%s;)V' % SCREEN)])
    self.assertEqual('field_71439_g', self.names.fields[(
      MINECRAFT, 'player', 'Lnet/minecraft/client/player/LocalPlayer;')])
    self.assertEqual('(L%s;)V' % MCP_SCREEN,
                     self.names.running('(L%s;)V' % SCREEN))

  def test_a_line_it_can_t_read_is_refused(self) -> None:
    with self.assertRaises(ValueError) as said:
      SrgNames.fromText(TSRG1 + '\tlonely\n')
    self.assertIn('line 12', str(said.exception))


class ComposedTests(unittest.TestCase):

  def setUp(self) -> None:
    self.names = MojangNames.fromText(LOG + OVERRIDE).onSrg(
      SrgNames.fromText(TSRG))

  def test_members_by_srg_classes_by_mojang(self) -> None:
    self.assertEqual('srg', self.names.kind)
    self.assertEqual(MINECRAFT, self.names.classes[MINECRAFT])
    self.assertEqual('m_91398_',
                     self.names.methods[(MINECRAFT, 'tick', '()V')])
    self.assertEqual('m_91152_', self.names.methods[(
      MINECRAFT, 'setScreen', '(L%s;)V' % SCREEN)])
    self.assertEqual('f_91076_', self.names.fields[(
      MINECRAFT, 'player', 'Lnet/minecraft/client/player/LocalPlayer;')])

  def test_an_override_by_its_own_class_s_line(self) -> None:
    for owner in ('net/minecraft/world/entity/Entity',
                  'net/minecraft/client/player/LocalPlayer'):
      with self.subTest(owner=owner):
        self.assertEqual('m_6144_', self.names.methods[
          (owner, 'isShiftKeyDown', '()Z')])

  def test_a_name_srg_keeps_stays_the_obfuscated_one(self) -> None:
    self.assertEqual('<init>', self.names.methods[(
      MINECRAFT, '<init>', '(Lnet/minecraft/client/main/GameConfig;)V')])
    self.assertEqual('toString', self.names.methods[(
      MINECRAFT, 'toString', '()Ljava/lang/String;')])

  def test_a_descriptor_as_forge_runs_it(self) -> None:
    self.assertEqual('(L%s;)V' % SCREEN,
                     self.names.running('(L%s;)V' % SCREEN))

  def test_its_table_says_srg(self) -> None:
    folder = tempfile.mkdtemp(prefix='unittas-srg-table-')
    self.addCleanup(shutil.rmtree, folder, True)
    path = self.names.write(os.path.join(folder, 'names.txt'), '1.20.1')
    with io.open(path, encoding='utf-8') as file:
      lines = file.read().splitlines()
    self.assertEqual('unittas-names\t1\tsrg\t1.20.1', lines[0])
    self.assertIn('m\t%s\ttick\t()V\tm_91398_' % MINECRAFT, lines)
    self.assertIn('c\t%s\t%s' % (MINECRAFT, MINECRAFT), lines)


if __name__ == '__main__':
  unittest.main()

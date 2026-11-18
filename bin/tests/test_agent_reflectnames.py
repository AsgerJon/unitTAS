"""
Reflection's names beside each kind of renaming (SPEC.md 19.7 step 8),
with no game: the probe's own Members (agent/src/modern/java), compiled on
its own with a stand-in Version, asked through the agent's own Names
lookup, handed over as the bridge hands it (names::lookup), for the
members of a class of its own, Thing:
- by a table of kind srg (Forge 1.20.1's: Mojang's class names, SRG's
  member names), a class the table names by its own name is the game's,
  so a member is found by its running name, and not by that name spelt;
- by a table of kind obfuscated (1.21.1's), a class renamed is the game's
  likewise, and named to the orchestrator by its Mojang name;
- a class the table hasn't (the JDK's, a mod's) keeps its own names.
A Java 17 runtime and a javac from 17 on are needed; without them it
skips, saying so.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_agent_wrap import JAVAS, ROOT, java, javac  # noqa: E402

MODERN = os.path.join(ROOT, 'agent', 'src', 'modern', 'java')
BOOTSTRAP = os.path.join(ROOT, 'agent', 'src', 'bootstrap', 'java')
PROBE = 'io/github/asgerjon/unittas/probe/'
THING = PROBE + 'Thing'
#  each table: its kind, its version, Thing's Mojang name
TABLES = (('srg', '1.20.1', THING),
          ('obfuscated', '1.21.1', 'net/minecraft/world/Thing'))
#  the checks MembersCheck makes of each table, in its order
CHECKS = ('kind', 'game-field', 'game-method', 'running-name-spelt',
          'class-name', 'not-the-game-s')

#  the probe's Version, as far as Members asks it
VERSION = '''package io.github.asgerjon.unittas.probe;

final class Version {
\tstatic String port() {
\t\treturn "the check";
\t}
}
'''
#  the game's class, its members by their running names
THING_JAVA = '''package io.github.asgerjon.unittas.probe;

public final class Thing {
\tpublic int f_100_;

\tpublic float m_200_(int amount) {
\t\treturn amount;
\t}
}
'''
#  the bridge's handing over: the table's lookup as a JDK function
LOOKUP = '''package io.github.asgerjon.unittas.agent;

import java.io.IOException;
import java.nio.file.Path;
import java.util.function.Function;

public final class LookupOf {
\tpublic static Function<String, String> read(String table)
\t\tthrows IOException {
\t\tNames names = Names.read(Path.of(table));
\t\treturn names::lookup;
\t}
}
'''
#  each table's checks: "ok KIND CHECK" or "FAIL KIND CHECK: why"
CHECK = '''package io.github.asgerjon.unittas.probe;

import io.github.asgerjon.unittas.agent.LookupOf;
import java.lang.reflect.Method;

public final class MembersCheck {
\tprivate static String kind;

\tpublic static void main(String[] args) throws Exception {
\t\tfor (int at = 0; at < args.length; at += 3) {
\t\t\tMembers.names = LookupOf.read(args[at]);
\t\t\tkind = args[at + 1];
\t\t\tString mojang = args[at + 2].replace('/', '.');
\t\t\tMethod running =
\t\t\t\tThing.class.getDeclaredMethod("m_200_", int.class);
\t\t\tsay("kind", kind.equals(Members.namesKind()), Members.namesKind());
\t\t\tString field = Members.runningField(Thing.class, "inventory");
\t\t\tsay("game-field", "f_100_".equals(field), field);
\t\t\tsay("game-method", Members.isMethod(running, "getHealth"),
\t\t\t\t"not m_200_");
\t\t\tsay("running-name-spelt", !Members.isMethod(running, "m_200_")
\t\t\t\t&& Members.runningField(Thing.class, "f_100_") == null, "taken");
\t\t\tString named = Members.className(Thing.class);
\t\t\tsay("class-name", mojang.equals(named), named);
\t\t\tMethod length = String.class.getMethod("length");
\t\t\tsay("not-the-game-s", "value".equals(
\t\t\t\tMembers.runningField(String.class, "value"))
\t\t\t\t&& Members.isMethod(length, "length"), "renamed");
\t\t}
\t}

\tprivate static void say(String check, boolean ok, Object found) {
\t\tString named = kind + " " + check;
\t\tSystem.out.println(ok ? "ok " + named : "FAIL " + named + ": " + found);
\t}
}
'''


def table(kind: str, minecraft: str, mojang: str) -> str:
  """A table of names: Thing's Mojang names to its running ones."""
  return '\n'.join([
    'unittas-names\t1\t%s\t%s' % (kind, minecraft),
    'c\t%s\t%s' % (mojang, THING),
    'f\t%s\tinventory\tI\tf_100_' % mojang,
    'm\t%s\tgetHealth\t(I)F\tm_200_' % mojang]) + '\n'


class ReflectNamesTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    homes = {major: java(major) for major in JAVAS}
    compiler = javac(homes)
    if compiler is None or homes[17] is None:
      raise unittest.SkipTest('no Java 17 and javac from 17 on installed')
    cls.work = tempfile.mkdtemp(prefix='unittas-reflectnames-')
    sources = os.path.join(cls.work, 'src')
    written = []
    for relative, text in (
        (PROBE + 'Version.java', VERSION),
        (PROBE + 'Thing.java', THING_JAVA),
        (PROBE + 'MembersCheck.java', CHECK),
        ('io/github/asgerjon/unittas/agent/LookupOf.java', LOOKUP)):
      path = os.path.join(sources, relative)
      os.makedirs(os.path.dirname(path), exist_ok=True)
      with open(path, 'w', encoding='utf-8') as file:
        file.write(text)
      written.append(path)
    classes = os.path.join(cls.work, 'classes')
    compiled = subprocess.run(
      [compiler, '--release', '17', '-d', classes, '-sourcepath',
       os.pathsep.join([sources, BOOTSTRAP]), '-implicit:class',
       os.path.join(MODERN, PROBE, 'Members.java')] + written,
      capture_output=True, text=True)
    if compiled.returncode != 0:
      raise AssertionError('the check did not compile: ' + compiled.stderr)
    arguments = []
    for kind, minecraft, mojang in TABLES:
      path = os.path.join(cls.work, kind + '.txt')
      with open(path, 'w', encoding='utf-8') as file:
        file.write(table(kind, minecraft, mojang))
      arguments += [path, kind, mojang]
    ran = subprocess.run(
      [os.path.join(homes[17], 'bin', 'java'), '-cp', classes,
       'io.github.asgerjon.unittas.probe.MembersCheck'] + arguments,
      capture_output=True, text=True, timeout=120)
    cls.said = ran.stdout.splitlines()
    cls.errors = ran.stderr

  @classmethod
  def tearDownClass(cls) -> None:
    shutil.rmtree(cls.work, ignore_errors=True)

  def test_every_check_of_every_kind(self) -> None:
    for kind, _, _ in TABLES:
      for check in CHECKS:
        with self.subTest(kind=kind, check=check):
          self.assertIn('ok %s %s' % (kind, check), self.said,
                        '\n'.join(self.said) + self.errors)


if __name__ == '__main__':
  unittest.main()

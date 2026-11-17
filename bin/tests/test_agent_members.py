"""
The names the agent's probe reaches by reflection (Members.field and
Members.method, SPEC.md 19.7 step 6c), checked against each obfuscated
version's own names without a game: javac checks every call the shared
code makes against each version's stubs, but a member reached by its name
in a string isn't javac's to see, and a version that hasn't it fails only
as the probe loads (1.21.1's pick is GameRenderer's, not Minecraft's). Each
Members.field(X.class, "name") and Members.method(X.class, "name", ...) in
a version's sources must be in that version's table of names, X by the
file's imports. A version whose obfuscation log isn't in the download
cache is skipped, saying so.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import re
import sys
import unittest

BIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BIN)
sys.path.insert(0, os.path.join(os.path.dirname(BIN), 'python', 'src'))

import build_agent  # noqa: E402
from unittas.cache import defaultRoot  # noqa: E402
from unittas.mojangnames import MojangNames  # noqa: E402

_IMPORT = re.compile(r'^import ([\w.]+);', re.M)
_LOOKUP = re.compile(r'Members\.(field|method)\(\s*([\w.]+)\.class,\s*"(\w+)"')


def lookups(folders: tuple) -> list:
  """Each (file, kind, Mojang internal owner, name) the sources reach by name."""
  found = []
  for folder in folders:
    for where, _, files in os.walk(folder):
      for name in sorted(files):
        if not name.endswith('.java'):
          continue
        text = open(os.path.join(where, name), encoding='utf-8').read()
        imports = {each.split('.')[-1]: each for each in _IMPORT.findall(text)}
        for kind, owner, member in _LOOKUP.findall(text):
          head, _, nested = owner.partition('.')
          if head[0].islower():
            internal = owner.replace('.', '/')
          else:
            internal = imports.get(head, head).replace('.', '/') + (
              '$' + nested.replace('.', '$') if nested else '')
          found.append((name, kind, internal, member))
  return found


class MembersTests(unittest.TestCase):

  def test_each_obfuscated_version_has_every_name(self) -> None:
    checked = 0
    for minecraft, version in sorted(build_agent.VERSIONS.items()):
      if not version.obfuscated:
        continue
      log = os.path.join(defaultRoot(), 'versions', minecraft, 'client.txt')
      if not os.path.isfile(log):
        continue
      with open(log, encoding='utf-8') as file:
        names = MojangNames.fromText(file.read())
      fields = {(owner, name) for owner, name, _ in names.fields}
      methods = {(owner, name) for owner, name, _ in names.methods}
      sources = tuple(each for each in version.sources if each != build_agent.CORE)
      for file, kind, owner, member in lookups(sources):
        with self.subTest(minecraft=minecraft, file=file, member=owner + '.' + member):
          known = (owner, member) in (fields if kind == 'field' else methods)
          self.assertTrue(known, '%s has no %s %s.%s (%s reaches it by name)' % (minecraft, kind, owner, member, file))
        checked += 1
    if not checked:
      self.skipTest('no obfuscated version\'s obfuscation log is in the download cache (%s)' % defaultRoot())

  def test_the_lookups_are_found(self) -> None:
    """The scan itself: it finds the lookups the shared code is known to make."""
    found = lookups((build_agent.MODERN,))
    self.assertIn(('ModernVerbs.java', 'method', 'net/minecraft/client/gui/screens/inventory/AbstractContainerScreen',
                   'slotClicked'), found)
    self.assertIn(('ModernChat.java', 'field',
                   'net/minecraft/client/gui/components/CommandSuggestions$SuggestionsList', 'originalContents'), found)


if __name__ == '__main__':
  unittest.main()

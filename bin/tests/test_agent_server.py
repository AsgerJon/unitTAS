"""
A dedicated server's probe reaches no client class (SPEC.md 19.7 step
10b), with no game: the agent is built for each version (bin/build_agent.py,
the version's stubs where it is obfuscated) and its probe's classes read
from their constant pools. Every class the server's entry
(ModernServerEntry, its server hooks file's) reaches, through the probe's
own classes, names no class of the client's (net/minecraft/client,
com/mojang/blaze3d): a dedicated server has none, and the JVM's verifier
may load a class named there. A version whose jars aren't in the download
cache is skipped, saying so, and all are with no JDK 25; any other failure
to build (a compile error above all) is the test's error, never a skip.
And every game class and member it reaches is in the version's real
server, by the name it runs under there (V21): an obfuscated version's
by its server's own table (from its server_mappings), each member by the
class that declares it, as the agent renames them; 26.3's classes by
Mojang's names. A version whose server jar or tables aren't in the
download cache is skipped for that, saying so.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import glob
import io
import os
import re
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile

BIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BIN)
sys.path.insert(0, os.path.join(os.path.dirname(BIN), 'python', 'src'))

import build_agent  # noqa: E402
from unittas.cache import defaultRoot  # noqa: E402
from unittas.launcher import Missing  # noqa: E402

ENTRY = 'io/github/asgerjon/unittas/probe/ModernServerEntry'
OWN = 'io/github/asgerjon/unittas/'
CLIENT = ('net/minecraft/client/', 'com/mojang/blaze3d/')
#  a class named in a descriptor or a signature
NAMED = re.compile(r'L([A-Za-z0-9_/$]+)[;<]')


def named(data: bytes) -> set:
  """
  Every class a class file names: its constant pool's classes, and the
  classes in its descriptors and signatures (a method's parameter needs no
  class entry of its own).
  """
  count = struct.unpack('>H', data[8:10])[0]
  at, index = 10, 1
  out = set()
  while index < count:
    tag = data[at]
    if tag == 1:
      length = struct.unpack('>H', data[at + 1:at + 3])[0]
      text = data[at + 3:at + 3 + length].decode('utf-8', 'replace')
      out.update(NAMED.findall(text))
      if '/' in text and ';' not in text and '(' not in text:
        # a class entry's name is a plain internal name
        out.add(text.lstrip('['))
      at += 3 + length
    elif tag in (3, 4):
      at += 5
    elif tag in (5, 6):
      at += 9
      index += 1
    elif tag in (7, 8, 16, 19, 20):
      at += 3
    elif tag in (9, 10, 11, 12, 17, 18):
      at += 5
    elif tag == 15:
      at += 4
    else:
      raise ValueError('a constant pool tag %d no class file has' % tag)
    index += 1
  return out


def references(data: bytes) -> tuple:
  """
  A class file's references: the classes its constant pool names, and the
  members it refers to, each (f or m, owner, name, descriptor).
  """
  count = struct.unpack('>H', data[8:10])[0]
  at, index, entries = 10, 1, {}
  sizes = {3: 5, 4: 5, 5: 9, 6: 9, 8: 3, 15: 4, 16: 3, 17: 5, 18: 5,
           19: 3, 20: 3}
  while index < count:
    tag = data[at]
    if tag == 1:
      length = struct.unpack('>H', data[at + 1:at + 3])[0]
      entries[index] = (1, data[at + 3:at + 3 + length].decode('utf-8'))
      at += 3 + length
    elif tag == 7:
      entries[index] = (7, struct.unpack('>H', data[at + 1:at + 3])[0])
      at += 3
    elif tag in (9, 10, 11, 12):
      entries[index] = (tag,) + struct.unpack('>HH', data[at + 1:at + 5])
      at += 5
    elif tag in sizes:
      at += sizes[tag]
    else:
      raise ValueError('a constant pool tag %d no class file has' % tag)
    index += 2 if tag in (5, 6) else 1
  classes, members = set(), []
  for entry in entries.values():
    if entry[0] == 7:
      name = entries[entry[1]][1].lstrip('[')
      classes.add(name[1:-1] if name.endswith(';') else name)
    elif entry[0] in (9, 10, 11):
      owner = entries[entries[entry[1]][1]][1]
      _, name, descriptor = entries[entry[2]]
      members.append(('f' if entry[0] == 9 else 'm', owner,
                      entries[name][1], entries[descriptor][1]))
  return classes, members


def table(path: str) -> tuple:
  """A table of names (unittas.mojangnames): its classes and members."""
  classes, members = {}, {}
  with open(path, encoding='utf-8') as file:
    for line in file.read().split('\n')[1:]:
      parts = line.split('\t')
      if parts[0] == 'c':
        classes[parts[1]] = parts[2]
      elif parts[0] in ('f', 'm'):
        members[tuple(parts[:4])] = parts[4]
  return classes, members


def cached(pattern: str) -> str:
  """The download cache's one file by that pattern, or ''."""
  found = glob.glob(os.path.join(defaultRoot(), pattern))
  return found[0] if len(found) == 1 else ''


def serverClasses(minecraft: str) -> set:
  """The version's real server's classes: its bundler's inner jar's."""
  path = cached('versions/%s/server-%s.jar' % (minecraft, minecraft))
  if not path:
    return set()
  with zipfile.ZipFile(path) as bundler:
    inner = 'META-INF/versions/%s/server-%s.jar' % (minecraft, minecraft)
    real = zipfile.ZipFile(io.BytesIO(bundler.read(inner)))
  with real:
    return {name[:-len('.class')] for name in real.namelist()
            if name.endswith('.class')}


def reached(classes: dict) -> set:
  """The probe's own classes the server's entry reaches."""
  found, todo = {ENTRY}, [ENTRY]
  while todo:
    for name in references(classes[todo.pop()])[0]:
      if name.startswith(OWN) and name in classes and name not in found:
        found.add(name)
        todo.append(name)
  return found


def probeClasses(jar: str) -> dict:
  """The agent's probe's classes, by internal name: its inner jar's."""
  with zipfile.ZipFile(jar) as outer:
    inner = zipfile.ZipFile(io.BytesIO(outer.read(build_agent.INNER)))
  with inner:
    return {name[:-len('.class')]: inner.read(name)
            for name in inner.namelist() if name.endswith('.class')}


class ServerProbeTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls) -> None:
    try:
      build_agent.javac('')
    except FileNotFoundError as none:
      raise unittest.SkipTest(str(none))
    cls.work = tempfile.mkdtemp(prefix='unittas-agent-server-')
    cls.jars = {}
    try:
      for minecraft in build_agent.VERSIONS:
        try:
          cls.jars[minecraft] = build_agent.build(
            os.path.join(cls.work, 'agent-%s.jar' % minecraft), '', '',
            minecraft)
        except Missing as missing:
          # the version's jars not in the download cache: only that skips
          cls.jars[minecraft] = missing
    except BaseException:
      shutil.rmtree(cls.work, ignore_errors=True)
      raise

  @classmethod
  def tearDownClass(cls) -> None:
    shutil.rmtree(cls.work, ignore_errors=True)

  def test_the_server_s_entry_reaches_no_client_class(self) -> None:
    for minecraft, jar in self.jars.items():
      with self.subTest(minecraft=minecraft):
        if isinstance(jar, Exception):
          self.skipTest('no %s agent built here: %s' % (minecraft, jar))
        classes = probeClasses(jar)
        self.assertIn(ENTRY, classes)
        reached, path, todo = {ENTRY}, {ENTRY: [ENTRY]}, [ENTRY]
        found = []
        while todo:
          each = todo.pop()
          for name in named(classes[each]):
            if name.startswith(CLIENT):
              found.append(' -> '.join(path[each] + [name]))
            elif name.startswith(OWN) and name in classes \
                and name not in reached:
              reached.add(name)
              path[name] = path[each] + [name]
              todo.append(name)
        self.assertEqual([], sorted(found)[:10])


  def test_what_it_reaches_is_the_server_s(self) -> None:
    for minecraft, jar in self.jars.items():
      with self.subTest(minecraft=minecraft):
        if isinstance(jar, Exception):
          self.skipTest('no %s agent built here: %s' % (minecraft, jar))
        inServer = serverClasses(minecraft)
        if not inServer:
          self.skipTest('no %s server jar in the download cache'
                        % minecraft)
        classes = probeClasses(jar)
        found = []
        if build_agent.VERSIONS[minecraft].obfuscated:
          found = self.byTables(minecraft, jar, classes, inServer)
        else:
          client = cached('versions/%s/%s.jar' % (minecraft, minecraft))
          with zipfile.ZipFile(client) as each:
            game = {name[:-len('.class')] for name in each.namelist()
                    if name.endswith('.class')}
          for own in sorted(reached(classes)):
            named, members = references(classes[own])
            for name in named | {member[1] for member in members}:
              if name in game and name not in inServer:
                found.append('%s: %s' % (own, name))
        self.assertEqual([], sorted(set(found))[:10])

  def byTables(self, minecraft: str, jar: str, classes: dict,
               inServer: set) -> list:
    """What an obfuscated version's server lacks, by its own table."""
    clientPath = cached('names/%s-obfuscated-*.txt' % minecraft)
    serverPath = cached('names/%s-server-obfuscated-*.txt' % minecraft)
    if not (clientPath and serverPath):
      self.skipTest("no %s client's and server's tables of names in the "
                    'download cache' % minecraft)
    client, clientMembers = table(clientPath)
    server, serverMembers = table(serverPath)
    with zipfile.ZipFile(jar) as outer:
      inner = zipfile.ZipFile(io.BytesIO(outer.read(build_agent.INNER)))
    with inner:
      text = inner.read(build_agent.DECLARERS).decode('utf-8')
    declarers = {}
    for line in text.split('\n'):
      parts = line.split('\t')
      if len(parts) == 4:
        declarers[tuple(parts[:3])] = parts[3]
    found = []
    for own in sorted(reached(classes)):
      named, members = references(classes[own])
      for name in named:
        if name not in client:
          continue
        if name not in server:
          found.append('%s: class %s not in the server' % (own, name))
        elif server[name] not in inServer:
          found.append('%s: class %s (%s) not in the server jar'
                       % (own, name, server[name]))
      for kind, owner, name, descriptor in members:
        if owner not in client:
          continue
        declarer = declarers.get((owner, name, descriptor), owner)
        key = (kind, declarer, name, descriptor)
        if key in clientMembers and key not in serverMembers:
          found.append('%s: %s.%s%s not in the server'
                       % (own, declarer, name, descriptor))
    return found


if __name__ == '__main__':
  unittest.main()

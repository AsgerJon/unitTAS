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
Mojang's names. Each member is also declared in the server jar itself,
by its class or one above it: a table may list a member the server jar
hasn't (1.16.1's Level.setRainLevel, client-only). A version whose server
jar or tables aren't in the download cache is skipped for that, saying
so.
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
from typing import Optional

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


def pool(data: bytes) -> tuple:
  """
  A class file's constant pool: its UTF-8, class and member entries by
  index, and where the pool ends.
  """
  count = struct.unpack('>H', data[8:10])[0]
  at, index, entries = 10, 1, {}
  sizes = {3: 5, 4: 5, 5: 9, 6: 9, 8: 3, 15: 4, 16: 3, 17: 5, 18: 5,
           19: 3, 20: 3}
  while index < count:
    tag = data[at]
    if tag == 1:
      length = struct.unpack('>H', data[at + 1:at + 3])[0]
      text = data[at + 3:at + 3 + length].decode('utf-8', 'replace')
      entries[index] = (1, text)
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
  return entries, at


def declared(data: bytes) -> tuple:
  """
  What a class file declares: its superclass ('' for none), its
  interfaces, and its fields' and methods' names and descriptors.
  """
  entries, at = pool(data)

  def className(index: int) -> str:
    """The class entry's internal name."""
    return entries[entries[index][1]][1]

  parent, count = struct.unpack('>HH', data[at + 4:at + 8])
  at += 8
  interfaces = [className(struct.unpack('>H', data[at + 2 * i:
                                                    at + 2 * i + 2])[0])
                for i in range(count)]
  at += 2 * count
  members = set()
  for _ in ('fields', 'methods'):
    count = struct.unpack('>H', data[at:at + 2])[0]
    at += 2
    for _ in range(count):
      name, descriptor, attributes = struct.unpack('>HHH',
                                                   data[at + 2:at + 8])
      members.add((entries[name][1], entries[descriptor][1]))
      at += 8
      for _ in range(attributes):
        at += 6 + struct.unpack('>I', data[at + 2:at + 6])[0]
  return className(parent) if parent else '', interfaces, members


def declarer(jar: zipfile.ZipFile, names: set, parsed: dict, owner: str,
             member: tuple) -> str:
  """
  The jar's class that declares the member (its name and descriptor),
  looked for from the owner up its superclasses and interfaces, as the
  JVM resolves a reference; '' where no class of the jar's does (one
  above them all, the JDK's, may). Each class read is kept in parsed.
  """
  todo, seen = [owner], set()
  while todo:
    each = todo.pop()
    if each in seen or each not in names:
      continue
    seen.add(each)
    if each not in parsed:
      parsed[each] = declared(jar.read(each + '.class'))
    parent, interfaces, members = parsed[each]
    if member in members:
      return each
    todo.extend(([parent] if parent else []) + interfaces)
  return ''


def obfuscated(descriptor: str, classes: dict) -> str:
  """A descriptor by a table's names for its classes (Mojang's to it)."""
  return re.sub(r'L([^;]+);',
                lambda found: 'L%s;' % classes.get(found.group(1),
                                                   found.group(1)),
                descriptor)


def references(data: bytes) -> tuple:
  """
  A class file's references: the classes its constant pool names, and the
  members it refers to, each (f or m, owner, name, descriptor).
  """
  entries = pool(data)[0]
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


def serverJar(minecraft: str) -> Optional[zipfile.ZipFile]:
  """
  The version's real server's jar of classes: its bundler's inner jar
  (from 1.18 on), or the jar itself before (1.16.1's server is a plain
  jar); None where the download cache has no server jar.
  """
  path = cached('versions/%s/server-%s.jar' % (minecraft, minecraft))
  if not path:
    return None
  inner = 'META-INF/versions/%s/server-%s.jar' % (minecraft, minecraft)
  with zipfile.ZipFile(path) as outer:
    data = outer.read(inner) if inner in outer.namelist() else b''
  if not data:
    with open(path, 'rb') as file:
      data = file.read()
  return zipfile.ZipFile(io.BytesIO(data))


def classNames(jar: zipfile.ZipFile) -> set:
  """A jar's classes, by internal name."""
  return {name[:-len('.class')] for name in jar.namelist()
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
  maxDiff = None

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
        real = serverJar(minecraft)
        if real is None:
          self.skipTest('no %s server jar in the download cache'
                        % minecraft)
        with real:
          classes = probeClasses(jar)
          if build_agent.VERSIONS[minecraft].obfuscated:
            found = self.byTables(minecraft, jar, classes, real)
          else:
            found = self.byMojang(minecraft, classes, real)
        self.assertEqual([], sorted(set(found))[:10])

  def byMojang(self, minecraft: str, classes: dict,
               real: zipfile.ZipFile) -> list:
    """
    What a version under Mojang's names lacks in its server: a game class
    the probe names, or a game member it reaches that the server's class
    and those above it don't declare (the client's do).
    """
    inServer = classNames(real)
    path = cached('versions/%s/%s.jar' % (minecraft, minecraft))
    found = []
    with zipfile.ZipFile(path) as client:
      game, inClient, inJar = classNames(client), {}, {}
      for own in sorted(reached(classes)):
        named, members = references(classes[own])
        for name in named | {member[1] for member in members}:
          if name in game and name not in inServer:
            found.append('%s: %s' % (own, name))
        for _, owner, name, descriptor in members:
          member = (name, descriptor)
          if owner not in game or owner not in inServer \
              or not declarer(client, game, inClient, owner, member):
            continue
          if not declarer(real, inServer, inJar, owner, member):
            found.append('%s: %s.%s%s not in the server jar'
                         % (own, owner, name, descriptor))
    return found

  def byTables(self, minecraft: str, jar: str, classes: dict,
               real: zipfile.ZipFile) -> list:
    """
    What an obfuscated version's server lacks, by its own table: a class
    or member the table hasn't, or one the server jar hasn't by the name
    the table gives (its server_mappings may list a member the server
    jar's class has not, a client-only one).
    """
    inServer, inJar = classNames(real), {}
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
        at = declarers.get((owner, name, descriptor), owner)
        key = (kind, at, name, descriptor)
        if key not in clientMembers or owner not in server:
          continue
        if key not in serverMembers:
          found.append('%s: %s.%s%s not in the server'
                       % (own, at, name, descriptor))
          continue
        running = (serverMembers[key], obfuscated(descriptor, server))
        if not declarer(real, inServer, inJar, server[owner], running):
          found.append('%s: %s.%s%s (%s.%s%s) not in the server jar'
                       % ((own, at, name, descriptor, server[owner])
                          + running))
    return found


if __name__ == '__main__':
  unittest.main()

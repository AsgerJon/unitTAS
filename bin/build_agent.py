"""
Builds unitTAS's loader-free probe for a version (SPEC.md 19.7 steps 5 and 6): a Java agent, no Gradle, no Loom, no
library. 26.3 unless --minecraft names another of VERSIONS.

  python3 bin/build_agent.py [--minecraft VERSION] [--out JAR] [--cache DIR] [--java25 JDK]

What it compiles against comes from unitTAS's own launcher: 26.3's client jar and its libraries for this system,
from the download cache (~/.cache/unittas, or UNITTAS_CACHE, or --cache), each held to its sha1, fetched there if
missing. Java 25's javac compiles, in two passes:
- the bootstrap (agent/src/bootstrap/java): the premain, the class rewriter and the bridge, JDK classes only, for
  Java 17, so that one bootstrap runs on every version's Java (17 for 1.20.1, 21 for 1.21.1, 25 for 26.3: SPEC.md
  19.7 step 6);
- the probe (src/probe-core/java and the version's own folders), against the game and the bootstrap, for the game's
  Java.
The probe's classes go into a jar of their own (unittas-probe-inner.jar), which goes inside the agent's jar beside
the bootstrap's classes: on the application class path only the bootstrap is; the bridge loads the probe under the
game's own class loader. The version's hooks (its hooks.txt) go beside the bootstrap, which reads them at premain.
Both manifests carry the root's mod_version. The jar: agent/build/unittas-probe-VERSION.jar unless --out says
otherwise. Exits 1 with javac's own words when it fails, 2 when something it needs is missing.
It uses the standard library and unitTAS's own Python package only.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'python', 'src'))

MINECRAFT = '26.3'
INNER = 'unittas-probe-inner.jar'
#  the version's hooks, beside the bootstrap (its Agent.HOOKS_FILE), and a dedicated server's (Agent.SERVER_HOOKS_FILE)
HOOKS_FILE = 'unittas-probe-hooks.txt'
SERVER_HOOKS_FILE = 'unittas-probe-server-hooks.txt'
PREMAIN = 'io.github.asgerjon.unittas.agent.Agent'
AGENT = os.path.join(ROOT, 'agent', 'src')
OUT = os.path.join(ROOT, 'agent', 'build', 'unittas-probe-%s.jar')
BOOTSTRAP = os.path.join(AGENT, 'bootstrap', 'java')
CORE = os.path.join(ROOT, 'src', 'probe-core', 'java')
#  the probe's code shared by the versions from 1.20.1 on, compiled for each against its own classes (19.7 step 6c)
MODERN = os.path.join(AGENT, 'modern', 'java')
#  the builder's own tools (stubs, declarers: SPEC.md 19.7 step 6b), never shipped
TOOLS = os.path.join(AGENT, 'build', 'java')
#  an obfuscated version's declarers, in the probe's jar (its RenamingLoader.DECLARERS)
DECLARERS = 'unittas-probe-declarers.txt'


@dataclass(frozen=True)
class Version:
  """
  One version the builder makes an agent for: its probe's source folders, its Java (javac --release), its hooks (a
  client's, and a dedicated server's beside it: server-hooks.txt), and whether the game runs obfuscated (before 26.1:
  the probe compiled against its stubs and renamed as it loads).
  """
  release: str
  sources: tuple
  hooks: str
  obfuscated: bool = False

  @property
  def serverHooks(self) -> str:
    """A dedicated server's hooks: server-hooks.txt beside the client's hooks.txt."""
    return os.path.join(os.path.dirname(self.hooks), 'server-hooks.txt')


VERSIONS = {
  '26.3': Version('25', (CORE, MODERN, os.path.join(AGENT, 'v26', 'java')), os.path.join(AGENT, 'v26', 'hooks.txt')),
  '1.21.1': Version('21', (CORE, MODERN, os.path.join(AGENT, 'v1_21_1', 'java')),
                    os.path.join(AGENT, 'v1_21_1', 'hooks.txt'), True),
  '1.20.1': Version('17', (CORE, MODERN, os.path.join(AGENT, 'v1_20_1', 'java')),
                    os.path.join(AGENT, 'v1_20_1', 'hooks.txt'), True),
}
#  the bootstrap's Java: the oldest a version runs on
BOOTSTRAP_RELEASE = '17'
JAVA_25 = ('/usr/lib/jvm/java-25-openjdk', '/usr/lib/jvm/java-25-openjdk-amd64', '/usr/lib/jvm/jdk-25')
#  every entry's time, so the same classes make the same jar
STAMP = (1980, 1, 1, 0, 0, 0)


def sourcesUnder(folder: str) -> list:
  """Every .java file under the folder, in a fixed order."""
  found = []
  for where, folders, names in os.walk(folder):
    folders.sort()
    found.extend(os.path.join(where, name) for name in sorted(names) if name.endswith('.java'))
  return sorted(found)


def modVersion() -> str:
  """The root's mod_version (gradle.properties), which the release buttons stamp: one version for every probe."""
  with open(os.path.join(ROOT, 'gradle.properties'), encoding='utf-8') as file:
    for line in file:
      key, _, value = line.partition('=')
      if key.strip() == 'mod_version':
        return value.strip()
  raise SystemExit('bin/build_agent.py: no mod_version in %s' % os.path.join(ROOT, 'gradle.properties'))


def _manifest(lines: list) -> bytes:
  return ('\r\n'.join(['Manifest-Version: 1.0'] + lines) + '\r\n\r\n').encode('utf-8')


def _add(jar: zipfile.ZipFile, name: str, data: bytes) -> None:
  entry = zipfile.ZipInfo(name, STAMP)
  entry.compress_type = zipfile.ZIP_DEFLATED
  entry.external_attr = 0o644 << 16
  jar.writestr(entry, data)


def _addFolder(jar: zipfile.ZipFile, folder: str) -> None:
  for path in sorted(sourcesUnderAll(folder)):
    with open(path, 'rb') as file:
      _add(jar, os.path.relpath(path, folder).replace(os.sep, '/'), file.read())


def sourcesUnderAll(folder: str) -> list:
  """Every file under the folder."""
  found = []
  for where, _, names in os.walk(folder):
    found.extend(os.path.join(where, name) for name in names)
  return found


def assemble(bootstrapClasses: str, probeClasses: str, version: str, out: str, hooks: bytes, minecraft: str,
             serverHooks: bytes = b'') -> str:
  """
  The agent's jar at 'out': its manifest first, the bootstrap's classes, the version's hooks beside them (a client's,
  and a dedicated server's where given), and the probe's jar inside it.
  """
  inner = io.BytesIO()
  with zipfile.ZipFile(inner, 'w') as jar:
    _add(jar, 'META-INF/MANIFEST.MF', _manifest(['Implementation-Title: unitTAS probe for %s' % minecraft,
                                                 'Implementation-Version: %s' % version]))
    _addFolder(jar, probeClasses)
  os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
  with zipfile.ZipFile(out, 'w') as jar:
    _add(jar, 'META-INF/MANIFEST.MF', _manifest(['Premain-Class: %s' % PREMAIN,
                                                 'Implementation-Title: unitTAS probe for %s (a Java agent)' % minecraft,
                                                 'Implementation-Version: %s' % version]))
    _addFolder(jar, bootstrapClasses)
    _add(jar, HOOKS_FILE, hooks)
    if serverHooks:
      _add(jar, SERVER_HOOKS_FILE, serverHooks)
    _add(jar, INNER, inner.getvalue())
  return out


def javac(java25: str) -> str:
  """Java 25's javac: in the JDK named, else the usual places."""
  for home in ([java25] if java25 else list(JAVA_25)):
    binary = os.path.join(home, 'bin', 'javac')
    if os.path.isfile(binary) and os.access(binary, os.X_OK):
      return binary
  raise FileNotFoundError('no Java 25 javac at %s: install a JDK 25, or name it with --java25' % (
    java25 or ', '.join(JAVA_25)))


def _compile(compiler: str, classPath: list, sources: list, into: str, release: str) -> None:
  os.makedirs(into, exist_ok=True)
  command = [compiler, '--release', release, '-encoding', 'UTF-8', '-nowarn', '-d', into]
  if classPath:
    command += ['-cp', os.pathsep.join(classPath)]
  done = subprocess.run(command + sources, stdin=subprocess.DEVNULL, capture_output=True, text=True)
  if done.returncode != 0:
    raise RuntimeError('javac failed:\n' + done.stdout + done.stderr)


def compileBootstrap(compiler: str, into: str) -> None:
  """The bootstrap's classes into the folder, for Java 17: it needs the JDK only, so any javac from 17 does."""
  _compile(compiler, [], sourcesUnder(BOOTSTRAP), into, BOOTSTRAP_RELEASE)


def _tool(compiler: str, tools: str, name: str, *args: str) -> None:
  """One of the builder's tools, run on the JDK whose javac compiles; RuntimeError with its own words if it fails."""
  java = os.path.join(os.path.dirname(compiler), 'java')
  done = subprocess.run([java, '-cp', tools, 'io.github.asgerjon.unittas.agent.' + name] + list(args),
                        stdin=subprocess.DEVNULL, capture_output=True, text=True)
  if done.returncode != 0:
    raise RuntimeError('%s failed:\n%s%s' % (name, done.stdout, done.stderr))


def stubs(sources, minecraft: str, client: str, compiler: str, tools: str) -> str:
  """
  An obfuscated version's stubs (SPEC.md 19.7 step 6b): its client jar's classes by Mojang's names, declarations only,
  made once into the download cache by the client jar's sha1, never shipped.
  """
  from unittas.cache import fileSha1
  from unittas.launcher import namesTable
  target = sources.cache.path('stubs/%s-%s.jar' % (minecraft, fileSha1(client)))
  if not os.path.isfile(target):
    os.makedirs(os.path.dirname(target), exist_ok=True)
    _tool(compiler, tools, 'Stubs', client, namesTable(sources, minecraft), target)
  return target


def build(out: str = '', cacheRoot: str = '', java25: str = '', minecraft: str = MINECRAFT) -> str:
  """
  The version's agent's jar, built from the sources as they are now: two javac passes, then the jars. For an
  obfuscated version the probe is compiled against its stubs, and its declarers found and packed with it.
  """
  from unittas.cache import Cache, defaultRoot
  from unittas.launcher import Sources, classPath
  if minecraft not in VERSIONS:
    raise ValueError('no agent for %s: the builder knows %s' % (minecraft, ', '.join(sorted(VERSIONS))))
  version = VERSIONS[minecraft]
  out = out or OUT % minecraft
  compiler = javac(java25)
  sources = Sources(cache=Cache(cacheRoot or defaultRoot()))
  game = classPath(sources, minecraft)
  os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
  work = tempfile.mkdtemp(prefix='classes-', dir=os.path.dirname(os.path.abspath(out)))
  try:
    bootstrapClasses = os.path.join(work, 'bootstrap')
    probeClasses = os.path.join(work, 'probe')
    compileBootstrap(compiler, bootstrapClasses)
    against = game
    if version.obfuscated:
      tools = os.path.join(work, 'tools')
      _compile(compiler, [], sourcesUnder(BOOTSTRAP) + sourcesUnder(TOOLS), tools, BOOTSTRAP_RELEASE)
      gameStubs = stubs(sources, minecraft, game[-1], compiler, tools)
      against = game[:-1] + [gameStubs]
    _compile(compiler, against + [bootstrapClasses], [path for folder in version.sources for path in sourcesUnder(folder)],
             probeClasses, version.release)
    if version.obfuscated:
      _tool(compiler, tools, 'Declarers', gameStubs, probeClasses, os.path.join(probeClasses, DECLARERS))
    with open(version.hooks, 'rb') as file:
      hooks = file.read()
    with open(version.serverHooks, 'rb') as file:
      serverHooks = file.read()
    return assemble(bootstrapClasses, probeClasses, modVersion(), out, hooks, minecraft, serverHooks)
  finally:
    shutil.rmtree(work, ignore_errors=True)


def main(args: list) -> int:
  taken = {}
  for option in ('--minecraft', '--out', '--cache', '--java25'):
    if option in args:
      at = args.index(option)
      if at + 1 >= len(args):
        print(__doc__.strip().split('\n')[2])
        return 2
      taken[option] = args[at + 1]
      del args[at:at + 2]
  if args:
    print(__doc__.strip().split('\n')[2])
    return 2
  from unittas.launcher import Missing
  try:
    jar = build(taken.get('--out', ''), taken.get('--cache', ''), taken.get('--java25', ''),
                taken.get('--minecraft', MINECRAFT))
  except (RuntimeError, ValueError) as failed:
    print('bin/build_agent.py: %s' % failed)
    return 1
  except (Missing, OSError) as missing:
    print('bin/build_agent.py: %s' % missing)
    return 2
  print(jar)
  return 0


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))

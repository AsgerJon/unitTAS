"""
Builds unitTAS's loader-free probe for 26.3 (SPEC.md 19.7 step 5): a Java agent, no Gradle, no Loom, no library.

  python3 bin/build_agent.py [--out JAR] [--cache DIR] [--java25 JDK]

What it compiles against comes from unitTAS's own launcher: 26.3's client jar and its libraries for this system,
from the download cache (~/.cache/unittas, or UNITTAS_CACHE, or --cache), each held to its sha1, fetched there if
missing. Java 25's javac compiles, in two passes:
- the bootstrap (agent/src/bootstrap/java): the premain, the class rewriter and the bridge, JDK classes only, for
  Java 17, so that one bootstrap runs on every version's Java (17 for 1.20.1, 21 for 1.21.1, 25 for 26.3: SPEC.md
  19.7 step 6);
- the probe (src/probe-core/java and agent/src/v26/java), against the game and the bootstrap, for the game's Java.
The probe's classes go into a jar of their own (unittas-probe-inner.jar), which goes inside the agent's jar beside
the bootstrap's classes: on the application class path only the bootstrap is; the bridge loads the probe under the
game's own class loader. Both manifests carry the root's mod_version. The jar: agent/build/unittas-probe-26.3.jar
unless --out says otherwise. Exits 1 with javac's own words when it fails, 2 when something it needs is missing.
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'python', 'src'))

MINECRAFT = '26.3'
INNER = 'unittas-probe-inner.jar'
PREMAIN = 'io.github.asgerjon.unittas.agent.Agent'
OUT = os.path.join(ROOT, 'agent', 'build', 'unittas-probe-26.3.jar')
BOOTSTRAP = os.path.join(ROOT, 'agent', 'src', 'bootstrap', 'java')
PROBE = (os.path.join(ROOT, 'src', 'probe-core', 'java'), os.path.join(ROOT, 'agent', 'src', 'v26', 'java'))
#  the bootstrap's Java (the oldest a version runs on), and the 26.3 probe's (its game's)
BOOTSTRAP_RELEASE = '17'
PROBE_RELEASE = '25'
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


def assemble(bootstrapClasses: str, probeClasses: str, version: str, out: str) -> str:
  """The agent's jar at 'out': its manifest first, the bootstrap's classes, and the probe's jar inside it."""
  inner = io.BytesIO()
  with zipfile.ZipFile(inner, 'w') as jar:
    _add(jar, 'META-INF/MANIFEST.MF', _manifest(['Implementation-Title: unitTAS probe for %s' % MINECRAFT,
                                                 'Implementation-Version: %s' % version]))
    _addFolder(jar, probeClasses)
  os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
  with zipfile.ZipFile(out, 'w') as jar:
    _add(jar, 'META-INF/MANIFEST.MF', _manifest(['Premain-Class: %s' % PREMAIN,
                                                 'Implementation-Title: unitTAS probe for %s (a Java agent)' % MINECRAFT,
                                                 'Implementation-Version: %s' % version]))
    _addFolder(jar, bootstrapClasses)
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


def build(out: str = OUT, cacheRoot: str = '', java25: str = '') -> str:
  """The agent's jar, built from the sources as they are now: two javac passes, then the jars."""
  from unittas.cache import Cache, defaultRoot
  from unittas.launcher import Sources, classPath
  compiler = javac(java25)
  game = classPath(Sources(cache=Cache(cacheRoot or defaultRoot())), MINECRAFT)
  os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
  work = tempfile.mkdtemp(prefix='classes-', dir=os.path.dirname(os.path.abspath(out)))
  try:
    bootstrapClasses = os.path.join(work, 'bootstrap')
    probeClasses = os.path.join(work, 'probe')
    compileBootstrap(compiler, bootstrapClasses)
    _compile(compiler, game + [bootstrapClasses], [path for folder in PROBE for path in sourcesUnder(folder)],
             probeClasses, PROBE_RELEASE)
    return assemble(bootstrapClasses, probeClasses, modVersion(), out)
  finally:
    shutil.rmtree(work, ignore_errors=True)


def main(args: list) -> int:
  taken = {}
  for option in ('--out', '--cache', '--java25'):
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
    jar = build(taken.get('--out', OUT), taken.get('--cache', ''), taken.get('--java25', ''))
  except RuntimeError as failed:
    print('bin/build_agent.py: %s' % failed)
    return 1
  except (Missing, OSError) as missing:
    print('bin/build_agent.py: %s' % missing)
    return 2
  print(jar)
  return 0


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))

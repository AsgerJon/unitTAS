"""
Step 9 of phase 3 (SPEC.md section 9.3): old saves through the orchestrator, on a save set the development client
makes itself (run/oldsaves/selfcheck: two test worlds, each with a gold marker block and a building list naming it),
so nothing is downloaded. The self suite 'oldsaves' (SaveTests, Java in src/self, its Python twin in
tests/selfsuite/oldsaves.py) in each save, as found and as this game saved it:
- 1. by the script, ./unittas.sh oldsaves dev@selfcheck (Java's save mode, as before);
- 2. by the orchestrator, unittas run --java oldsaves --saves ... (java.run, Java's save mode inside it);
- 3. by the orchestrator in Python, unittas run selfsuite.oldsaves --saves ... (the Python Run's save mode).
All three alike, by bin/compare_reports.py: 'the same'. Then 4: the Python twin in the real client, every line ok (the
release jar doesn't carry the self source set's Java suite).

  python -m unittas.selftest test_oldsaves.      (through the watcher: "probe test_oldsaves.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import unittest

from probegame import READY_SECONDS, ROOT, modVersion, results
from unittas.api import Game
from unittas.dev import DevGame
from unittas.gamefiles import copyExactly, removeTree

SET = os.path.join(ROOT, 'run', 'oldsaves', 'selfcheck')
#  each save and its marker
SAVES = (('selfcheck-far', (40, 4, -24)), ('selfcheck-gold', (8, 4, 8)))
TESTS = ('testA_loadedWithoutErrors', 'testB_itsMarkerIsThere', 'testC_theOneNamedIsOpen')
RESULT = re.compile(r'^(.+?) \.\.\. (\S.*?) \(\d+\.\d s\)$')


def makeSaves() -> None:
  """The self-check saves, made once by the development client: a test world each, its marker set, closed, kept."""
  if all(os.path.isfile(os.path.join(SET, name, 'level.dat')) for name, _ in SAVES):
    return
  game = DevGame(ROOT, results(), 'selfcheck-make')
  connection = game.start()
  try:
    connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    made = Game(connection)
    os.makedirs(SET, exist_ok=True)
    for name, (x, y, z) in SAVES:
      folder = os.path.join(game.gameDir, 'saves', name)
      if os.path.lexists(folder):
        removeTree(folder)
      made.request('world.create', {'folder': name}, timeout=240)
      made.request('world.prepare')
      made.setBlock((x, y, z), 'minecraft:gold_block')
      made.request('world.close', timeout=240)
      kept = os.path.join(SET, name)
      if os.path.lexists(kept):
        removeTree(kept)
      copyExactly(folder, kept)
      removeTree(folder)
      with open(os.path.join(SET, name + '.buildings'), 'w', encoding='utf-8') as file:
        file.write('# made by python/tests/probe/test_oldsaves.py on %s: name dim x1 y1 z1 x2 y2 z2 view x y z yaw '
                   'pitch\n' % time.strftime('%Y-%m-%d %H:%M'))
        file.write('marker 0 %d %d %d %d %d %d view %.2f %.2f %.2f 180.0 10.0\n' % (x, y, z, x, y, z, x + 0.5, y + 1,
                                                                                   z + 3.5))
  finally:
    game.stop()


class OldSavesTests(unittest.TestCase):
  reports = {}

  @classmethod
  def setUpClass(cls) -> None:
    makeSaves()
    folder = os.path.join(results(), 'specs')
    os.makedirs(folder, exist_ok=True)
    cls.gradleSpec = os.path.join(folder, 'oldsaves-gradle.toml')
    with open(cls.gradleSpec, 'w', encoding='utf-8') as file:
      file.write('minecraft = "1.7.10"\nloader = { forge = "10.13.4.1614" }\nclient = "gradle"\n[gradle]\n'
                 'project = "%s"\ntask = "runClient"\ngame = "%s"\n' % (ROOT, os.path.join(ROOT, 'run', 'client')))
    # unitTAS's own Gradle cache, as ./unittas.sh gives its Gradle
    cls.environment = dict(os.environ, GRADLE_USER_HOME=os.path.join(ROOT, '.gradle-home'),
                           UNITTAS_GRADLE_HOME=os.path.join(ROOT, '.gradle-home'))
    cls.environment.pop('UNITTAS_STAMP', None)

  def unittas(self, name: str, *args: str, spec: str = None) -> str:
    """'python -m unittas run ...' as a user runs it; its report's path, after checking it exited 0."""
    out = os.path.join(results(), name)
    process = subprocess.run([sys.executable, '-m', 'unittas', 'run'] + list(args) + [
      '--saves', SET, '--instance', spec or self.gradleSpec, '--results', out], cwd=os.path.join(ROOT, 'python', 'tests'),
      env=self.environment, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=READY_SECONDS + 1200)
    with open(os.path.join(out, 'said.txt'), 'w', encoding='utf-8') as file:
      file.write(process.stdout + process.stderr)
    self.assertEqual(0, process.returncode, process.stdout[-3000:] + process.stderr[-3000:])
    return os.path.join(out, 'report.txt')

  def lines(self, report: str) -> list:
    with open(report, encoding='utf-8') as file:
      return [(found.group(1), found.group(2)) for found in map(RESULT.match, file.read().split('\n')) if found]

  def expected(self) -> list:
    return [('SaveTests.%s [%s, load %d]' % (test, name, load), 'ok') for load in (1, 2) for name, _ in SAVES
            for test in TESTS]

  def same(self, before: str, after: str) -> None:
    compared = subprocess.run([sys.executable, '-I', os.path.join(ROOT, 'bin', 'compare_reports.py'), before, after],
                              capture_output=True, text=True)
    self.assertEqual(0, compared.returncode, compared.stdout + compared.stderr)
    self.assertIn('the same: %d tests' % len(self.expected()), compared.stdout)

  def test_1_the_script(self) -> None:
    relative = os.path.relpath(os.path.join(results(), 'oldsaves-script'), os.path.join(ROOT, 'unittas-results'))
    process = subprocess.run([os.path.join(ROOT, 'unittas.sh'), 'oldsaves', 'dev@selfcheck'], cwd=ROOT,
                             env=dict(self.environment, UNITTAS_STAMP=relative), stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=READY_SECONDS + 1200)
    report = os.path.join(ROOT, 'unittas-results', relative, 'report.txt')
    self.assertEqual(0, process.returncode, process.stdout[-3000:] + process.stderr[-3000:])
    self.assertEqual(sorted(self.expected()), sorted(self.lines(report)))
    OldSavesTests.reports['script'] = report

  def test_2_java_by_the_orchestrator(self) -> None:
    report = self.unittas('oldsaves-java', '--java', 'oldsaves')
    self.assertEqual(sorted(self.expected()), sorted(self.lines(report)))
    self.assertEqual(sorted(name for name, _ in SAVES),
                     sorted(os.listdir(os.path.join(results(), 'oldsaves-java', 'saves-after'))))
    if 'script' in OldSavesTests.reports:
      self.same(OldSavesTests.reports['script'], report)
    OldSavesTests.reports['java'] = report

  def test_3_python_by_the_orchestrator(self) -> None:
    report = self.unittas('oldsaves-python', 'selfsuite.oldsaves')
    self.assertEqual(self.expected(), self.lines(report), 'in the Java runner\'s order')
    self.assertEqual(sorted(name for name, _ in SAVES),
                     sorted(os.listdir(os.path.join(results(), 'oldsaves-python', 'saves-after'))))
    with open(os.path.join(results(), 'oldsaves-python', 'progress.txt'), encoding='utf-8') as file:
      progress = file.read()
    self.assertIn('opening selfcheck-far as it was found', progress)
    self.assertIn('opening selfcheck-gold again, as this game saved it', progress)
    self.assertIn('test 12/12 SaveTests.testC_theOneNamedIsOpen [selfcheck-gold, load 2] ... ok', progress)
    for other in ('script', 'java'):
      if other in OldSavesTests.reports:
        self.same(OldSavesTests.reports[other], report)

  def test_4_python_in_the_real_client(self) -> None:
    jar = os.path.join(ROOT, 'build', 'libs', 'unittas-%s.jar' % modVersion())
    spec = os.path.join(results(), 'specs', 'oldsaves-real.toml')
    with open(spec, 'w', encoding='utf-8') as file:
      file.write('minecraft = "1.7.10"\nloader = { forge = "10.13.4.1614" }\nclient = "real"\n'
                 'build = "%s -p %s --console=plain remapJar"\nmods = ["%s"]\nlibraries = ["%s"]\nprobe = "%s"\n'
                 'game = "%s"\n' % (os.path.join(ROOT, 'gradlew'), ROOT, jar,
                                    os.path.join(ROOT, 'run', 'oldsaves', 'mods', 'unimixins-1.7.10-0.3.1.jar'), jar,
                                    os.path.join(ROOT, 'run', 'release')))
    report = self.unittas('oldsaves-real', 'selfsuite.oldsaves', spec=spec)
    self.assertEqual(self.expected(), self.lines(report))


if __name__ == '__main__':
  unittest.main()

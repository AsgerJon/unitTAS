"""
Step 7 of phase 3 (SPEC.md section 9.3): unitTAS's own self suites in Python (tests/selfsuite), twins of the Java
ones by the same names.
- In the development client: green, red and a suite that isn't there on one Run, the report checked by
  bin/self_red_check.py --python. Its table is the Java run's, less what Python doesn't twin.
- In the real client (unitTAS's release jar from an instance spec): the green suite, every line ok.

  python -m unittas.selftest test_selfsuites.      (through the watcher: "probe test_selfsuites.")
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import unittest

from probegame import READY_SECONDS, ROOT, modVersion, results
from unittas.api import Game
from unittas.dev import DevGame
from unittas.launcher import Sources
from unittas.mappings import Mappings
from unittas.run import Run, runSuites
from unittas.spec import InstanceSpec
from unittas.specgame import gameFor

#  the self suites live beside the probe's tests, not among them
sys.path.insert(0, os.path.join(ROOT, 'python', 'tests'))
RESULT = re.compile(r'^(\S+) \.\.\. (.+?) \(\d+\.\d s\)$')


class SelfSuitesTests(unittest.TestCase):

  def run_(self, launched, suites: list) -> str:
    """The suites on a Run of the launched game; its report's path."""
    connection = launched.start()
    connection.events.waitFor(lambda event: event.get('event') == 'ready', READY_SECONDS)
    run = Run(Game(connection, mappings=Mappings.load(Sources(gradleHome=os.path.join(ROOT, '.gradle-home')))),
              launched.gameDir, os.path.join(launched.results, 'run'), stop=launched.stop)
    try:
      run.begin()
      runSuites(run, suites, stream=io.StringIO(), verbosity=2)
    finally:
      report = run.finish()
    return report

  def test_1_in_the_development_client(self) -> None:
    report = self.run_(DevGame(ROOT, results(), 'selfsuites-dev'),
                       ['selfsuite.green', 'selfsuite.red', 'selfsuite.nosuch'])
    checked = subprocess.run([sys.executable, '-I', os.path.join(ROOT, 'bin', 'self_red_check.py'), '--python', report],
                             capture_output=True, text=True)
    self.assertEqual(0, checked.returncode, checked.stdout + checked.stderr)

  def test_2_in_the_real_client(self) -> None:
    jar = os.path.join(ROOT, 'build', 'libs', 'unittas-%s.jar' % modVersion())
    folder = os.path.join(results(), 'specs')
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, 'self-real.toml')
    with open(path, 'w', encoding='utf-8') as file:
      file.write('minecraft = "1.7.10"\nloader = { forge = "10.13.4.1614" }\nclient = "real"\n'
                 'build = "%s -p %s --console=plain remapJar"\nmods = ["%s"]\nlibraries = ["%s"]\nprobe = "%s"\n'
                 'game = "%s"\n' % (os.path.join(ROOT, 'gradlew'), ROOT, jar,
                                    os.path.join(ROOT, 'run', 'oldsaves', 'mods', 'unimixins-1.7.10-0.3.1.jar'), jar,
                                    os.path.join(ROOT, 'run', 'release')))
    os.environ['UNITTAS_GRADLE_HOME'] = os.environ['GRADLE_USER_HOME'] = os.path.join(ROOT, '.gradle-home')
    try:
      report = self.run_(gameFor(InstanceSpec.read(path), results(), 'selfsuites-real'), ['selfsuite.green'])
    finally:
      os.environ.pop('UNITTAS_GRADLE_HOME', None)
      os.environ.pop('GRADLE_USER_HOME', None)
    with open(report, encoding='utf-8') as file:
      lines = file.read().split('\n')
    outcomes = [(found.group(1), found.group(2)) for found in map(RESULT.match, lines) if found]
    self.assertEqual(15, len(outcomes), outcomes)
    self.assertEqual([], [each for each in outcomes if each[1] != 'ok'], '\n'.join(lines))
    self.assertEqual('OK', [line for line in lines if line][-1])


if __name__ == '__main__':
  unittest.main()

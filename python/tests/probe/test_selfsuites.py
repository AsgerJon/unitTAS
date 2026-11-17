"""
Step 7 of phase 3 (SPEC.md section 9.3): unitTAS's own self suites in Python (tests/selfsuite), twins of the Java
ones by the same names.
- In the development client: green, red and a suite that isn't there on one Run, the report checked by
  bin/self_red_check.py --python. Its table is the Java run's, less what Python doesn't twin.
- In the real client (unitTAS's release jar from an instance spec): the green suite, every line ok.
- On 26.3, 1.21.1 and 1.20.1 (SPEC.md 19.7 steps 4, 6d and 6e): 'unittas run' as a user runs it (python -m unittas,
  a process of its own) with a Fabric spec of the port's version (the mod's loader), the probe the version's agent jar
  beside it: the green suite, every line ok.

  python -m unittas.selftest test_selfsuites.      (through the watcher: "probe test_selfsuites.")
  python -m unittas.selftest test_selfsuites on 26.3-fabric      ("probe test_selfsuites on 26.3-fabric")
  python -m unittas.selftest test_selfsuites on 1.21.1-fabric    ("probe test_selfsuites on 1.21.1-fabric")
  python -m unittas.selftest test_selfsuites on 1.20.1-fabric    ("probe test_selfsuites on 1.20.1-fabric")
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

from agentgame import buildAgent
from ports import V1_7_10, V1_20_1, V1_21_1, V26_3, onlyOn, version
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


def outcomes(report: str) -> tuple:
  """A run's report: its lines, and (test, outcome) for each test's line."""
  with open(report, encoding='utf-8') as file:
    lines = file.read().split('\n')
  return lines, [(found.group(1), found.group(2)) for found in map(RESULT.match, lines) if found]


@onlyOn(V1_7_10, why="1.7.10's development and real clients; the agent's versions' are SelfSuitesAgentTests'")
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
                 'build = "%s -p %s --no-daemon --console=plain remapJar"\nmods = ["%s"]\nlibraries = ["%s"]\nprobe = "%s"\n'
                 'game = "%s"\n' % (os.path.join(ROOT, 'gradlew'), ROOT, jar,
                                    os.path.join(ROOT, 'run', 'oldsaves', 'mods', 'unimixins-1.7.10-0.3.1.jar'), jar,
                                    os.path.join(ROOT, 'run', 'release')))
    os.environ['UNITTAS_GRADLE_HOME'] = os.environ['GRADLE_USER_HOME'] = os.path.join(ROOT, '.gradle-home')
    try:
      report = self.run_(gameFor(InstanceSpec.read(path), results(), 'selfsuites-real'), ['selfsuite.green'])
    finally:
      os.environ.pop('UNITTAS_GRADLE_HOME', None)
      os.environ.pop('GRADLE_USER_HOME', None)
    lines, ended = outcomes(report)
    # the green suite's tests (selfsuite/green.py), WorldTerrainTests' two and WorldTerrainThenFlatTests' one among them
    self.assertEqual(18, len(ended), ended)
    self.assertEqual([], [each for each in ended if each[1] != 'ok'], '\n'.join(lines))
    self.assertEqual('OK', [line for line in lines if line][-1])


@onlyOn(V26_3, V1_21_1, V1_20_1, why="the agent's versions' real client from a spec; 1.7.10's are SelfSuitesTests'")
class SelfSuitesAgentTests(unittest.TestCase):

  def test_1_unittas_run_on_a_spec_of_the_version(self) -> None:
    minecraft = version()
    jar = buildAgent(os.path.join(results(), 'agent-build', 'build.log'), minecraft)
    folder = os.path.join(results(), 'specs')
    os.makedirs(folder, exist_ok=True)
    spec = os.path.join(folder, 'self-%s.toml' % minecraft)
    with open(spec, 'w', encoding='utf-8') as file:
      # no "java": the launcher finds one the version asks for (25, 21, 17), as a user's spec would leave it
      file.write('minecraft = "%s"\nloader = { fabric = "0.20.1" }\nclient = "real"\nprobe = "%s"\ngame = "%s"\n' % (
        minecraft, jar, os.path.join(ROOT, 'run', 'fabric-%s-spec' % minecraft)))
    run = os.path.join(results(), 'self-%s' % minecraft)
    process = subprocess.Popen([sys.executable, '-m', 'unittas', 'run', 'selfsuite.green', '--instance', spec,
                                '--results', run], cwd=os.path.join(ROOT, 'python', 'tests'),
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    said, _ = process.communicate(timeout=READY_SECONDS + 900)
    with open(os.path.join(results(), 'self-%s-said.txt' % minecraft), 'w', encoding='utf-8') as file:
      file.write(said)
    self.assertEqual(0, process.returncode, said)
    lines, ended = outcomes(os.path.join(run, 'report.txt'))
    self.assertEqual(18, len(ended), ended)
    self.assertEqual([], [each for each in ended if each[1] != 'ok'], '\n'.join(lines))
    self.assertEqual('OK', [line for line in lines if line][-1])


if __name__ == '__main__':
  unittest.main()

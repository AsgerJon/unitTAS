"""
Tests of the GitHub workflows' shell steps: no `${{ ... }}` expression is pasted into a `run:` script. GitHub expands
such an expression into the script's text before the shell reads it, so a value with shell syntax in it would run.
What a script needs comes from the environment instead: GitHub's own variables (`$GITHUB_REF`, `$GITHUB_REPOSITORY`),
or an `env:` entry the step sets, always quoted.

  python -m unittest discover -s bin/tests
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import glob
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOWS = os.path.join(ROOT, '.github', 'workflows')
RUN = re.compile(r'^(\s*)(?:- )?run:\s*(.*)$')


def run_scripts(path: str) -> list:
  """Each `run:` step's script in the workflow, as (line number, text) pairs: a block's lines, or the one line."""
  with open(path, encoding='utf-8') as file:
    lines = file.read().splitlines()
  found = []
  index = 0
  while index < len(lines):
    match = RUN.match(lines[index])
    index += 1
    if not match:
      continue
    indent, rest = len(match.group(1)), match.group(2).strip()
    if rest[:1] not in ('|', '>'):
      found.append((index, rest))
      continue
    while index < len(lines):
      line = lines[index]
      if line.strip() and len(line) - len(line.lstrip()) <= indent:
        break
      index += 1
      found.append((index, line))
  return found


class WorkflowTests(unittest.TestCase):

  def test_there_are_workflows(self) -> None:
    self.assertTrue(glob.glob(os.path.join(WORKFLOWS, '*.yml')), 'no workflows found in ' + WORKFLOWS)

  def test_finds_block_and_single_line_scripts(self) -> None:
    for path in glob.glob(os.path.join(WORKFLOWS, '*.yml')):
      with self.subTest(workflow=os.path.basename(path)):
        self.assertTrue(run_scripts(path), 'no run: step found in ' + path)

  def test_no_expression_inside_a_script(self) -> None:
    pasted = []
    for path in sorted(glob.glob(os.path.join(WORKFLOWS, '*.yml'))):
      for number, text in run_scripts(path):
        if '${{' in text:
          pasted.append('%s:%d: %s' % (os.path.basename(path), number, text.strip()))
    self.assertEqual([], pasted, 'expressions pasted into shell scripts (use the environment):\n' + '\n'.join(pasted))


class FabricProbeReleasedTests(unittest.TestCase):
  """
  Every release button builds the 26.3 Fabric probe too (SPEC.md 12, D6): fabric/ with its own wrapper on Java 25,
  while Java 21 stays the default (the root's Gradle 8.10.2 doesn't run on 25), and the release carries its jar
  beside the 1.7.10 ones, by a name with the version in it.
  """

  JAR = 'unittas-probe-26.3-fabric'

  def workflows(self) -> list:
    out = []
    for path in sorted(glob.glob(os.path.join(WORKFLOWS, '*.yml'))):
      with open(path, encoding='utf-8') as file:
        out.append((os.path.basename(path), file.read()))
    return out

  def test_java_25_beside_21_which_stays_the_default(self) -> None:
    for name, text in self.workflows():
      for versions in re.findall(r'java-version: \|\n((?:\s+\d+\n)+)', text):
        listed = versions.split()
        self.assertIn('25', listed, name)
        self.assertEqual('21', listed[-1], '%s: the last one listed is the default JAVA_HOME' % name)

  def test_fabric_is_built_on_java_25(self) -> None:
    for name, text in self.workflows():
      self.assertEqual(2, text.count('working-directory: fabric'), '%s: in the test job and the publish job' % name)
      self.assertEqual(2, text.count('JAVA_HOME: ${{ env.JAVA_HOME_25_X64 }}'), name)

  def test_the_release_carries_its_jar(self) -> None:
    for name, text in self.workflows():
      self.assertIn('test -f fabric/build/libs/%s.jar' % self.JAR, text, name)
      self.assertIn('build/libs/%s-${{ env.VERSION_INFO }}.jar' % self.JAR, text, '%s: kept for the release' % name)
      self.assertIn('"jars/%s-$VERSION_INFO.jar"' % self.JAR, text, '%s: in the release' % name)


if __name__ == '__main__':
  unittest.main()

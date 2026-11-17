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
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOWS = os.path.join(ROOT, '.github', 'workflows')
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, os.path.join(ROOT, 'bin', 'release_tooling'))
sys.path.insert(0, os.path.join(ROOT, 'python', 'src'))

from build_agent import VERSIONS  # noqa: E402
from release_state import BUTTONS, buttonKind  # noqa: E402
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


class ButtonsTests(unittest.TestCase):
  """
  The release buttons are WorkToy's (bin/release_tooling/release_state.py): nine, a level and a kind each, every one a
  workflow of its name. Each decides its press in its first job from VERSION and, where the press needs one, its own
  safety (safety_check.py BUTTON), locks every safety, pushes the lock, tests the release tooling and only then fails
  or goes on; names its version and advances the counters by its own name; and makes a pre-release (dev, rc) or the
  latest release (lts). unitTAS's own stay: the version commit and its tag pushed together or not at all, the release
  a job of its own, no expression pasted into a script.
  """

  def text(self, button: str) -> str:
    with open(os.path.join(WORKFLOWS, button + '.yml'), encoding='utf-8') as file:
      return file.read()

  def test_one_workflow_for_each_button(self) -> None:
    names = sorted(os.path.basename(path)[:-len('.yml')] for path in glob.glob(os.path.join(WORKFLOWS, '*.yml')))
    self.assertEqual(sorted(BUTTONS), names)

  def test_each_decides_by_its_own_name(self) -> None:
    for button in BUTTONS:
      with self.subTest(button=button):
        text = self.text(button)
        self.assertIn('name: %s\n' % button, text)
        self.assertIn('python bin/release_tooling/safety_check.py %s SAFETY_VERDICT' % button, text)
        self.assertIn('python bin/release_tooling/version_get.py %s VERSION_INFO' % button, text)
        self.assertIn('python bin/release_tooling/version_bump.py %s\n' % button, text)
        self.assertIn('git diff --cached --quiet || git commit -m "%s: safeties locked, verdict ${SAFETY_VERDICT}"'
                      % button, text)

  def test_the_lock_is_pushed_and_the_tooling_tested_before_the_verdict(self) -> None:
    for button in BUTTONS:
      with self.subTest(button=button):
        text = self.text(button)
        lock = text.index('git push origin "HEAD:$GITHUB_REF"')
        tested = text.index('python -B -m unittest discover -s tests -t .')
        enforced = text.index('if [ "$SAFETY_VERDICT" != "ALLOW" ]; then')
        self.assertLess(lock, tested)
        self.assertLess(tested, enforced)
        self.assertIn('working-directory: bin/release_tooling', text)

  def test_the_version_commit_and_its_tag_go_together(self) -> None:
    words = {'dev': 'dev', 'rc': 'rc', 'lts': 'LTS'}
    for button in BUTTONS:
      with self.subTest(button=button):
        text = self.text(button)
        self.assertIn('git commit -m "%s $VERSION_INFO"' % words[buttonKind(button)], text)
        self.assertIn('git push --atomic origin "HEAD:$GITHUB_REF" "refs/tags/$VERSION_INFO"', text)

  def test_dev_and_rc_are_pre_releases_lts_the_latest(self) -> None:
    for button in BUTTONS:
      with self.subTest(button=button):
        text = self.text(button)
        kind = buttonKind(button)
        if kind == 'lts':
          self.assertIn('--title "$VERSION_INFO" --latest --generate-notes', text)
          self.assertNotIn('--prerelease', text)
        else:
          self.assertIn('--title "%s $VERSION_INFO" --prerelease --generate-notes' % kind, text)


class ProbeReleasedTests(unittest.TestCase):
  """
  Every release button builds each version's probe too (SPEC.md 12 D6, 19.7 steps 5 and 6f): the loader-free agent of
  every version bin/build_agent.py knows (its VERSIONS: none left out as one is added), by Java 25's javac (no Gradle,
  no fabric/ any more), while Java 21 stays the default (the root's Gradle 8.10.2 doesn't run on 25), and the release
  carries each one's jar beside the 1.7.10 ones, by a name with the version in it.
  """

  BUILD = 'python bin/build_agent.py --java25 "$JAVA_HOME_25_X64" --minecraft %s'

  def workflows(self) -> list:
    """Each workflow's text, a script's continued lines (a backslash at the end) joined."""
    out = []
    for path in sorted(glob.glob(os.path.join(WORKFLOWS, '*.yml'))):
      with open(path, encoding='utf-8') as file:
        out.append((os.path.basename(path), re.sub(r' \\\n\s*', ' ', file.read())))
    return out

  def test_java_25_beside_21_which_stays_the_default(self) -> None:
    for name, text in self.workflows():
      for versions in re.findall(r'java-version: \|\n((?:\s+\d+\n)+)', text):
        listed = versions.split()
        self.assertIn('25', listed, name)
        self.assertEqual('21', listed[-1], '%s: the last one listed is the default JAVA_HOME' % name)

  def test_each_version_s_agent_is_built_on_java_25(self) -> None:
    for name, text in self.workflows():
      self.assertEqual(2 * len(VERSIONS), text.count('python bin/build_agent.py --java25 "$JAVA_HOME_25_X64"'), name)
      for minecraft in VERSIONS:
        with self.subTest(workflow=name, minecraft=minecraft):
          self.assertEqual(2, text.count(self.BUILD % minecraft + '\n') + text.count(self.BUILD % minecraft + ' '),
                           '%s: in the test job and the publish job' % name)
      self.assertNotIn('working-directory: fabric', text, '%s: fabric/ is gone' % name)

  def test_the_release_carries_each_version_s_jar(self) -> None:
    for name, text in self.workflows():
      for minecraft in VERSIONS:
        with self.subTest(workflow=name, minecraft=minecraft):
          jar = 'unittas-probe-%s' % minecraft
          self.assertIn(self.BUILD % minecraft + ' --out "build/libs/%s-$VERSION_INFO.jar"' % jar, text, name)
          self.assertIn('test -f "build/libs/%s-$VERSION_INFO.jar"' % jar, text, '%s: its jar there' % name)
          self.assertIn('build/libs/%s-${{ env.VERSION_INFO }}.jar' % jar, text, '%s: kept for the release' % name)
          self.assertIn('"jars/%s-$VERSION_INFO.jar"' % jar, text, '%s: in the release' % name)
      self.assertNotIn('26.3-fabric', text, name)


if __name__ == '__main__':
  unittest.main()

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


if __name__ == '__main__':
  unittest.main()

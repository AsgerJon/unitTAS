"""
TestVersionFile tests how the release state reads and writes 'VERSION'.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os

import release_state

from . import ReleaseToolingTest, TOOLING_VERSION


class TestVersionFile(ReleaseToolingTest):
  """
  'VERSION' holds five counters and the locked level. Reading it must give
  the counters as numbers and the level as text, and refuse a file the
  state machine could never have written, since a press decided from such
  a file would publish a wrong name. Writing must keep the explanation at
  the head of the file.
  """

  def assertRefusedFile(self, text: str, message: str) -> None:
    self.writeText(self.versionPath, text)
    with self.assertRaises(RuntimeError) as context:
      release_state.readVersion(self.versionPath)
    self.assertEqual(str(context.exception), message)

  def test_read(self) -> None:
    self.writeVersion(level='minor', rc=1, dev=3)
    info = release_state.readVersion(self.versionPath)
    self.assertEqual(info, dict(major=1, minor=1, micro=1, rc=1, dev=3,
                                level='minor'))

  def test_write_keeps_the_head(self) -> None:
    text = str.join('\n', [
      '#  The head of the file.',
      '#',
      '#  Second paragraph.',
      'MAJOR=1', 'MINOR=1', 'MICRO=1', 'RC=0', 'DEV=0', 'LEVEL=none', '',
    ])
    self.writeText(self.versionPath, text)
    info = release_state.readVersion(self.versionPath)
    info.update(level='minor', dev=1)
    release_state.writeVersion(self.versionPath, info)
    self.assertEqual(self.readText(self.versionPath), str.join('\n', [
      '#  The head of the file.',
      '#',
      '#  Second paragraph.',
      'MAJOR=1', 'MINOR=1', 'MICRO=1', 'RC=0', 'DEV=1', 'LEVEL=minor', '',
    ]))

  def test_write_refuses_an_impossible_state(self) -> None:
    info = release_state.readVersion(self.versionPath)
    info.update(rc=1)
    with self.assertRaises(RuntimeError) as context:
      release_state.writeVersion(self.versionPath, info)
    self.assertIn('With LEVEL=none no cycle is open', str(context.exception))
    self.assertEqual(self.readCounters()['rc'], 0)

  def test_refused_files(self) -> None:
    lines = 'MAJOR=1\nMINOR=1\nMICRO=1\nRC=0\nDEV=0\n'
    self.assertRefusedFile(lines, """VERSION lacks the line for LEVEL.""")
    self.assertRefusedFile(lines + 'LEVEL=none\nPATCH=3\n',
                           """VERSION holds an unknown line: 'PATCH=3'.""")
    self.assertRefusedFile(lines + 'LEVEL=a=b\n',
                           """VERSION holds more than one '=' in the line:
'LEVEL=a=b'.""".replace('\n', ' '))
    self.assertRefusedFile(lines + 'LEVEL=mini\n',
                           """LEVEL must be none, micro, minor or major, but
VERSION reads LEVEL=mini.""".replace('\n', ' '))
    self.assertRefusedFile(lines.replace('DEV=0', 'DEV=x') + 'LEVEL=none\n',
                           """The counter DEV in VERSION is no whole number:
'x'.""".replace('\n', ' '))
    self.assertRefusedFile(lines.replace('RC=0', 'RC=-1') + 'LEVEL=none\n',
                           """The counter RC in VERSION is below 0:
-1.""".replace('\n', ' '))
    self.assertRefusedFile(
        lines.replace('MICRO=1', 'MICRO=0') + 'LEVEL=none\n',
        """MICRO holds the next micro version after the last full release,
so it is at least 1, but VERSION reads MICRO=0.""".replace('\n', ' '))
    self.assertRefusedFile(
        lines.replace('RC=0', 'RC=1') + 'LEVEL=none\n',
        """With LEVEL=none no cycle is open, so RC and DEV are 0, but
VERSION reads RC=1 DEV=0.""".replace('\n', ' '))
    self.assertRefusedFile(
        lines + 'LEVEL=minor\n',
        """With LEVEL=minor a dev cycle was opened, so DEV is at least 1,
but VERSION reads DEV=0.""".replace('\n', ' '))

  def test_lines_skipped(self) -> None:
    self.writeText(self.versionPath, str.join('\n', [
      '#  a comment', '', '   ', 'not a setting', 'MAJOR = 1', 'MINOR=1',
      'MICRO=1', 'RC=0', 'DEV=0', 'level = none', '',
    ]))
    info = release_state.readVersion(self.versionPath)
    self.assertEqual(info, dict(major=1, minor=1, micro=1, rc=0, dev=0,
                                level='none'))

  def test_the_real_version_file_reads(self) -> None:
    #  Read only: the file of the repository is never written by a test.
    info = release_state.readVersion(TOOLING_VERSION)
    self.assertEqual(sorted(info),
                     ['dev', 'level', 'major', 'micro', 'minor', 'rc'])
    self.assertTrue(os.path.isfile(TOOLING_VERSION))

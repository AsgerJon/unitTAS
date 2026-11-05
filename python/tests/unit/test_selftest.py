"""
The probe's own test runs (unittas.selftest), as their terminal and report show them: each test numbered against
the run's total, 'test N/M Class.method ... outcome', as the Java runner's progress has it.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import unittest

from unittas.selftest import runNumbered


class NumberedTests(unittest.TestCase):

  def test_each_line_numbered_against_the_total(self) -> None:
    class SampleTests(unittest.TestCase):  # made here, so discovery doesn't take it for tests of its own

      def test_a(self) -> None:
        pass

      def test_b(self) -> None:
        self.fail('on purpose')

      @unittest.skip('not today')
      def test_c(self) -> None:
        pass

    stream = io.StringIO()
    result = runNumbered(unittest.TestLoader().loadTestsFromTestCase(SampleTests), stream)
    text = stream.getvalue()
    self.assertEqual(3, result.testsRun)
    for line in ('test 1/3 SampleTests.test_a ... ok', 'test 2/3 SampleTests.test_b ... FAIL',
                 "test 3/3 SampleTests.test_c ... skipped 'not today'", 'FAIL: test 2/3 SampleTests.test_b'):
      self.assertIn(line + '\n', text)


if __name__ == '__main__':
  unittest.main()

"""
The probe's own test runs (unittas.selftest), as their terminal and report show them: each test numbered against
the run's total, 'test N/M Class.method ... outcome', as the Java runner's progress has it. A run names the port its
games are (SPEC.md 19.7): '[filter] [on PORT]', as words or as the one line the watcher passes.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import io
import unittest

from unittas.selftest import PORTS, parseArgs, runNumbered


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



class PortTests(unittest.TestCase):

  def test_1_7_10_unless_named(self) -> None:
    self.assertEqual(('', '1.7.10-forge'), parseArgs([]))
    self.assertEqual(('test_values', '1.7.10-forge'), parseArgs(['test_values']))

  def test_named_as_words_or_one_line(self) -> None:
    self.assertEqual(('test_values', '26.3-fabric'), parseArgs(['test_values', 'on', '26.3-fabric']))
    self.assertEqual(('test_values', '26.3-fabric'), parseArgs(['test_values on 26.3-fabric']))
    self.assertEqual(('', '26.3-fabric'), parseArgs(['on 26.3-fabric']))
    self.assertEqual(('1.7.10-forge', '26.3-fabric', '26.3'), PORTS)
    self.assertEqual(('test_agent', '26.3'), parseArgs(['test_agent on 26.3']), 'vanilla 26.3, the probe an agent')

  def test_mistakes_refused(self) -> None:
    for argv, said in ((['on 1.12.2-forge'], "no port '1.12.2-forge'"), (['test_values on'], "'on' names a port"),
                       (['a b'], 'one filter at most')):
      with self.subTest(argv=argv):
        with self.assertRaises(ValueError) as raised:
          parseArgs(argv)
        self.assertIn(said, str(raised.exception))


if __name__ == '__main__':
  unittest.main()

"""
The probe's own tests in the game: 'python -m unittas.selftest [filter]
[on PORT]' from the repository's root, as the watcher's 'probe' request
runs it. The tests are python/tests/probe; each class starts the game it
needs, of the run's port (1.7.10 Forge's development client unless the
run names another: SPEC.md 19.7), which UNITTAS_PROBE_PORT tells them. The report is unittest's own, each test
numbered as the Java runner's progress has it (test 3/144 Class.method
... ok), written to
'unittas-results/<time>/report.txt' as it runs and ending in OK or FAILED,
as the Java runner's does; the exit code is 0 only for OK.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import sys
import time
import unittest

ROOT_MARKER = 'settings.gradle'
TESTS = os.path.join('python', 'tests', 'probe')
#  The ports the probe's tests run against, each a version and what runs it: 1.7.10's development client with
#  Forge; 26.3 with Fabric Loader; 26.3 as Mojang ships it, the probe a Java agent (SPEC.md 19.7 step 5); 1.21.1 as
#  Mojang ships it (obfuscated) and with Fabric Loader (intermediary's names: steps 6c and 6d); 1.20.1 the same
#  (step 6e); 1.21.1 with NeoForge (Mojang's names, its installer's: step 7)
PORTS = ('1.7.10-forge', '26.3-fabric', '26.3', '1.21.1', '1.21.1-fabric', '1.20.1', '1.20.1-fabric',
         '1.21.1-neoforge')


def parseArgs(argv: list) -> tuple:
  """
  The run's filter and port from its arguments, '[filter] [on PORT]', as
  words or as one line (the watcher passes its request's rest as one):
  (filter, port), '' for no filter, 1.7.10 Forge for no port. ValueError
  for a port that isn't one, an 'on' naming none, or two filters.
  """
  words = ' '.join(argv).split()
  port = PORTS[0]
  if 'on' in words:
    at = words.index('on')
    if at + 1 >= len(words):
      raise ValueError("'on' names a port: on %s" % ' | '.join(PORTS))
    port = words[at + 1]
    del words[at:at + 2]
  if port not in PORTS:
    raise ValueError('no port %r: the ports are %s' % (port, ', '.join(PORTS)))
  if len(words) > 1:
    raise ValueError('one filter at most, not %s' % ' '.join(words))
  return (words[0] if words else ''), port


class NumberedResult(unittest.TextTestResult):
  """
  unittest's own lines, each test numbered against the run's total as the
  Java runner's progress has it: 'test 69/420 Class.method ... ok'.
  """

  total = 0

  def __init__(self, *args, **kwargs) -> None:
    super().__init__(*args, **kwargs)
    self.labels = {}

  def startTest(self, test: unittest.TestCase) -> None:
    self.labels[test] = 'test %d/%d %s.%s' % (self.testsRun + 1, self.total, type(test).__name__,
                                             getattr(test, '_testMethodName', str(test)))
    super().startTest(test)

  def getDescription(self, test: unittest.TestCase) -> str:
    return self.labels.get(test) or super().getDescription(test)


def runNumbered(suite: unittest.TestSuite, stream) -> unittest.TestResult:
  """The suite run as the probe's tests run, its lines numbered (NumberedResult)."""
  result = type('BoundNumberedResult', (NumberedResult,), {'total': suite.countTestCases()})
  return unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=result).run(suite)


class _Both:
  """A stream writing to the report and to the terminal at once."""

  def __init__(self, *streams) -> None:
    self.streams = streams

  def write(self, text: str) -> None:
    for stream in self.streams:
      stream.write(text)
      stream.flush()

  def flush(self) -> None:
    for stream in self.streams:
      stream.flush()


def main(argv: list) -> int:
  root = os.getcwd()
  if not os.path.isfile(os.path.join(root, ROOT_MARKER)) or not os.path.isdir(os.path.join(root, TESTS)):
    print('unittas.selftest: run from unitTAS\'s root (no %s or %s here)' % (ROOT_MARKER, TESTS), file=sys.stderr)
    return 2
  try:
    wanted, port = parseArgs(argv)
  except ValueError as error:
    print('unittas.selftest: %s' % error, file=sys.stderr)
    return 2
  stamp = os.environ.get('UNITTAS_STAMP') or time.strftime('%Y-%m-%d_%H-%M-%S')
  results = os.path.join(root, 'unittas-results', stamp)
  os.makedirs(results, exist_ok=True)
  latest = os.path.join(root, 'unittas-results', 'latest')
  if os.path.islink(latest) or not os.path.exists(latest):
    if os.path.lexists(latest):
      os.remove(latest)
    os.symlink(stamp, latest)
  os.environ['UNITTAS_RESULTS_ROOT'] = results
  os.environ['UNITTAS_PROBE_PORT'] = port
  loader = unittest.TestLoader()
  if wanted:
    loader.testNamePatterns = ['*%s*' % wanted]
  suite = loader.discover(os.path.join(root, TESTS), top_level_dir=os.path.join(root, TESTS))
  with open(os.path.join(results, 'report.txt'), 'w', encoding='utf-8') as report:
    stream = _Both(report, sys.stdout)
    stream.write('unitTAS probe tests, %s%s, on %s\n\n' % (time.strftime('%Y-%m-%d %H:%M:%S'),
                                                           ', only tests matching %r' % wanted if wanted else '', port))
    result = runNumbered(suite, stream)
  if result.testsRun == 0:
    print('unittas.selftest: no test matched', file=sys.stderr)
    return 1
  return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))

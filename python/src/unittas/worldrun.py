"""
The run's part of worlds (SPEC.md 17.8): which world a test runs in, and
a class's tests grouped by world, so each world is entered once.

- worldOf: a test's world, by its name along the class's MRO.
- orderByWorld: a class's test names, grouped by world.
- orderTests: a suite's tests, each class's grouped by world.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from typing import TYPE_CHECKING

from ._test_world import World

if TYPE_CHECKING:  # pragma: no cover
  from typing import Optional, Sequence


def worldOf(cls: type, name: str) -> Optional[World]:
  """
  The world the test 'name' of 'cls' runs in: along the MRO, nearest
  first, the first class whose body placed a World that decorated the
  name. That's the order Python finds the method in, so an undecorated
  override keeps its base's world, and a world placed in a subclass that
  decorates its override moves the test there.

  Parameters
  ----------
  cls : type
    The test class.
  name : str
    The test method's name.

  Returns
  -------
  Optional[World]
    The test's world, or None: the class's own world, or the run's.
  """
  for klass in cls.__mro__:
    for value in vars(klass).values():
      if not isinstance(value, World):
        continue
      if value.getFieldOwner() is klass and name in value.getDecorated():
        return value
  return None


def orderByWorld(cls: type, names: Sequence[str]) -> list:
  """
  The test names of 'cls' grouped by world: the undecorated first, then
  each world's in the order its first test comes, each group in the order
  given. A class without worlds keeps the order given.

  Parameters
  ----------
  cls : type
    The test class.
  names : Sequence[str]
    Its test names, in unittest's order.

  Returns
  -------
  list
    The same names, grouped.
  """
  plain = []
  groups = {}
  for name in names:
    world = worldOf(cls, name)
    if world is None:
      plain.append(name)
    else:
      groups.setdefault(id(world), []).append(name)
  out = list(plain)
  for group in groups.values():
    out.extend(group)
  return out


def orderTests(tests: Sequence) -> list:
  """
  A suite's tests, each run of one class's tests grouped by world as
  orderByWorld groups names: the undecorated first, then each world's in
  the order its first test comes. Anything else keeps its place.

  Parameters
  ----------
  tests : Sequence
    The tests, flat, in the order unittest loaded them.

  Returns
  -------
  list
    The same tests, grouped.
  """
  out = []
  block = []

  def flush() -> None:
    ranks = {}
    keyed = []
    for index, test in enumerate(block):
      name = getattr(test, '_testMethodName', '')
      world = worldOf(type(test), name)
      rank = 0 if world is None else ranks.setdefault(id(world),
                                                      len(ranks) + 1)
      keyed.append((rank, index, test))
    out.extend(test for _, _, test in sorted(keyed, key=lambda e: e[:2]))
    del block[:]

  for test in tests:
    if block and type(block[0]) is not type(test):
      flush()
    block.append(test)
  if block:
    flush()
  return out

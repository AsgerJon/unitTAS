"""
Worlds as classes (SPEC.md 17.3, 17.8), without a game: a World placed in
a class body decorates its tests and checks them once, when it's placed;
the run finds a test's world along the class's MRO and groups a class's
tests by world; on a fake game, the run enters each test's world, made
for it with its setUp run once, and leaves it for another. The fixtures
are plain classes, so unittest finds no tests in them.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import unittest

from worktoy.desc import FixBox

from test_run import FakeRun
from test_values import PLAYER
from unittas._test_world import World
from unittas.values import BlockPos, Vec3
from unittas.worldrun import orderByWorld, worldOf


class VillagePlains(World):
  """A seeded world, as a test author declares one."""

  seed = FixBox[int](8675309)


class Arena(World):
  """A world whose tests each enter it as its setUp left it."""

  fresh = FixBox[bool](True)


class WorldTests(unittest.TestCase):
  """A World decorates in the class body and checks itself once."""

  def test_decorating_returns_the_method(self) -> None:
    """The method comes back as received; its name is recorded."""
    plains = VillagePlains()

    def test_a(self) -> None:
      pass

    def test_b(self) -> None:
      pass

    self.assertIs(test_a, plains(test_a))
    self.assertIs(test_b, plains(test_b))
    self.assertEqual(('test_a', 'test_b'), plains.getDecorated())

  def test_placed_once_in_its_class(self) -> None:
    """The placement is the class body's: its owner and name."""

    class Base:
      plains = VillagePlains()

      @plains
      def test_a(self) -> None:
        pass

    world = vars(Base)['plains']
    self.assertIs(Base, world.getFieldOwner())
    self.assertEqual('plains', world.getFieldName())
    self.assertEqual(('test_a',), world.getDecorated())

  def test_a_test_redefined_after_decoration_is_refused(self) -> None:
    """A decorated test redefined in the body has lost its world."""
    with self.assertRaises(TypeError) as raised:
      class Broken:
        plains = VillagePlains()

        @plains
        def test_a(self) -> None:
          pass

        def test_a(self) -> None:  # noqa: F811, the point of the test
          pass

    self.assertIn('test_a', str(raised.exception))
    self.assertIn('plains', str(raised.exception))

  def test_a_test_under_two_worlds_is_refused(self) -> None:
    """One test runs in one world."""
    with self.assertRaises(TypeError) as raised:
      class Broken:
        plains = VillagePlains()
        arena = Arena()

        @plains
        @arena
        def test_a(self) -> None:
          pass

    self.assertIn('test_a', str(raised.exception))

  def test_a_second_placement_is_refused(self) -> None:
    """In a second class, or at a second name, a World is refused."""

    class Base:
      plains = VillagePlains()

    world = vars(Base)['plains']
    with self.assertRaises(TypeError):
      class Other:
        plains = world

    #  the refusal leaves the first placement as it was
    self.assertIs(Base, world.getFieldOwner())
    self.assertEqual('plains', world.getFieldName())
    with self.assertRaises(TypeError):
      class Twice:
        plains = hills = VillagePlains()

  def test_a_decoration_after_placement_is_refused(self) -> None:
    """Nothing would check it: a subclass places a world of its own."""

    class Base:
      plains = VillagePlains()

    with self.assertRaises(TypeError) as raised:
      class Sub(Base):
        @Base.plains
        def test_b(self) -> None:
          pass

    self.assertIn('test_b', str(raised.exception))

  def test_only_a_function_is_decorated(self) -> None:
    """Anything but a plain function is refused, loudly."""
    plains = VillagePlains()
    for value in (42, staticmethod(lambda: None), 'test_a'):
      with self.subTest(value=value):
        with self.assertRaises(TypeError):
          plains(value)

  def test_a_world_in_a_multiplayer_class_is_refused(self) -> None:
    """Worlds on a server come later (SPEC.md 17.8)."""
    from unittas.testcase import MultiplayerTestCase
    with self.assertRaises(TypeError) as raised:
      class Server(MultiplayerTestCase):
        plains = VillagePlains()

    self.assertIn('Server', str(raised.exception))

  def test_options_are_the_world_classes(self) -> None:
    """Each world class's options, the base's where it says none."""
    self.assertEqual(8675309, VillagePlains().seed)
    self.assertEqual(0, Arena().seed)
    self.assertTrue(Arena().fresh)
    self.assertFalse(VillagePlains().fresh)
    self.assertEqual('', VillagePlains().save)

  def test_a_world_takes_no_arguments(self) -> None:
    """Options belong to the world's class, not to its instances."""
    with self.assertRaises(TypeError):
      VillagePlains(1234)
    with self.assertRaises(TypeError):
      VillagePlains(seed=1234)


class LookupTests(unittest.TestCase):
  """The run finds a test's world by its name along the MRO."""

  def setUp(self) -> None:
    class Base:
      plains = VillagePlains()

      @plains
      def test_a(self) -> None:
        pass

      def test_b(self) -> None:
        pass

    class Override(Base):
      def test_a(self) -> None:
        pass

    class Moved(Base):
      arena = Arena()

      @arena
      def test_a(self) -> None:
        pass

    class Grandchild(Moved):
      pass

    self.base = Base
    self.override = Override
    self.moved = Moved
    self.grandchild = Grandchild

  def test_a_decorated_test_runs_in_its_world(self) -> None:
    """The world that decorated it."""
    self.assertIs(vars(self.base)['plains'], worldOf(self.base, 'test_a'))

  def test_an_undecorated_test_has_no_world(self) -> None:
    """None: the class's own world, or the run's superflat one."""
    self.assertIsNone(worldOf(self.base, 'test_b'))
    self.assertIsNone(worldOf(self.base, 'test_missing'))

  def test_an_undecorated_override_keeps_its_bases_world(self) -> None:
    """Overriding a test doesn't move it out of its world."""
    plains = vars(self.base)['plains']
    self.assertIs(plains, worldOf(self.override, 'test_a'))

  def test_a_subclass_world_moves_its_override(self) -> None:
    """A world placed in the subclass that decorates the name wins."""
    arena = vars(self.moved)['arena']
    self.assertIs(arena, worldOf(self.moved, 'test_a'))
    self.assertIs(vars(self.base)['plains'], worldOf(self.base, 'test_a'))

  def test_a_grandchild_inherits_the_nearest_world(self) -> None:
    """Its parent's world, not its grandparent's."""
    arena = vars(self.moved)['arena']
    self.assertIs(arena, worldOf(self.grandchild, 'test_a'))

  def test_with_several_bases_the_first_in_the_mro_wins(self) -> None:
    """As Python finds the method, so the run finds its world."""

    class Left:
      plains = VillagePlains()

      @plains
      def test_x(self) -> None:
        pass

    class Right:
      arena = Arena()

      @arena
      def test_x(self) -> None:
        pass

    class Both(Left, Right):
      pass

    self.assertIs(vars(Left)['plains'], worldOf(Both, 'test_x'))

  def test_a_world_in_a_mixin_counts(self) -> None:
    """A world placed in any class of the MRO, a mixin's too."""

    class Mixin:
      plains = VillagePlains()

      @plains
      def test_m(self) -> None:
        pass

    class Tests(Mixin, unittest.TestCase):
      pass

    self.assertIs(vars(Mixin)['plains'], worldOf(Tests, 'test_m'))


class OrderTests(unittest.TestCase):
  """A class's tests grouped by world, each world entered once."""

  def test_tests_are_grouped_by_world(self) -> None:
    """Undecorated first, then each world as its first test comes."""

    class Tests:
      plains = VillagePlains()
      arena = Arena()

      @plains
      def test_a(self) -> None:
        pass

      def test_b(self) -> None:
        pass

      @arena
      def test_c(self) -> None:
        pass

      @plains
      def test_d(self) -> None:
        pass

      def test_e(self) -> None:
        pass

    names = ['test_a', 'test_b', 'test_c', 'test_d', 'test_e']
    self.assertEqual(['test_b', 'test_e', 'test_a', 'test_d', 'test_c'],
                     orderByWorld(Tests, names))

  def test_a_class_without_worlds_keeps_its_order(self) -> None:
    """Nothing to group: the order given."""

    class Tests:
      def test_b(self) -> None:
        pass

      def test_a(self) -> None:
        pass

    self.assertEqual(['test_b', 'test_a'],
                     orderByWorld(Tests, ['test_b', 'test_a']))


class EnteringTests(FakeRun, unittest.TestCase):
  """
  The run enters a test's world (Run.enterWorld): made fresh for it in a
  save folder of its own, its setUp once, its start where the game put
  the player; left when another world, or the class's own, comes next.
  """

  def setUp(self) -> None:
    FakeRun.setUp(self)
    self.spawned = [12.5, 70.0, -3.5]
    self.setUps = []
    setUps = self.setUps
    flatPlayer = self.handlers['player.get']
    created = {'world': False}
    create = self.handlers['world.create']

    def creating(args, side):
      created['world'] = args['folder'] == 'unittas-world'
      return create(args, side)

    def opening(args, side):
      created['world'] = args['folder'] == 'unittas-world'
      return {'folder': args['folder'], 'name': 'unitTAS', 'load_ms': 5}

    def player(args, side):
      if created['world']:
        return dict(PLAYER, pos=self.spawned)
      return flatPlayer(args, side)

    self.handlers['world.create'] = creating
    self.handlers['world.open'] = opening
    self.handlers['player.get'] = player

    class Plains(VillagePlains):
      def setUp(self) -> None:
        setUps.append('plains')

    class Fresh(Arena):
      def setUp(self) -> None:
        setUps.append('arena')

    class Broken(World):
      def setUp(self) -> None:
        setUps.append('broken')
        raise ValueError('setUp fails on purpose')

    class Tests:
      plains = Plains()
      arena = Fresh()
      broken = Broken()

      @plains
      def test_a(self) -> None:
        pass

      def test_b(self) -> None:
        pass

      @arena
      def test_c(self) -> None:
        pass

      @plains
      def test_d(self) -> None:
        pass

      @arena
      def test_e(self) -> None:
        pass

      @broken
      def test_f(self) -> None:
        pass

    self.tests = Tests
    self.plains = vars(Tests)['plains']
    self.arena = vars(Tests)['arena']

  def ops(self, name: str) -> list:
    """The requests of that op, their arguments, in order."""
    return [each['args'] for each in self.asked if each['op'] == name]

  def hooks(self) -> list:
    return [args['hook'] for args in self.ops('hooks.run')]

  def entered(self, world: World) -> bool:
    try:
      _ = world.start
    except RuntimeError:
      return False
    return True

  def test_a_world_is_made_for_its_first_test(self) -> None:
    """Its options, its own folder, prepared; the player's start."""
    self.run.begin()
    self.run.enterClass('Tests')
    self.run.enterWorld(self.tests, 'test_a')
    made = self.ops('world.create')[-1]
    self.assertEqual(('unittas-world', 8675309, 'default'),
                     (made['folder'], made['seed'], made['type']))
    after = [each['op'] for each in self.asked]
    after = after[len(after) - after[::-1].index('world.create'):]
    self.assertIn('world.prepare', after)
    self.assertEqual('setUpWorld', self.hooks()[-1])
    self.assertEqual(['plains'], self.setUps)
    self.assertEqual(Vec3(12.5, 70.0, -3.5), self.plains.start)
    self.assertEqual(BlockPos(0, 4, 0), self.plains.spawn)
    self.assertEqual((12.5, 70.0, -3.5), self.run.start)
    self.assertIn('plains', self.run.worldNote)
    self.assertIn('Tests', self.run.worldNote)
    self.assertIn('seed 8675309', self.run.worldNote)

  def test_its_tests_share_it_and_setUp_runs_once(self) -> None:
    """The second test of a world finds it entered: nothing is made."""
    self.run.begin()
    self.run.enterClass('Tests')
    self.run.enterWorld(self.tests, 'test_a')
    creates = len(self.ops('world.create'))
    self.run.enterWorld(self.tests, 'test_d')
    self.assertEqual(creates, len(self.ops('world.create')))
    self.assertEqual(['plains'], self.setUps)
    self.assertTrue(self.entered(self.plains))

  def test_another_world_leaves_the_first(self) -> None:
    """One world is entered at a time."""
    self.run.begin()
    self.run.enterClass('Tests')
    self.run.enterWorld(self.tests, 'test_a')
    self.run.enterWorld(self.tests, 'test_c')
    self.assertFalse(self.entered(self.plains))
    self.assertTrue(self.entered(self.arena))
    self.assertEqual(['plains', 'arena'], self.setUps)
    self.assertIn('tearDownWorld', self.hooks())

  def test_a_test_with_no_world_gets_the_class_world_back(self) -> None:
    """After a world's tests, an undecorated test: the kept world."""
    self.run.begin()
    self.run.enterClass('Tests')
    self.run.enterWorld(self.tests, 'test_a')
    self.run.enterWorld(self.tests, 'test_b')
    self.assertFalse(self.entered(self.plains))
    self.assertEqual('unittas', self.ops('world.open')[-1]['folder'])
    self.assertEqual((0.5, 4.0, 0.5), self.run.start)

  def test_a_fresh_world_is_entered_as_its_setUp_left_it(self) -> None:
    """Kept after setUp; each later test opens that copy again."""
    self.run.begin()
    self.run.enterClass('Tests')
    self.run.enterWorld(self.tests, 'test_c')
    kept = os.path.join(self.gameDir, 'unittas', 'world.setup')
    self.assertTrue(os.path.isdir(kept), 'the copy kept after setUp')
    creates = len(self.ops('world.create'))
    self.run.enterWorld(self.tests, 'test_e')
    self.assertEqual(creates, len(self.ops('world.create')))
    self.assertEqual('unittas-world', self.ops('world.open')[-1]['folder'])
    self.assertEqual(['arena'], self.setUps)
    self.assertTrue(self.entered(self.arena))
    self.assertIn('as its setUp left it', self.run.worldNote)

  def test_a_setUp_that_raises_is_raised_and_tried_again(self) -> None:
    """The test's own error; the next test of that world tries again."""
    self.run.begin()
    self.run.enterClass('Tests')
    for _ in range(2):
      with self.assertRaises(ValueError):
        self.run.enterWorld(self.tests, 'test_f')
    self.assertEqual(['broken', 'broken'], self.setUps)
    self.assertFalse(self.entered(vars(self.tests)['broken']))

  def test_the_next_class_leaves_the_world(self) -> None:
    """A class's world, or the kept one, closes the entered world."""
    self.run.begin()
    self.run.enterClass('Tests')
    self.run.enterWorld(self.tests, 'test_a')
    self.run.enterClass('NextTests')
    self.assertFalse(self.entered(self.plains))

  def test_the_run_s_finish_leaves_the_world(self) -> None:
    """A finished run holds no world entered."""
    self.run.begin()
    self.run.enterClass('Tests')
    self.run.enterWorld(self.tests, 'test_a')
    self.run.finish()
    self.assertFalse(self.entered(self.plains))

  def test_a_world_s_reads_raise_until_it_is_entered(self) -> None:
    """Outside its tests, a world has no start or spawn."""
    with self.assertRaises(RuntimeError) as raised:
      _ = self.plains.start
    self.assertIn('plains', str(raised.exception))
    with self.assertRaises(RuntimeError):
      _ = self.plains.spawn


if __name__ == '__main__':
  unittest.main()

"""
World encapsulates a minecraft world used for testing.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from types import FunctionType
from typing import TYPE_CHECKING

from worktoy.desc import Field, FixBox
from worktoy.dispatch import overload
from worktoy.mcls import BaseObject

from .values import BlockPos

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Callable

  from mcdex import MCBiomes, MCBlocks, MCStructures

  from .api import Game
  from .values import Vec3


class World(BaseObject):
  """
  A Minecraft world for tests (SPEC.md 17). Each world is a subclass, its
  options 'FixBox' fields redeclared in its body and its setup its own
  'setUp'. An instance placed in a test class's body is the world that
  class's tests run in, and it decorates them:

    class VillagePlains(World):
      seed = FixBox[int](8675309)

    class VillageTests(UnitTAS):
      plains = VillagePlains()

      @plains
      def test_a_village_near_spawn(self) -> None:
        ...

  Decorating records the method's name and returns the method as
  received, before the class exists; placing the instance then runs
  'Object.__set_name__' exactly once, and 'hookSetName' checks what was
  decorated against the owner. Which world a test of a subclass runs in
  is the run's to find, along the class's MRO (SPEC.md 17.8).
  """

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  NAMESPACE  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  #  Class Variables

  #  Fallback Variables

  #  Private Variables
  #  The test methods this world decorated, by name, as decorated
  __decorated__: dict = None
  #  The owner and name of its one placement, once placed
  __placement__: tuple = None
  #  What the run handed over on entering (the game, start, spawn), else
  #  None while the world isn't entered
  __entered__: dict = None

  #  Public Variables
  #  The world's options; kind, layers, biome and rules follow once
  #  WorldKind exists (SPEC.md 17.4)
  seed = FixBox[int](0)
  save = FixBox[str]('')
  fresh = FixBox[bool](False)

  #  Virtual Variables
  start = Field()
  spawn = Field()

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  GETTERS  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  @start.GET
  def _getStart(self) -> Vec3:
    """Where the game put the player on entering; raises if not entered."""
    return self._getEntered()['start']

  @spawn.GET
  def _getSpawn(self) -> BlockPos:
    """The world's spawn point, from the game; raises if not entered."""
    return self._getEntered()['spawn']

  def _getEntered(self) -> dict:
    """
    What the run handed over on entering.

    Raises
    ------
    RuntimeError
      The world isn't entered: it answers only in its own tests.
    """
    if self.__entered__ is None:
      infoSpec = """The world '%s' isn't entered: it answers only in the
      tests it decorates, while they run."""
      raise RuntimeError(' '.join((infoSpec % self.label()).split()))
    return self.__entered__

  def isEntered(self) -> bool:
    """Whether the run has entered this world and not left it."""
    return self.__entered__ is not None

  def label(self) -> str:
    """'Owner.name' where it's placed, else its class's name."""
    if self.__placement__ is None:
      return type(self).__name__
    owner, name = self.__placement__
    return '%s.%s' % (owner.__name__, name)

  def createArgs(self) -> dict:
    """
    world.create's arguments for this world (PROTOCOL.md): default
    terrain from its seed. Its kind, layers, biome and rules, in each
    version's own terms, come with SPEC.md 17.7 step 2.

    Raises
    ------
    NotImplementedError
      A saved map ('save'): SPEC.md 17.7 step 3.
    """
    if self.save:
      infoSpec = """The world '%s' is the saved map '%s': saved maps come
      with SPEC.md 17.7 step 3."""
      info = infoSpec % (self.label(), self.save)
      raise NotImplementedError(' '.join(info.split()))
    return {'type': 'default', 'seed': self.seed}

  def getDecorated(self) -> tuple[str, ...]:
    """The names of the test methods this world decorated, in order."""
    if self.__decorated__ is None:
      return ()
    return tuple(self.__decorated__)

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  SETTERS  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  CONSTRUCTORS   # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  def __init__(self) -> None:
    """
    A world with nothing decorated yet and not entered. It takes no
    arguments: its options belong to its class.
    """
    BaseObject.__init__(self)
    self.__decorated__ = {}

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  PARENT METHODS   # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  def hookSetName(self, owner: type, name: str, **kwargs: Any) -> None:
    """
    The placement in a test class's body, exactly once, after every
    decoration in that body.

    Raises
    ------
    TypeError
      A method this world decorated isn't in the owner's body as it was
      decorated (redefined after its decoration); a method is decorated
      by two worlds; this world is placed a second time; or the owner is
      a MultiplayerTestCase, whose worlds come later (SPEC.md 17.8).
    """
    if self.__placement__ is not None:
      #  'Object.__set_name__' recorded this placement before the hook:
      #  the first one is put back, so the refusal changes nothing
      firstOwner, firstName = self.__placement__
      object.__setattr__(self, '__field_owner__', firstOwner)
      object.__setattr__(self, '__field_name__', firstName)
      infoSpec = """The world '%s.%s' is placed again, as '%s.%s'. A world
      is placed once, in the class body that made it; another class
      places a world of its own."""
      info = infoSpec % (firstOwner.__name__, firstName, owner.__name__,
                         name)
      raise TypeError(' '.join(info.split()))
    self.__placement__ = (owner, name)
    #  here, not at the top: unittas.testcase is the run's, and it uses
    #  worlds
    from .testcase import MultiplayerTestCase
    if issubclass(owner, MultiplayerTestCase):
      infoSpec = """The world '%s.%s' is placed in a MultiplayerTestCase:
      worlds on a server aren't there yet (SPEC.md 17.8)."""
      raise TypeError(' '.join((infoSpec % (owner.__name__, name)).split()))
    body = vars(owner)
    for key, method in self.__decorated__.items():
      if body.get(key) is not method:
        infoSpec = """'%s.%s' was decorated by the world '%s', then
        defined again in the class body, which left it without its
        world."""
        info = infoSpec % (owner.__name__, key, name)
        raise TypeError(' '.join(info.split()))
    for otherName, other in body.items():
      if other is self or not isinstance(other, World):
        continue
      for key in self.getDecorated():
        if key in other.getDecorated():
          infoSpec = """'%s.%s' is decorated by two worlds, '%s' and
          '%s'. A test runs in one world."""
          info = infoSpec % (owner.__name__, key, name, otherName)
          raise TypeError(' '.join(info.split()))

  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  #  DOMAIN SPECIFIC  # # # # # # # # # # # # # # # # # # # # # # # # # # # #
  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

  def __call__(self, method: Callable) -> Callable:
    """
    Decorates a test method: records its name, returns it as received.

    Raises
    ------
    TypeError
      The world is placed already, so nothing would check the decoration
      (a subclass places a world of its own); or 'method' is no plain
      function.
    """
    if not isinstance(method, FunctionType):
      infoSpec = """A world decorates test methods, plain functions in a
      class body, not %r."""
      raise TypeError(' '.join((infoSpec % (method,)).split()))
    if self.__placement__ is not None:
      owner, name = self.__placement__
      infoSpec = """'%s' is decorated by the world '%s.%s', which is
      placed already, so nothing would check the decoration. A class
      places a world of its own for its tests."""
      info = infoSpec % (method.__name__, owner.__name__, name)
      raise TypeError(' '.join(info.split()))
    self.__decorated__[method.__name__] = method
    return method

  def setUp(self) -> None:
    """A world's own setup: run once when it's made and entered."""

  def enter(self, game: Game, start: Vec3, spawn: BlockPos) -> None:
    """
    The run hands over the entered world (SPEC.md 17.8).

    Raises
    ------
    RuntimeError
      It's entered already: the run leaves a world before entering it.
    """
    if self.__entered__ is not None:
      infoSpec = """The world '%s' is entered already: the run leaves it
      first."""
      raise RuntimeError(' '.join((infoSpec % self.label()).split()))
    self.__entered__ = {'game': game, 'start': start, 'spawn': spawn}

  def leave(self) -> None:
    """
    The run takes the entered world back; reads raise after this.

    Raises
    ------
    RuntimeError
      It isn't entered.
    """
    self._getEntered()
    self.__entered__ = None

  @overload(BlockPos)
  def block(self, pos: BlockPos) -> frozenset:
    """The mcdex blocks the block at 'pos' is (SPEC.md 14.3)."""
    raise NotImplementedError

  @overload(int, int, int)
  def block(self, x: int, y: int, z: int) -> frozenset:
    """The mcdex blocks the block at x, y, z is."""
    return self.block(BlockPos(x, y, z))

  def fill(self, a: BlockPos, b: BlockPos, block: MCBlocks) -> None:
    """The box from 'a' to 'b' filled with 'block'."""
    raise NotImplementedError

  @overload(BlockPos)
  def biome(self, pos: BlockPos) -> MCBiomes:
    """The biome at 'pos', as the game holds it."""
    raise NotImplementedError

  @overload(int, int)
  def ground(self, x: int, z: int) -> BlockPos:
    """The top solid block at x, z, so no test names a height."""
    raise NotImplementedError

  def nearest(self, structure: MCStructures, pos: BlockPos) -> BlockPos:
    """The nearest structure of that kind, by the game's own search."""
    raise NotImplementedError

  def generate(self, a: BlockPos, b: BlockPos) -> None:
    """The chunks from 'a' to 'b' generated by the game's generator."""
    raise NotImplementedError

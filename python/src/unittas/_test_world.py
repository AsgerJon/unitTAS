"""
World encapsulates a minecraft world used for testing.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from types import FunctionType
from typing import TYPE_CHECKING

from mcdex import MCBiomes
from worktoy.desc import Field, FixBox
from worktoy.dispatch import overload
from worktoy.mcls import BaseObject

from .gamemode import GameMode
from .values import BlockPos
from .worldkind import WorldKind

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Callable, Optional

  from mcdex import MCBlocks, MCStructures, Version

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
  #  The world's options, in mcdex's terms and unitTAS's own (SPEC.md
  #  17.4): each version makes it as its own. 'layers' are a flat world's,
  #  bottom up, (MCBlocks member, thickness); 'flatBiome' is a flat
  #  world's too ('biome' is the read, 17.5); 'rules' maps MCGameRules
  #  members to their values.
  seed = FixBox[int](0)
  kind = FixBox[WorldKind](WorldKind.Default)
  layers = FixBox[tuple](())
  flatBiome = FixBox[MCBiomes](MCBiomes.Plains)
  rules = FixBox[dict]({})
  gameMode = FixBox[GameMode](GameMode.Creative)
  structures = FixBox[bool](True)
  save = FixBox[str]('')
  fresh = FixBox[bool](False)

  #  Virtual Variables
  start = Field()
  spawn = Field()
  game = Field()

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

  @game.GET
  def _getGame(self) -> Game:
    """The game it's entered in, for its setUp; raises if not entered."""
    return self._getEntered()['game']

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

  def createArgs(self, version: Version,
                 declared: Optional[dict] = None) -> dict:
    """
    world.create's arguments for this world in the version (PROTOCOL.md):
    its kind, seed, game mode and structures; a flat world's layers as
    that version's blocks, bottom up, and its biome as that version's
    id, from which each probe writes its own generator text. 'declared'
    is the game's mods' declarations (Game.declared).

    Raises
    ------
    Missing
      A layer's block or the flat biome is one vanilla lacks there and no mod
      declares: the world's sanity check fails (SPEC.md 17.4).
    TypeError
      Layers on a world that isn't flat; a layer that isn't an MCBlocks
      member with a thickness, or one told apart by block entity data.
    TypeError
      A saved map ('save'), which is opened, not made.
    """
    from .things import blockOf, resolve
    if self.save:
      infoSpec = """The world '%s' is the saved map '%s': it's opened from
      a fresh copy (savedFolder), not made."""
      info = infoSpec % (self.label(), self.save)
      raise TypeError(' '.join(info.split()))
    args = {'type': self.kind.value, 'seed': self.seed,
            'game_mode': self.gameMode.value, 'structures': self.structures}
    if not self.layers:
      return args
    if self.kind is not WorldKind.Flat:
      raise TypeError("%s has layers, which are a flat world's, but its "
                      "kind is %s" % (self.label(), self.kind))
    layers = []
    for layer in self.layers:
      if not isinstance(layer, tuple) or len(layer) != 2:
        raise TypeError('%s: a layer is (MCBlocks member, thickness), not %r'
                        % (self.label(), layer))
      member, count = layer
      block, tile = blockOf(member, version, declared)
      if tile:
        raise TypeError('%s: %s.%s is told apart by its block entity data '
                        'there, which a layer has none of'
                        % (self.label(), type(member).__name__, member.name))
      layer = {'id': block.id}
      #  none from 1.13 on (D4)
      if block.meta >= 0:
        layer['meta'] = block.meta
      layer['count'] = count
      layers.append(layer)
    args['layers'] = layers
    args['biome'] = resolve(self.flatBiome, version, declared).text()
    return args

  def savedFolder(self) -> str:
    """
    A saved map's folder (SPEC.md 17.4): 'save' beside the module that
    declares this World's class, or as given when absolute. The run
    copies it fresh for each use and opens the copy, never the map.

    Raises
    ------
    TypeError
      This World is no saved map, or it sets options that are the map's
      own (kind, seed, layers, flatBiome, gameMode, structures).
    FileNotFoundError
      No save is there (no level.dat).
    """
    import os
    import sys
    if not self.save:
      raise TypeError('%s is no saved map' % self.label())
    defaults = (('kind', WorldKind.Default), ('seed', 0), ('layers', ()),
                ('flatBiome', MCBiomes.Plains),
                ('gameMode', GameMode.Creative), ('structures', True))
    own = [name for name, value in defaults if getattr(self, name) != value]
    if own:
      raise TypeError("%s is the saved map %s, whose %s are the map's own, "
                      "not the World's to set"
                      % (self.label(), self.save, ', '.join(own)))
    module = sys.modules.get(type(self).__module__)
    path = getattr(module, '__file__', None)
    if path is None:
      raise TypeError('%s is declared in %s, which has no file to find '
                      'its map beside'
                      % (self.label(), type(self).__module__))
    folder = os.path.normpath(os.path.join(
      os.path.dirname(os.path.abspath(path)), self.save))
    if not os.path.isfile(os.path.join(folder, 'level.dat')):
      raise FileNotFoundError('%s: no saved map at %s (no level.dat there)'
                              % (self.label(), folder))
    return folder

  def ruleArgs(self, version: Version,
               declared: Optional[dict] = None) -> dict:
    """
    world.rules.set's rules for this world in the version: each
    MCGameRules member's name there, to its value.

    Raises
    ------
    Missing
      A rule vanilla lacks there: the world's sanity check fails.
    """
    from .things import resolve
    return {resolve(member, version, declared).text(): value
            for member, value in self.rules.items()}

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

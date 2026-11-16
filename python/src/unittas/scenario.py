"""
ScenarioTestCase: a GameTestCase with a scene and the agent that plays
it (SPEC.md 15.3).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .agent import Agent
from .run import Run
from .scene import Scene
from .testcase import GameTestCase
from .values import BlockPos, Vec3

if TYPE_CHECKING:  # pragma: no cover
  from typing import Any, Optional


class ScenarioTestCase(GameTestCase):
  """
  A scenario's tests: 'self.agent' plays the run's own player, a player
  and nothing more (SPEC.md 15.2), its views' frames kept in the run's
  results (frames/); 'self.scene' gives places from the block the run's
  start stands in, when the class set up, and notes what each test
  examined under its report line.

    class LeverTests(ScenarioTestCase):
      @classmethod
      def setUpClass(cls) -> None:
        super().setUpClass()
        cls.scene.place(MCBlocks.Lever, at=(5, 0, 7))

      def test_the_lever(self) -> None:
        lever = self.scene.thing(MCBlocks.Lever, at=(5, 0, 7))
        if not lever.isOn():
          lever.activate()
        self.assertTrue(lever.isOn())
  """

  agent: Agent = None
  scene: Scene = None

  @classmethod
  def setUpClass(cls) -> None:
    super().setUpClass()
    cls.agent = Agent(cls.game, os.path.join(Run.current.results, 'frames'))
    cls.scene = Scene(cls.agent, Vec3(*Run.current.start).block())

  def assertIdentifies(self, pos: BlockPos, member: Any,
                       among: Optional[Any] = None, msg: str = '') -> None:
    """
    That the agent tells the block at 'pos' is 'member' by its looks alone
    (SPEC.md 15.4), among 'among' or every full cube: a FAIL naming what it
    is by its looks otherwise. What can't be told is the agent's
    TesttimeError, an ERROR.
    """
    found = self.agent.identify(pos, among)
    if found is not member:
      self.fail(msg or 'the block at (%d, %d, %d) is %s.%s by its looks, '
                'not %s.%s' % (pos.x, pos.y, pos.z, type(found).__name__,
                               found.name, type(member).__name__,
                               member.name))

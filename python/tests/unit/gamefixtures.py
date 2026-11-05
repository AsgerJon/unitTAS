"""
Class fixtures for test_runsuites.py: a suite (by module name) whose classes fail or skip in setUpClass or fail in
tearDownClass. Not a test module (unittest's discovery doesn't load it); test_runsuites runs it on a fake game.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import unittest

from unittas.testcase import GameTestCase


class AFixtureErrorTests(GameTestCase):

  @classmethod
  def setUpClass(cls) -> None:
    super().setUpClass()
    raise RuntimeError('setUpClass fails on purpose')

  def test_never_runs(self) -> None:
    self.fail('ran')


class BSkipClassTests(GameTestCase):

  @classmethod
  def setUpClass(cls) -> None:
    super().setUpClass()
    raise unittest.SkipTest('the whole class is skipped')

  def test_a(self) -> None:
    self.fail('ran')

  def test_b(self) -> None:
    self.fail('ran')


class CTearDownErrorTests(GameTestCase):

  @classmethod
  def tearDownClass(cls) -> None:
    raise RuntimeError('tearDownClass fails on purpose')

  def test_1(self) -> None:
    pass

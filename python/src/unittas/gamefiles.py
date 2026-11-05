"""
The 'gamefiles' module keeps a game folder's own settings safe while an
orchestrator's game runs in it (PROTOCOL.md section 0, point 3): its
options.txt and its config/ are copied aside before the game starts, and
put back exactly after it has exited. That is outside the game, so a
crash can't skip it, and a copy left by a run that died is put back by
the next one before anything else.

- GameFiles: keep() before the launch, putBack() after the exit.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import shutil

from worktoy.desc import Field
from worktoy.mcls import BaseObject

_OPTIONS = 'options.txt'
_CONFIG = 'config'
#  options.txt wasn't there when the copy was made: put back means removed
_ABSENT = 'options.txt.absent'


def _below(root: str) -> list:
  """Everything under the folder, each folder before what it holds, links not followed; none if it isn't one."""
  if not os.path.isdir(root) or os.path.islink(root):
    return []
  found = []
  for here, dirs, files in os.walk(root, followlinks=False):
    for name in sorted(dirs) + sorted(files):
      found.append(os.path.join(here, name))
  return found


def _remove(path: str) -> None:
  """One file, link or empty folder."""
  if os.path.isdir(path) and not os.path.islink(path):
    os.rmdir(path)
  else:
    os.remove(path)


def _copyExactly(source: str, target: str) -> None:
  """
  Makes the folder 'target' hold exactly what 'source' holds: every file
  copied over, what 'source' lacks removed, links copied as links (what
  they point at is never read or written).
  """
  os.makedirs(target, exist_ok=True)
  for path in reversed(_below(target)):
    relative = os.path.relpath(path, target)
    there = os.path.join(source, relative)
    same = os.path.lexists(there) and (os.path.islink(there) == os.path.islink(path))
    if same and os.path.isdir(there) == os.path.isdir(path):
      continue
    if os.path.isdir(path) and not os.path.islink(path):
      _removeTree(path)
    else:
      os.remove(path)
  for path in _below(source):
    copy = os.path.join(target, os.path.relpath(path, source))
    if os.path.islink(path):
      if os.path.lexists(copy):
        os.remove(copy)
      os.symlink(os.readlink(path), copy)
    elif os.path.isdir(path):
      os.makedirs(copy, exist_ok=True)
    else:
      shutil.copy2(path, copy, follow_symlinks=False)


#  the run's kept world uses them too (unittas.run)
copyExactly = _copyExactly


def _removeTree(folder: str) -> None:
  """The folder and everything under it, deepest first, links removed as links."""
  for path in reversed(_below(folder)):
    _remove(path)
  if os.path.lexists(folder):
    _remove(folder)


class GameFiles(BaseObject):
  """
  A game folder's options.txt and config/. 'keep' copies them into
  'unittas/orchestrator.backup' and writes the marker last, so a copy
  counts only once it is whole; 'putBack' makes them exactly what was
  kept and removes the copy. Nothing else in the folder is touched.
  """

  gameDir: Field[str] = Field()
  backup: Field[str] = Field()
  marker: Field[str] = Field()

  def __init__(self, gameDir: str) -> None:
    self.__game_dir__ = os.path.abspath(gameDir)

  @gameDir.GET
  def _getGameDir(self) -> str:
    return self.__game_dir__

  @backup.GET
  def _getBackup(self) -> str:
    return os.path.join(self.gameDir, 'unittas', 'orchestrator.backup')

  @marker.GET
  def _getMarker(self) -> str:
    return os.path.join(self.gameDir, 'unittas', 'orchestrator.backup.whole')

  def keep(self) -> None:
    """
    Copies options.txt and config/ aside. A whole copy already there is
    an earlier run's that never put it back: that one is put back first.
    """
    self.putBack()
    _removeTree(self.backup)
    os.makedirs(self.backup)
    options = os.path.join(self.gameDir, _OPTIONS)
    if os.path.lexists(options):
      shutil.copy2(options, os.path.join(self.backup, _OPTIONS), follow_symlinks=False)
    else:
      open(os.path.join(self.backup, _ABSENT), 'w').close()
    config = os.path.join(self.gameDir, _CONFIG)
    if os.path.isdir(config) and not os.path.islink(config):
      _copyExactly(config, os.path.join(self.backup, _CONFIG))
    open(self.marker, 'w').close()

  def putBack(self) -> bool:
    """
    Puts back what 'keep' copied, exactly, and removes the copy. False,
    and nothing touched, when there is no whole copy.
    """
    if not os.path.isfile(self.marker):
      return False
    options = os.path.join(self.gameDir, _OPTIONS)
    if os.path.lexists(os.path.join(self.backup, _ABSENT)):
      if os.path.lexists(options):
        os.remove(options)
    else:
      if os.path.lexists(options):
        os.remove(options)
      shutil.copy2(os.path.join(self.backup, _OPTIONS), options, follow_symlinks=False)
    kept = os.path.join(self.backup, _CONFIG)
    config = os.path.join(self.gameDir, _CONFIG)
    if os.path.isdir(kept):
      _copyExactly(kept, config)
    elif os.path.lexists(config):
      if os.path.isdir(config) and not os.path.islink(config):
        _removeTree(config)
      else:
        os.remove(config)
    os.remove(self.marker)
    _removeTree(self.backup)
    return True


#  the run's kept world uses it too (unittas.run)
removeTree = _removeTree

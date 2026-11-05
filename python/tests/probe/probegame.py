"""
What the probe's tests share: where the repository and this run's results
are, and how long the game may take for each thing it does.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
#  from the start of loading to the title screen, with every mod (a cold start included)
READY_SECONDS = 600.0
#  from asking it to quit, or from losing its orchestrator, to its process gone
GONE_SECONDS = 120.0
#  unitTAS's mixins, as the ready event names them (mixins.unittas.json)
MIXINS = ('MixinHandshakeTrace', 'MixinLoginClientTrace', 'MixinLoginServerTrace', 'MixinMinecraft',
          'MixinMouseHelper', 'MixinNetworkManagerTrace', 'MixinNetworkSystemTrace', 'MixinPlayClientTrace',
          'MixinSoundHandler')


def results() -> str:
  """This run's results folder (unittas.selftest sets it), or one of the tests' own when run by hand."""
  folder = os.environ.get('UNITTAS_RESULTS_ROOT') or os.path.join(ROOT, 'unittas-results', 'probe-by-hand')
  os.makedirs(folder, exist_ok=True)
  return folder


def modVersion() -> str:
  """unitTAS's version, as gradle.properties says (the release tooling stamps it there)."""
  with open(os.path.join(ROOT, 'gradle.properties'), encoding='utf-8') as file:
    for line in file:
      if line.startswith('mod_version='):
        return line.split('=', 1)[1].strip()
  raise AssertionError('no mod_version in gradle.properties')

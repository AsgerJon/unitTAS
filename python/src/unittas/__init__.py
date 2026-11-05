"""
The 'unittas' package is the Python side of unitTAS: the orchestrator that
starts Minecraft, and the protocol it speaks with the probe inside the game
(PROTOCOL.md). Being built, phase 3 of the pivot (SPEC.md section 9).

- wire: the protocol's closed sets and its messages, as lines of JSON.
- errors: one exception for each error type an answer can carry.
- link: the listener, the start file, and a connection to one game.
- values, codec: the protocol's values, and their JSON edge.
- snbt: NBT as SNBT text, read into a typed tree and written back.
- spec: the instance spec, a TOML file saying which game a run needs.
- cache, launcher: the download cache, and the real client's launch.
- mappings: readable (MCP) names to the game's, for reflection.
- api: Game, the face of a game a test speaks to.
- game, dev, release: the games the probe's own tests start; gamefiles,
  the game folder's own files kept aside and put back.
- display: the test display (gamescope) in front of a game.
- specgame: the game an instance spec names, real or the mod's Gradle run.
- reset: the reset, in PROTOCOL.md 9.5's order.
- run, testcase: a run's lifecycle and report, and GameTestCase.
- session, cli: the 'unittas' command (run, launch, compare), and the run
  plain unittest starts from the spec.
- compare: two reports compared test by test.
- selftest: the probe's own tests, in one game.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

__version__ = '0.1.0.dev0'

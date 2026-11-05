"""
The 'unittas' package is the Python side of unitTAS: the orchestrator that
starts Minecraft, and the protocol it speaks with the probe inside the game
(PROTOCOL.md). Being built, phase 2 of the pivot.

- wire: the protocol's closed sets and its messages, as lines of JSON.
- errors: one exception for each error type an answer can carry.
- link: the listener, the start file, and a connection to one game.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

__version__ = '0.1.0.dev0'

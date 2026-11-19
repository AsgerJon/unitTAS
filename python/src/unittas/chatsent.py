"""
ChatSent: what came back to the chat after a line was sent to it, as if
typed and sent (chat.send, PROTOCOL.md 8.6; Game.sendChat).
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from worktoy.ezdata import EZData, EZField


class ChatSent(EZData, frozen=True):
  """
  The chat lines that came in while it settled ('lines', plain text),
  and the red ones among them ('errors': a command refused, say).
  """

  lines = EZField[tuple]()
  errors = EZField[tuple]()

"""'python -m unittas ...' is the 'unittas' command (unittas.cli)."""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import sys

from .cli import main

if __name__ == '__main__':
  sys.exit(main())

"""
unitTAS's own launcher: a real (not development) Minecraft 1.7.10 Forge 10.13.4.1614 client, started from what the
project's Gradle cache already holds, so nothing is downloaded and no other launcher is needed.

  python3 bin/launch_client.py --game DIR [--dry-run]

From the cache (.gradle-home, or UNITTAS_GRADLE_HOME): Unimined's official client jar and vanilla's version.json,
Forge's universal jar and the version.json inside it, every library they name from modules-2, the LWJGL and JInput
natives, and Unimined's assets. The class path follows the two version.json files as a launcher does: vanilla's
rules for Linux, a library both name kept once (Forge's: guava 17, commons-lang3 3.3.2), natives off it (extracted
into DIR/natives instead), the client jar last. The game runs on Java 8 (UNITTAS_JAVA8, else
/usr/lib/jvm/java-8-openjdk), offline as unitTAS, in DIR (its mods/, config/, saves/, unittas/request.properties).
The java process replaces this one, so its command line holds DIR. --dry-run only prints the command.

Exits 2 when something it needs is missing, naming it.

The launcher itself is the Python package's (python/src/unittas/launcher.py), which can also fetch what the Gradle
cache lacks into a download cache; this script never does. It uses the standard library only, so the system's own
Python runs it.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'python', 'src'))

from unittas.launcher import main  # noqa: E402  (after the package's folder is on the path)

if __name__ == '__main__':
  sys.exit(main(*sys.argv[1:], gradleHome=os.path.join(ROOT, '.gradle-home')))

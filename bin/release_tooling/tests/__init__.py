"""
The tests of the release tooling in 'bin/release_tooling'. They run with
'unittest' from that folder,

  python -B -m unittest discover -s tests -t .

and every release workflow runs them in its 'safety' job, after the
safeties are locked and before the verdict is enforced. Each test works
on copies in a temporary folder, never on the files of the repository.

- ReleaseToolingTest
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from ._release_tooling_test import ReleaseToolingTest, SAFETY, BASE
from ._release_tooling_test import TOOLING_VERSION

__all__ = [
  'ReleaseToolingTest',
  'SAFETY',
  'BASE',
  'TOOLING_VERSION',
]

"""
The 'cache' module keeps the files a game needs, fetched once and shared by
every run: '~/.cache/unittas', or the folder UNITTAS_CACHE names (SPEC.md
9.3, step 3).

Every file is held to its sha1 before it is kept. It is written to a part
file of its own and renamed into place only once whole and checked, so a
run that dies mid-download never leaves a file that looks done. A file in
the cache was checked when it was written, so using it needs no network.
Nothing is fetched but over HTTPS.

The standard library only: bin/launch_client.py uses this from the system's
own Python.

- Cache: the cache's folder, and 'get', which gives a file, fetching it when
  it isn't there yet.
- httpsFetch: the default way to fetch a URL, HTTPS only.
- sha1Of: a file's or some bytes' sha1.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

import hashlib
import os
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
  from typing import Callable, Iterable, Optional

#  How long one request may take, connecting and reading.
FETCH_SECONDS = 120


class CacheError(Exception):
  """A file that can't be had: not fetched, or not what its sha1 says."""


def defaultRoot() -> str:
  return os.environ.get('UNITTAS_CACHE') or os.path.join(os.path.expanduser('~'), '.cache', 'unittas')


def httpsFetch(url: str, timeout: float = FETCH_SECONDS) -> bytes:
  """The bytes at the URL; ValueError for anything but https://, OSError when the server can't give them."""
  if not url.startswith('https://'):
    raise ValueError('only https:// is fetched, not %s' % url)
  from . import __version__
  request = urllib.request.Request(url, headers={'User-Agent': 'unittas/%s' % __version__})
  with urllib.request.urlopen(request, timeout=timeout) as answer:
    return answer.read()


def sha1Of(data: bytes) -> str:
  return hashlib.sha1(data).hexdigest()


def fileSha1(path: str) -> str:
  digest = hashlib.sha1()
  with open(path, 'rb') as file:
    for block in iter(lambda: file.read(1 << 20), b''):
      digest.update(block)
  return digest.hexdigest()


class Cache:
  """The cache's folder ('root') and the fetcher it uses ('fetch', a URL to its bytes)."""

  def __init__(self, root: Optional[str] = None, fetch: Optional[Callable[[str], bytes]] = None) -> None:
    self.root = os.path.abspath(root or defaultRoot())
    self.fetch = fetch or httpsFetch

  def path(self, relative: str) -> str:
    return os.path.join(self.root, *relative.split('/'))

  def get(self, relative: str, url: str, sha1s: Iterable[str] = (), sha1Url: Optional[str] = None,
          what: Optional[str] = None) -> str:
    """
    The file at 'relative' in the cache, fetched from 'url' when it isn't
    there. It must match one of 'sha1s', or else the sha1 at 'sha1Url' (a
    maven's .sha1 file); with neither known it isn't fetched at all.
    CacheError naming 'what' (the url by default) when it can't be had.
    """
    target = self.path(relative)
    if os.path.isfile(target):
      return target
    name = what or url
    wanted = [each.lower() for each in sha1s]
    if not wanted and sha1Url is not None:
      try:
        wanted = [self.fetch(sha1Url).decode('ascii', 'replace').split()[0].lower()]
      except (OSError, ValueError, IndexError) as error:
        raise CacheError('%s: no checksum known (its .sha1 at %s: %s)' % (name, sha1Url, error)) from None
    if not wanted:
      raise CacheError('%s: no checksum known, so it isn\'t fetched' % name)
    try:
      data = self.fetch(url)
    except (OSError, ValueError) as error:
      raise CacheError('%s: couldn\'t be fetched from %s: %s' % (name, url, error)) from None
    got = sha1Of(data)
    if got not in wanted:
      raise CacheError('%s: what %s gave has the sha1 %s, not %s; not kept' % (name, url, got, ' or '.join(wanted)))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    part = '%s.part-%d' % (target, os.getpid())
    try:
      with open(part, 'wb') as file:
        file.write(data)
      os.replace(part, target)
    finally:
      if os.path.exists(part):
        os.remove(part)
    return target

  def store(self, relative: str, source: str, sha1: Optional[str] = None) -> str:
    """A file from elsewhere (the Gradle cache's) copied in, held to its sha1 when one is known, renamed into place."""
    target = self.path(relative)
    if os.path.isfile(target):
      return target
    if sha1 is not None and fileSha1(source) != sha1.lower():
      raise CacheError('%s: its sha1 is not %s; not kept' % (source, sha1))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    part = '%s.part-%d' % (target, os.getpid())
    try:
      with open(source, 'rb') as reading, open(part, 'wb') as writing:
        for block in iter(lambda: reading.read(1 << 20), b''):
          writing.write(block)
      os.replace(part, target)
    finally:
      if os.path.exists(part):
        os.remove(part)
    return target

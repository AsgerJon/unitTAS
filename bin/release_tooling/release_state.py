"""
release_state holds the release state machine of unitTAS: the nine
release buttons, the three states 'VERSION' can be in, and what a press
of each button does in each state. 'version_get.py', 'version_bump.py'
and 'safety_check.py' import it, so every press is decided in one place.

Known limitation: the tooling publishes one line of releases. Every
button runs on 'main' alone, and every press names its version from the
one 'VERSION' file, so a micro update cannot be published on an older
line, as a 1.1.1 once 1.2.0 is released. This remains unimplemented by
decision (2026-11-12): it will not be necessary for a long time, and it
would bring a lot of complexity.
"""
#  Apache-2.0 license
#  Copyright (c) 2026 Asger Jon Vistisen
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
  from typing import Optional

#  The nine buttons, each named level first and kind second, as is its
#  workflow file, in the order the messages list them.
BUTTONS = (
  'micro-dev', 'micro-rc', 'micro-lts',
  'minor-dev', 'minor-rc', 'minor-lts',
  'major-dev', 'major-rc', 'major-lts',
)

#  The kind of each button, its level, and the stem of its safety file,
#  which carries the name of the button.
_BUTTON_TABLE = {
  'micro-dev': ('dev', 'micro', 'micro-dev'),
  'micro-rc': ('rc', 'micro', 'micro-rc'),
  'micro-lts': ('lts', 'micro', 'micro-lts'),
  'minor-dev': ('dev', 'minor', 'minor-dev'),
  'minor-rc': ('rc', 'minor', 'minor-rc'),
  'minor-lts': ('lts', 'minor', 'minor-lts'),
  'major-dev': ('dev', 'major', 'major-dev'),
  'major-rc': ('rc', 'major', 'major-rc'),
  'major-lts': ('lts', 'major', 'major-lts'),
}

#  The levels from lowest to highest.
LEVELS = ('micro', 'minor', 'major')
NO_LEVEL = 'none'

#  The safety files, by stem, in the order of the buttons.
SAFETY_NAMES = (*(_BUTTON_TABLE[button][2] for button in BUTTONS),)

#  The settings of 'VERSION', in the order they are written.
_KEYS = ('major', 'minor', 'micro', 'rc', 'dev', 'level')

#  The kinds of press.
ARMED = 'armed'
FREE = 'free'
REFUSED = 'refused'

_NEEDS_RC = """A release needs at least one release candidate before it,
even if it is identical."""


def _flat(text: str) -> str:
  """Collapse every run of whitespace in 'text' to one space"""
  return str.join(' ', str.split(text))


class ReleaseRefused(RuntimeError):
  """
  A press refused by the state machine, raised by 'advance' with the
  message 'decide' gives the press.
  """


class Press:
  """
  The decision on one press of one button in one state of 'VERSION'.

  Attributes
  ----------

  button : str
    The button pressed.

  kind : str
    'armed' when the press runs only once its safety reads 'ALLOW',
    'free' when it needs no safety, 'refused' when it may not run.

  name : str or None
    The version the press publishes, or 'None' for a refused press.

  safety : str or None
    The stem of the safety file an armed press reads, or 'None'.

  accepted : tuple[str, ...]
    The buttons a press is accepted from in this state.

  message : str
    The decision in plain words.
  """

  def __init__(self, button: str, kind: str, name: Optional[str],
               safety: Optional[str], accepted: tuple, message: str
               ) -> None:
    self.button = button
    self.kind = kind
    self.name = name
    self.safety = safety
    self.accepted = accepted
    self.message = message


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#  BUTTONS  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def buttonKind(button: str) -> str:
  """Return 'dev', 'rc' or 'lts' for 'button'"""
  return _BUTTON_TABLE[button][0]


def buttonLevel(button: str) -> str:
  """Return 'micro', 'minor' or 'major' for 'button'"""
  return _BUTTON_TABLE[button][1]


def safetyName(button: str) -> str:
  """Return the stem of the safety file of 'button'"""
  return _BUTTON_TABLE[button][2]


def buttonOf(kind: str, level: str) -> str:
  """Return the button of 'kind' and 'level'"""
  for button in BUTTONS:
    if _BUTTON_TABLE[button][:2] == (kind, level):
      return button
  raise KeyError((kind, level))


def joinWords(*words: str) -> str:
  """Join 'words' as a sentence lists them: 'a, b and c'"""
  if len(words) < 2:
    return str.join('', words)
  return '%s and %s' % (str.join(', ', words[:-1]), words[-1])


def joinChoices(*words: str) -> str:
  """Join 'words' as a choice: 'a, b or c'"""
  if len(words) < 2:
    return str.join('', words)
  return '%s or %s' % (str.join(', ', words[:-1]), words[-1])


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#  VERSION  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def _readText(path: str) -> str:
  handle = None
  try:
    handle = open(path, 'r', encoding='utf-8')
  except OSError as osError:
    raise osError
  else:
    return handle.read()
  finally:
    if handle is not None:
      handle.close()


def _writeText(path: str, text: str) -> None:
  handle = None
  try:
    handle = open(path, 'w', encoding='utf-8', newline='')
  except OSError as osError:
    raise osError
  else:
    handle.write(text)
  finally:
    if handle is not None:
      handle.close()


def validate(info: dict) -> None:
  """
  A press decided from a 'VERSION' the state machine could never have
  written would publish a wrong name, so such a file is refused before
  any press is decided from it, and before any is written.

  Implementation
  --------------

  Every setting must be present; the counters must be whole numbers of
  at least 0, and MICRO at least 1, since it holds the next micro version
  after the last full release; LEVEL must be 'none' or a level. With no
  level locked, RC and DEV are 0; with one locked, a dev0 was published,
  so DEV is at least 1.

  Raises
  ------

  RuntimeError
    The settings describe no state of the machine.
  """
  missing = [str.upper(key) for key in _KEYS if key not in info]
  if missing:
    if len(missing) == 1:
      raise RuntimeError('VERSION lacks the line for %s.' % missing[0])
    infoSpec = 'VERSION lacks the lines for %s.'
    raise RuntimeError(infoSpec % joinWords(*missing))
  for key in _KEYS[:-1]:
    if info[key] < 0:
      infoSpec = 'The counter %s in VERSION is below 0: %d.'
      raise RuntimeError(infoSpec % (str.upper(key), info[key]))
  level = info['level']
  if level != NO_LEVEL and level not in LEVELS:
    infoSpec = """LEVEL must be none, micro, minor or major, but VERSION
    reads LEVEL=%s."""
    raise RuntimeError(_flat(infoSpec % level))
  if info['micro'] < 1:
    infoSpec = """MICRO holds the next micro version after the last full
    release, so it is at least 1, but VERSION reads MICRO=%d."""
    raise RuntimeError(_flat(infoSpec % info['micro']))
  if level == NO_LEVEL:
    if info['rc'] or info['dev']:
      infoSpec = """With LEVEL=none no cycle is open, so RC and DEV are 0,
      but VERSION reads RC=%d DEV=%d."""
      raise RuntimeError(_flat(infoSpec % (info['rc'], info['dev'])))
    return
  if info['dev'] < 1:
    infoSpec = """With LEVEL=%s a dev cycle was opened, so DEV is at least
    1, but VERSION reads DEV=0."""
    raise RuntimeError(_flat(infoSpec % level))


def readVersion(path: str) -> dict:
  """
  The counters and the locked level must be read from 'VERSION' the same
  way by every script that decides a press.

  Implementation
  --------------

  Blank lines, comment lines starting with '#' and lines without '=' are
  passed over. Every other line is 'KEY=VALUE', the key in any case and
  the value a whole number, except for LEVEL, whose value is text. The
  result is checked by 'validate'.

  Parameters
  ----------

  path : str
    The path of the 'VERSION' file.

  Returns
  -------

  dict
    The keys 'major', 'minor', 'micro', 'rc' and 'dev', each an 'int',
    and 'level', a 'str'.

  Raises
  ------

  RuntimeError
    A line holds more than one '=', an unknown key or a counter that is
    no whole number, or the file describes no state of the machine.
  """
  out = dict()
  for line in str.split(_readText(path), '\n'):
    line = str.strip(line)
    if not line or str.startswith(line, '#') or '=' not in line:
      continue
    key, value, *remainder = str.split(line, '=')
    if remainder:
      infoSpec = """VERSION holds more than one '=' in the line: '%s'."""
      raise RuntimeError(infoSpec % line)
    key, value = str.lower(str.strip(key)), str.strip(value)
    if key not in _KEYS:
      raise RuntimeError("VERSION holds an unknown line: '%s'." % line)
    if key == 'level':
      out[key] = value
      continue
    try:
      out[key] = int(value)
    except ValueError as valueError:
      infoSpec = """The counter %s in VERSION is no whole number: '%s'."""
      raise RuntimeError(infoSpec % (str.upper(key), value)) from valueError
  validate(out)
  return out


def writeVersion(path: str, info: dict) -> None:
  """
  After a publish the advanced counters must be written back, keeping
  the explanation at the head of the file.

  Implementation
  --------------

  The settings are checked by 'validate' first, so nothing is written for
  a state the machine has no place for. The comment lines of the file at
  'path' are kept, in order, and followed by one line per setting.

  Parameters
  ----------

  path : str
    The path of the 'VERSION' file.

  info : dict
    The settings, as 'readVersion' gives them.

  Raises
  ------

  RuntimeError
    The settings describe no state of the machine.
  """
  validate(info)
  comments = []
  for line in str.split(_readText(path), '\n'):
    line = str.strip(line)
    if str.startswith(line, '#'):
      comments.append(line)
  settings = [
    'MAJOR=%d' % info['major'],
    'MINOR=%d' % info['minor'],
    'MICRO=%d' % info['micro'],
    'RC=%d' % info['rc'],
    'DEV=%d' % info['dev'],
    'LEVEL=%s' % info['level'],
  ]
  _writeText(path, str.join('\n', [*comments, *settings, '']))


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#  STATES  # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def stateOf(info: dict) -> str:
  """
  Return the state of 'VERSION': 'none' while no level is locked, 'dev'
  while a level is locked and no rc is out, 'rc' once the rc0 of the
  locked level is out.
  """
  if info['level'] == NO_LEVEL:
    return NO_LEVEL
  return 'rc' if info['rc'] else 'dev'


def lastRelease(info: dict) -> str:
  """Return the last full release, as 'X.Y.Z'"""
  return '%d.%d.%d' % (info['major'], info['minor'], info['micro'] - 1)


def target(info: dict, level: str) -> str:
  """
  Return the release a level leads to from the last full release X.Y.Z:
  X.Y.(Z+1) for micro, X.(Y+1).0 for minor and (X+1).0.0 for major.
  """
  if level == 'micro':
    return '%d.%d.%d' % (info['major'], info['minor'], info['micro'])
  if level == 'minor':
    return '%d.%d.0' % (info['major'], info['minor'] + 1)
  return '%d.0.0' % (info['major'] + 1,)


def _kindOf(info: dict, button: str) -> str:
  """
  The table of Asger's design of 2026-11-09, for one button in the state
  of 'info'. With no level locked, only a dev press runs, armed. In a dev
  cycle, a dev press of the locked level is free, of a higher level armed
  and of a lower one refused; the rc of the locked level is armed; every
  other press is refused. In an rc cycle, the rc of the locked level is
  free, its lts armed, and every other press refused.
  """
  kind, level = buttonKind(button), buttonLevel(button)
  state = stateOf(info)
  if state == NO_LEVEL:
    return ARMED if kind == 'dev' else REFUSED
  locked = info['level']
  if state == 'dev':
    if kind == 'dev':
      if level == locked:
        return FREE
      if LEVELS.index(level) > LEVELS.index(locked):
        return ARMED
      return REFUSED
    if kind == 'rc' and level == locked:
      return ARMED
    return REFUSED
  if kind == 'dev' or level != locked:
    return REFUSED
  return FREE if kind == 'rc' else ARMED


def _nameOf(info: dict, button: str) -> str:
  """
  Return the version a press accepted in the state of 'info' publishes:
  the devN of the target of the button's level, N being 0 when the press
  opens or climbs to the level; its rcN; or the target itself for lts.
  """
  kind, level = buttonKind(button), buttonLevel(button)
  version = target(info, level)
  if kind == 'dev':
    dev = info['dev'] if info['level'] == level else 0
    return '%s-dev%d' % (version, dev)
  if kind == 'rc':
    return '%s-rc%d' % (version, info['rc'])
  return version


def _stateSentence(info: dict) -> str:
  state = stateOf(info)
  if state == NO_LEVEL:
    infoSpec = """No cycle is open since the last release, %s
    (LEVEL=none)."""
    return _flat(infoSpec % lastRelease(info))
  locked = info['level']
  version = target(info, locked)
  if state == 'dev':
    infoSpec = """A dev cycle is open for %s (LEVEL=%s), last published as
    %s-dev%d."""
    return _flat(infoSpec % (version, locked, version, info['dev'] - 1))
  infoSpec = """A release candidate cycle is open for %s (LEVEL=%s), last
  published as %s-rc%d."""
  return _flat(infoSpec % (version, locked, version, info['rc'] - 1))


def _reasonSentence(info: dict, button: str) -> str:
  kind = buttonKind(button)
  state = stateOf(info)
  if state == NO_LEVEL:
    if kind == 'rc':
      return 'A release candidate needs a dev cycle before it.'
    return _flat(_NEEDS_RC)
  locked = info['level']
  if state == 'dev':
    if kind == 'dev':
      return _flat("""A dev release may stay at the locked level or climb
      to a higher one, never step down.""")
    if kind == 'rc':
      infoSpec = """The release candidate of this cycle comes from '%s'."""
      return infoSpec % buttonOf('rc', locked)
    return _flat(_NEEDS_RC)
  if kind == 'dev':
    return _flat("""A release candidate freezes the scope: release what it
    froze, then open the next line.""")
  infoSpec = """This cycle continues through '%s' and ends through '%s'."""
  return infoSpec % (buttonOf('rc', locked), buttonOf('lts', locked))


def _acceptedSentence(info: dict, accepted: tuple) -> str:
  entries = []
  for button in accepted:
    if _kindOf(info, button) == FREE:
      need = 'no safety'
    else:
      need = 'needs %s.safety' % safetyName(button)
    entries.append('%s (%s, %s)' % (button, _nameOf(info, button), need))
  return 'Accepted now: %s.' % str.join(', ', entries)


def decide(info: dict, button: str) -> Press:
  """
  Every press of every button must be decided by one rule from the state
  of 'VERSION' alone: whether it may run, whether it needs its safety,
  what it publishes, and, when it is refused, why, in words that name the
  state and the buttons that would be accepted instead.

  Implementation
  --------------

  The kind follows the table in '_kindOf', the name '_nameOf'. 'info' is
  not changed. 'safety_check.py' turns an armed press into a verdict by
  reading the safety, 'version_get.py' prints the name, and
  'version_bump.py' advances the counters through 'advance'.

  Parameters
  ----------

  info : dict
    The settings, as 'readVersion' gives them.

  button : str
    One of 'BUTTONS'.

  Returns
  -------

  Press
    The decision.
  """
  accepted = (*(b for b in BUTTONS if _kindOf(info, b) != REFUSED),)
  kind = _kindOf(info, button)
  if kind == REFUSED:
    message = str.join(' ', [
      "'%s' is refused." % button,
      _stateSentence(info),
      _reasonSentence(info, button),
      _acceptedSentence(info, accepted),
    ])
    return Press(button, kind, None, None, accepted, message)
  name = _nameOf(info, button)
  if kind == FREE:
    message = "'%s' publishes %s and needs no safety." % (button, name)
    return Press(button, kind, name, None, accepted, message)
  safety = safetyName(button)
  infoSpec = """'%s' publishes %s and needs %s.safety to read 'ALLOW'."""
  message = infoSpec % (button, name, safety)
  return Press(button, kind, name, safety, accepted, message)


def advance(info: dict, button: str) -> dict:
  """
  Once a press has published, 'VERSION' must record it, so the next press
  is decided from the new state.

  Implementation
  --------------

  A dev press of the locked level adds one to DEV; a dev press that opens
  a cycle, or climbs to a higher level, locks its level and sets DEV to 1,
  its dev0 being out. An rc press adds one to RC. An lts press moves the
  counters as the lts buttons always have: MICRO up for micro; MINOR up
  and MICRO to 1 for minor; MAJOR up, MINOR to 0 and MICRO to 1 for
  major; RC and DEV to 0 and LEVEL to 'none'. 'info' is not changed.

  Parameters
  ----------

  info : dict
    The settings, as 'readVersion' gives them.

  button : str
    One of 'BUTTONS'.

  Returns
  -------

  dict
    The settings after the press.

  Raises
  ------

  ReleaseRefused
    The press is refused in this state, with the message of 'decide'.
  """
  press = decide(info, button)
  if press.kind == REFUSED:
    raise ReleaseRefused(press.message)
  out = dict(info)
  kind, level = buttonKind(button), buttonLevel(button)
  if kind == 'dev':
    if out['level'] == level:
      out['dev'] += 1
    else:
      out['level'] = level
      out['dev'] = 1
  elif kind == 'rc':
    out['rc'] += 1
  else:
    if level == 'micro':
      out['micro'] += 1
    elif level == 'minor':
      out['minor'] += 1
      out['micro'] = 1
    else:
      out['major'] += 1
      out['minor'] = 0
      out['micro'] = 1
    out.update(rc=0, dev=0, level=NO_LEVEL)
  validate(out)
  return out

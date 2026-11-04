"""A small client of Minecraft 1.7.10's protocol (5), for building test worlds on a vanilla server.

It does only what a client may: log in (offline mode), answer keep-alives, confirm the server's position packets,
send position packets 20 times a second (a 1.7.10 player's own update runs once for each), chat commands, the
command block's "set command" message (MC|AdvCdm), creative inventory slots, and the respawn request after the End.
"""
import json
import math
import socket
import struct
import threading
import time

from nbt import gzip_bytes

EYE = 1.62


def varint(n):
    out = bytearray()
    n &= 0xFFFFFFFF
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def text(s):
    raw = s.encode('utf-8')
    return varint(len(raw)) + raw


class Buffer:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, n):
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def varint(self):
        result = 0
        shift = 0
        while True:
            b = self.data[self.pos]
            self.pos += 1
            result |= (b & 0x7F) << shift
            if not b & 0x80:
                break
            shift += 7
        if result & 0x80000000:
            result -= 1 << 32
        return result

    def number(self, fmt):
        size = struct.calcsize(fmt)
        return struct.unpack('>' + fmt, self.take(size))[0]

    def text(self):
        return self.take(self.varint()).decode('utf-8')


def chat_key(message):
    """A chat message's translation key and arguments, or (None, its text)."""
    try:
        data = json.loads(message)
    except ValueError:
        return None, message
    if isinstance(data, dict) and 'translate' in data:
        return data['translate'], data.get('with', [])
    return None, message


def flat(component):
    """A chat component's plain text, roughly."""
    if isinstance(component, str):
        return component
    if isinstance(component, dict):
        if 'translate' in component:
            return component['translate'] + '(' + ', '.join(flat(c) for c in component.get('with', [])) + ')'
        return component.get('text', '') + ''.join(flat(c) for c in component.get('extra', []))
    if isinstance(component, list):
        return ''.join(flat(c) for c in component)
    return str(component)


class Bot:
    def __init__(self, host, port, name, log=print):
        self.host, self.port, self.name, self.log = host, port, name, log
        self.sock = None
        self.send_lock = threading.Lock()
        self.state_lock = threading.Condition()
        self.x = self.y = self.z = 0.0
        self.yaw = self.pitch = 0.0
        self.dimension = None
        self.gamemode = None
        self.entity_id = None
        self.spawn = None
        self.health = 20.0
        self.positions = 0          # the server's position packets so far
        self.respawns = 0           # dimension changes (respawn packets) so far
        self.responses = []         # command responses, in order: (key, args)
        self.admin = []             # command blocks' output to operators
        self.other_chat = []
        self.disconnected = None
        self.credits = 0
        self.running = False
        self.moving = True
        self.positions_at_respawn = 0
        self.debug = False
        self.marks = {}
        self.mark_count = 0

    # ---------------------------------------------------------------- the connection

    def connect(self, timeout=60):
        self.sock = socket.create_connection((self.host, self.port), timeout=30)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._send(0x00, varint(5) + text(self.host) + struct.pack('>H', self.port) + varint(2))
        self._send(0x00, text(self.name))
        while True:
            pid, buf = self._read()
            if pid == 0x02:
                uuid = buf.text()
                self.log('logged in as %s (%s)' % (buf.text(), uuid))
                break
            if pid == 0x00:
                raise RuntimeError('login refused: ' + buf.text())
            if pid == 0x01:
                raise RuntimeError('the server wants encryption (online mode)')
        self.running = True
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._mover, daemon=True).start()
        self.wait_for(lambda: self.positions > 0, timeout, 'the first position')

    def close(self):
        self.running = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()

    def _send(self, pid, payload=b''):
        body = varint(pid) + payload
        with self.send_lock:
            self.sock.sendall(varint(len(body)) + body)

    def _read_exact(self, n):
        data = bytearray()
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError('the server closed the connection')
            data += chunk
        return bytes(data)

    def _read(self):
        length = 0
        shift = 0
        while True:
            b = self._read_exact(1)[0]
            length |= (b & 0x7F) << shift
            if not b & 0x80:
                break
            shift += 7
        buf = Buffer(self._read_exact(length))
        return buf.varint(), buf

    def _reader(self):
        try:
            while self.running:
                pid, buf = self._read()
                self._handle(pid, buf)
        except Exception as e:  # noqa: BLE001 (a reader that dies quietly leaves the bot waiting forever)
            if self.running:
                self.disconnected = self.disconnected or str(e)
                self.log('connection ended: %s' % self.disconnected)
            self.running = False
            with self.state_lock:
                self.state_lock.notify_all()

    def _handle(self, pid, buf):
        if pid == 0x00:      # keep-alive
            self._send(0x00, struct.pack('>i', buf.number('i')))
        elif pid == 0x01:    # join game
            self.entity_id = buf.number('i')
            self.gamemode = buf.number('B')
            self.dimension = buf.number('b')
        elif pid == 0x02:    # chat
            raw = buf.text()
            if self.debug:
                self.log('chat: ' + raw[:300])
            key, args = chat_key(raw)
            with self.state_lock:
                if key == 'commands.generic.deprecatedId':
                    # a warning that comes along with numeric block ids' answers, not an answer itself
                    self.other_chat.append((key, args))
                elif key is not None and (key.startswith('commands.') or key.startswith('advMode.')):
                    self.responses.append((key, args))
                elif key == 'chat.type.admin':
                    self.admin.append(args)
                elif key == 'chat.type.emote' and 'unitTAS-mark-' in raw:
                    self.marks[raw[raw.index('unitTAS-mark-'):].split('"')[0]] = len(self.responses)
                else:
                    self.other_chat.append((key, args))
                self.state_lock.notify_all()
        elif pid == 0x05:    # spawn position
            self.spawn = (buf.number('i'), buf.number('i'), buf.number('i'))
        elif pid == 0x06:    # health
            self.health = buf.number('f')
            if self.health <= 0.0:
                self.log('died; asking to respawn')
                self._send(0x16, struct.pack('>b', 0))
        elif pid == 0x07:    # respawn (another dimension)
            with self.state_lock:
                self.dimension = buf.number('i')
                buf.number('B')
                self.gamemode = buf.number('B')
                self.respawns += 1
                self.positions_at_respawn = self.positions
                self.state_lock.notify_all()
        elif pid == 0x08:    # position and look: y is the eyes
            x, y, z = buf.number('d'), buf.number('d'), buf.number('d')
            yaw, pitch = buf.number('f'), buf.number('f')
            with self.state_lock:
                self.x, self.y, self.z = x, y - EYE, z
                self.yaw, self.pitch = yaw, pitch
                self._send_position(look=True)
                self.positions += 1
                self.state_lock.notify_all()
        elif pid == 0x2B:    # game state: 4 is the End's credits
            reason = buf.number('B')
            if reason == 4:
                self.credits += 1
                self.log('the credits; asking to respawn')
                self._send(0x16, struct.pack('>b', 0))
            elif reason == 3:
                self.gamemode = int(buf.number('f'))
        elif pid == 0x40:    # disconnect
            self.disconnected = buf.text()
            self.running = False

    def _send_position(self, look=False):
        if look:
            self._send(0x06, struct.pack('>ddddffB', self.x, self.y, self.y + EYE, self.z, self.yaw, self.pitch, 1))
        else:
            self._send(0x04, struct.pack('>ddddB', self.x, self.y, self.y + EYE, self.z, 1))

    def _mover(self):
        while self.running:
            # as a real client: position packets only once in play, after the server's first position
            if self.moving and self.positions > 0:
                with self.state_lock:
                    try:
                        self._send_position()
                    except OSError:
                        return
            time.sleep(0.05)

    def wait_for(self, condition, timeout, what):
        deadline = time.time() + timeout
        with self.state_lock:
            while not condition():
                if not self.running:
                    raise RuntimeError('disconnected while waiting for %s: %s' % (what, self.disconnected))
                left = deadline - time.time()
                if left <= 0:
                    raise TimeoutError('no %s in %d s' % (what, timeout))
                self.state_lock.wait(min(left, 0.5))

    def ticks(self, n):
        time.sleep(n * 0.05)

    # ---------------------------------------------------------------- commands

    def commands(self, lines, window=100, timeout=300):
        """Chat commands (each at most 100 characters), pipelined; returns the failures: [(command, key, args)].

        Most commands answer the player who ran them, but not all (1.7.10's /gamemode on oneself only changes the
        game mode), so the batch ends with a /me marker: what came before it is the batch's. When every command
        answered, each failure is matched to its command; otherwise the command shows as "?".
        """
        lines = list(lines)
        with self.state_lock:
            base = len(self.responses)
        deadline = time.time() + timeout
        for sent, line in enumerate(lines):
            if len(line) > 100:
                raise ValueError('a chat command over 100 characters: ' + line)
            # at most `window` unanswered (a silent command only holds a place until a few seconds pass)
            try:
                self.wait_for(lambda: sent - (len(self.responses) - base) < window, 5, 'room in the window')
            except TimeoutError:
                pass
            self._send(0x01, text(line))
        self.mark_count += 1
        mark = 'unitTAS-mark-%d' % self.mark_count
        self._send(0x01, text('/me ' + mark))
        self.wait_for(lambda: mark in self.marks, max(5, deadline - time.time()), 'the end of a batch of %d commands' % len(lines))
        with self.state_lock:
            answers = self.responses[base:self.marks[mark]]
        failures = []
        if len(answers) == len(lines):
            for line, (key, args) in zip(lines, answers):
                if not _succeeded(key):
                    failures.append((line, key, [flat(a) for a in args]))
        else:
            for key, args in answers:
                if not _succeeded(key):
                    failures.append(('? (%d answers to %d commands)' % (len(answers), len(lines)), key, [flat(a) for a in args]))
        return failures

    def command(self, line):
        """One command; long ones through a command block (see long_command). Returns the failures."""
        if len(line) <= 100:
            return self.commands([line])
        return self.long_command(line)

    def long_command(self, line, at=None):
        """A command of any length, run by a command block set by this player, powered, then removed.

        It runs in this player's dimension, where the command block is: give it absolute coordinates.
        """
        if at is None:
            at = (self.x, self.y + 3, self.z)
        # floor, not int(): int() rounds negative coordinates towards 0, into the next block
        x, y, z = (int(math.floor(c)) for c in at)
        failures = self.commands(['/setblock %d %d %d command_block 0 replace' % (x, y, z)])
        if failures:
            return [(line, 'command block not placed: ' + failures[0][1], failures[0][2])]
        with self.state_lock:
            base = len(self.responses)
            admin = len(self.admin)
        payload = struct.pack('>biii', 0, x, y, z) + text(line)
        self._send(0x17, text('MC|AdvCdm') + struct.pack('>h', len(payload)) + payload)
        self.wait_for(lambda: len(self.responses) > base, 10, 'the command block to take its command')
        if self.responses[base][0] != 'advMode.setCommand.success':
            return [(line, self.responses[base][0], [])]
        self.commands(['/setblock %d %d %d redstone_block 0 replace' % (x, y + 1, z)])
        # its output to operators says how it went (the command block runs one tick after it is powered)
        try:
            self.wait_for(lambda: len(self.admin) > admin, 10, 'the command block to run')
            result = self.admin[admin]
        except TimeoutError:
            result = ['?', {'translate': 'no output'}]
        self.commands(['/setblock %d %d %d air 0 replace' % (x, y + 1, z), '/setblock %d %d %d air 0 replace' % (x, y, z)])
        said = result[1] if len(result) > 1 else {}
        key = said.get('translate') if isinstance(said, dict) else None
        if key is None or not _succeeded(key):
            return [(line, key or flat(said), [flat(a) for a in (said.get('with', []) if isinstance(said, dict) else [])])]
        return []

    # ---------------------------------------------------------------- moving and the inventory

    def teleport(self, x, y, z, timeout=20):
        """Moves by /tp and waits for the server's position packet."""
        with self.state_lock:
            before = self.positions
        failures = self.commands(['/tp %s %.2f %.2f %.2f' % (self.name, x, y, z)])
        if failures:
            raise RuntimeError('tp failed: %s' % (failures,))
        self.wait_for(lambda: self.positions > before, timeout, 'the position after /tp')

    def set_slot(self, slot, item_id, count=1, damage=0, tag=None):
        """A creative player's slot in its own inventory (5-8 armour, 9-35 main, 36-44 the hotbar)."""
        data = struct.pack('>hhbh', slot, item_id, count, damage)
        if tag is None:
            data += struct.pack('>h', -1)
        else:
            raw = gzip_bytes('', tag)
            data += struct.pack('>h', len(raw)) + raw
        self._send(0x10, data)

    def wait_dimension_change(self, before, timeout=60):
        self.wait_for(lambda: self.respawns > before, timeout, 'the dimension change')
        # the position in the new dimension follows the respawn packet (it may be in already)
        self.wait_for(lambda: self.positions > self.positions_at_respawn, timeout, 'the position in the new dimension')


def _succeeded(key):
    if key is None:
        return False
    if key == 'commands.setblock.noChange':
        return True  # the block was already that
    bad = ('.failed', '.outOfWorld', '.notFound', '.tagError', '.usage', '.exception', '.permission',
           'generic.', '.invalid', '.noItem', '.notSafe', 'Error')
    return not any(b in key for b in bad)

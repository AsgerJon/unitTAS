"""NBT as 1.7.10 writes it: named tags, gzip files (level.dat, player data) and region files (.mca).

A tag is a (type, value) pair; a compound's value is a dict (in order), a list's value is (element type, [values]).
Short helpers build tags: byte(1), short(373), string("x"), compound(Items=lst(COMPOUND, [...]), ...).
"""
import gzip
import io
import os
import struct
import zlib

END, BYTE, SHORT, INT, LONG, FLOAT, DOUBLE, BYTE_ARRAY, STRING, LIST, COMPOUND, INT_ARRAY = range(12)

_FORMATS = {BYTE: 'b', SHORT: 'h', INT: 'i', LONG: 'q', FLOAT: 'f', DOUBLE: 'd'}


def byte(v):
    return (BYTE, int(v))


def short(v):
    return (SHORT, int(v))


def int_(v):
    return (INT, int(v))


def long_(v):
    return (LONG, int(v))


def float_(v):
    return (FLOAT, float(v))


def double(v):
    return (DOUBLE, float(v))


def string(v):
    return (STRING, str(v))


def lst(kind, values):
    """A list of tags of one kind: values are (kind, value) tags or bare values."""
    return (LIST, (kind, [v[1] if isinstance(v, tuple) and len(v) == 2 and v[0] == kind else v for v in values]))


def compound(**fields):
    return (COMPOUND, dict(fields))


# ---------------------------------------------------------------- reading


class _Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, n):
        chunk = self.data[self.pos:self.pos + n]
        if len(chunk) != n:
            raise ValueError('NBT ends early')
        self.pos += n
        return chunk

    def number(self, fmt):
        return struct.unpack('>' + fmt, self.take(struct.calcsize(fmt)))[0]

    def text(self):
        return self.take(self.number('H')).decode('utf-8', 'surrogateescape')

    def payload(self, kind):
        if kind in _FORMATS:
            return self.number(_FORMATS[kind])
        if kind == BYTE_ARRAY:
            return self.take(self.number('i'))
        if kind == STRING:
            return self.text()
        if kind == LIST:
            inner = self.number('b')
            count = self.number('i')
            return (inner, [self.payload(inner) for _ in range(count)])
        if kind == COMPOUND:
            fields = {}
            while True:
                t = self.number('b')
                if t == END:
                    return fields
                name = self.text()
                fields[name] = (t, self.payload(t))
        if kind == INT_ARRAY:
            count = self.number('i')
            return list(struct.unpack('>%di' % count, self.take(4 * count)))
        raise ValueError('unknown tag type %d' % kind)


def read(data):
    """The root tag of uncompressed NBT bytes: (name, (COMPOUND, fields))."""
    reader = _Reader(data)
    kind = reader.number('b')
    name = reader.text()
    return name, (kind, reader.payload(kind))


def read_gzip(path):
    with gzip.open(path, 'rb') as f:
        return read(f.read())


# ---------------------------------------------------------------- writing


def _write_payload(out, kind, value):
    if kind in _FORMATS:
        out.write(struct.pack('>' + _FORMATS[kind], value))
    elif kind == BYTE_ARRAY:
        out.write(struct.pack('>i', len(value)))
        out.write(bytes(value))
    elif kind == STRING:
        raw = value.encode('utf-8', 'surrogateescape')
        out.write(struct.pack('>H', len(raw)))
        out.write(raw)
    elif kind == LIST:
        inner, items = value
        out.write(struct.pack('>bi', inner if items else (inner or END), len(items)))
        for item in items:
            _write_payload(out, inner, item)
    elif kind == COMPOUND:
        for name, (t, v) in value.items():
            out.write(struct.pack('>b', t))
            _write_payload(out, STRING, name)
            _write_payload(out, t, v)
        out.write(b'\x00')
    elif kind == INT_ARRAY:
        out.write(struct.pack('>i', len(value)))
        out.write(struct.pack('>%di' % len(value), *value))
    else:
        raise ValueError('unknown tag type %d' % kind)


def write(name, tag):
    out = io.BytesIO()
    out.write(struct.pack('>b', tag[0]))
    _write_payload(out, STRING, name)
    _write_payload(out, tag[0], tag[1])
    return out.getvalue()


def write_gzip(path, name, tag):
    tmp = path + '.tmp'
    with gzip.open(tmp, 'wb') as f:
        f.write(write(name, tag))
    os.replace(tmp, path)


def gzip_bytes(name, tag):
    """As 1.7.10's CompressedStreamTools.compress: an item's NBT in a packet."""
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode='wb') as f:
        f.write(write(name, tag))
    return out.getvalue()


# ---------------------------------------------------------------- regions


def region_chunks(path):
    """Each saved chunk of a region file: (chunk x, chunk z, root compound fields)."""
    with open(path, 'rb') as f:
        data = f.read()
    if len(data) < 8192:
        return
    base = os.path.basename(path).split('.')
    rx, rz = int(base[1]), int(base[2])
    for index in range(1024):
        loc = struct.unpack('>I', data[index * 4:index * 4 + 4])[0]
        offset = loc >> 8
        if offset == 0:
            continue
        start = offset * 4096
        length = struct.unpack('>I', data[start:start + 4])[0]
        kind = data[start + 4]
        raw = data[start + 5:start + 4 + length]
        blob = zlib.decompress(raw) if kind == 2 else gzip.decompress(raw)
        _, (_, root) = read(blob)
        yield rx * 32 + index % 32, rz * 32 + index // 32, root


def world_chunks(world, dimension):
    """Every saved chunk of one dimension of a world folder: (chunk x, chunk z, root fields)."""
    folder = {0: 'region', -1: 'DIM-1/region', 1: 'DIM1/region'}[dimension]
    directory = os.path.join(world, folder)
    if not os.path.isdir(directory):
        return
    for name in sorted(os.listdir(directory)):
        if name.endswith('.mca'):
            yield from region_chunks(os.path.join(directory, name))


def section_blocks(level):
    """A chunk's blocks: {(x, y, z) in the world: (id, meta)} for every non-air block."""
    cx = level['xPos'][1]
    cz = level['zPos'][1]
    blocks = {}
    for section in level.get('Sections', (LIST, (COMPOUND, [])))[1][1]:
        sy = section['Y'][1]
        ids = section['Blocks'][1]
        add = section.get('Add', (BYTE_ARRAY, b''))[1]
        data = section['Data'][1]
        for i in range(4096):
            block = ids[i]
            if add:
                block |= ((add[i >> 1] >> ((i & 1) * 4)) & 0xF) << 8
            if block == 0:
                continue
            meta = (data[i >> 1] >> ((i & 1) * 4)) & 0xF
            x = i & 15
            z = (i >> 4) & 15
            y = i >> 8
            blocks[(cx * 16 + x, sy * 16 + y, cz * 16 + z)] = (block, meta)
    return blocks

#!/usr/bin/env python3
"""Vanilla 1.7.10 worlds for unitTAS's save mode (./unittas.sh oldsaves).

Each world is made by Mojang's 1.7.10 server, headless, and built by a scripted player (mcbot.py): an overworld house
and a block sweep, a Nether room, an End hut; then the player is left in one of the three dimensions with a full
inventory and effects. The world is then made a singleplayer save (the player in level.dat) in run/oldsaves/vanilla/,
with its building list, and checked: the saved region files hold what was built.

Needs run/oldsaves/server/minecraft_server.1.7.10.jar and the user's own run/oldsaves/server/eula.txt.
    python3 oldsaves/make_vanilla_worlds.py [world ...]     (default: all three)
"""
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import nbt  # noqa: E402
from nbt import BYTE, COMPOUND, INT, SHORT, STRING, byte, compound, int_, lst, short, string  # noqa: E402
from mcbot import Bot  # noqa: E402
from vanilla_server import Server, offline_uuid  # noqa: E402

ROOT = os.path.dirname(HERE)
OLDSAVES = os.path.join(ROOT, 'run', 'oldsaves')
JAR = os.path.join(OLDSAVES, 'server', 'minecraft_server.1.7.10.jar')
OUT = os.path.join(OLDSAVES, 'vanilla')
BOT = 'Builder'

WORLDS = [
    dict(folder='vanilla-overworld', name='Vanilla: the player in the overworld', seed=17102026, type='DEFAULT',
         last='overworld', mode=0, port=25621),
    dict(folder='vanilla-nether', name='Vanilla: the player in the Nether', seed=-4417102026, type='LARGEBIOMES',
         last='nether', mode=0, port=25622),
    dict(folder='vanilla-end', name='Vanilla: the player in the End', seed=26031710, type='FLAT',
         last='end', mode=1, port=25623),
]


def log(*args):
    print('[%s]' % time.strftime('%H:%M:%S'), *args, flush=True)


# ---------------------------------------------------------------- NBT as commands write it (1.7.10's JsonToNBT)


def mojangson(tag):
    kind, value = tag
    if kind == nbt.BYTE:
        return '%db' % value
    if kind == nbt.SHORT:
        return '%ds' % value
    if kind == nbt.INT:
        return '%d' % value
    if kind == nbt.LONG:
        return '%dL' % value
    if kind == nbt.FLOAT:
        return '%sf' % repr(float(value))
    if kind == nbt.DOUBLE:
        return '%sd' % repr(float(value))
    if kind == nbt.STRING:
        return '"%s"' % value.replace('\\', '\\\\').replace('"', '\\"')
    if kind == nbt.INT_ARRAY:
        return '[' + ','.join(str(v) for v in value) + ']'
    if kind == nbt.LIST:
        inner, items = value
        return '[' + ','.join(mojangson((inner, v)) for v in items) + ']'
    if kind == nbt.COMPOUND:
        return '{' + ','.join('%s:%s' % (k, mojangson(v)) for k, v in value.items()) + '}'
    raise ValueError(kind)


def item(item_id, count=1, damage=0, slot=None, **tag):
    fields = {}
    if slot is not None:
        fields['Slot'] = byte(slot)
    fields['id'] = short(item_id)
    fields['Count'] = byte(count)
    fields['Damage'] = short(damage)
    if tag:
        fields['tag'] = compound(**tag)
    return (COMPOUND, fields)


def items(*stacks):
    """Stacks into slots 0, 1, 2, ... (each an item(...) without a slot)."""
    out = []
    for slot, (_, fields) in enumerate(stacks):
        f = {'Slot': byte(slot)}
        f.update(fields)
        out.append(f)
    return lst(COMPOUND, out)


def enchants(*pairs):
    return lst(COMPOUND, [compound(id=short(i), lvl=short(l)) for i, l in pairs])


def effects(*triples):
    return lst(COMPOUND, [compound(Id=byte(i), Amplifier=byte(a), Duration=int_(d), Ambient=byte(0)) for i, a, d in triples])


def named(name, *lore):
    d = {'Name': string(name)}
    if lore:
        d['Lore'] = lst(STRING, [string(x) for x in lore])
    return compound(**d)


# 1.7.10's potion damage values: bits 0-3 the effect, 32 level II, 64 extended, 8192 drinkable, 16384 splash
POTIONS = [0, 16, 32, 64, 8192, 8193, 8257, 8225, 16385, 8194, 8226, 8195, 8259, 8196, 8228, 8197, 8229, 8198, 8262,
           8200, 8201, 8233, 8202, 8204, 8205, 8206, 8270, 16388, 16396, 16418, 8289]


def potion(damage, count=1):
    return item(373, count, damage)


CUSTOM_POTION = item(373, 1, 8192, CustomPotionEffects=effects((5, 1, 1200), (1, 0, 2400)),
                     display=named('A custom potion', 'strength II and speed, by CustomPotionEffects'))
SWORD = item(276, 1, 0, ench=enchants((16, 5), (20, 2), (21, 3)), display=named('Old Sword', 'made in vanilla 1.7.10'))
BOOK = item(387, 1, 0, title=string('Old book'), author=string(BOT),
            pages=lst(STRING, [string('Written in vanilla 1.7.10.'), string('Page two.')]))
ENCHANTED_BOOK = item(403, 1, 0, StoredEnchantments=enchants((48, 5)))
LEATHER = item(299, 1, 0, display=compound(color=int_(0x3366CC)))
HEAD = item(397, 1, 3, SkullOwner=string('Notch'))
ROCKET = item(401, 3, 0, Fireworks=compound(Flight=byte(2), Explosions=lst(COMPOUND, [compound(
    Type=byte(1), Colors=(nbt.INT_ARRAY, [0xFF0000, 0x00FF00]), Flicker=byte(1))])))


# ---------------------------------------------------------------- building helpers


class Builder:
    def __init__(self, bot):
        self.bot = bot
        self.failures = []
        self.pending = []
        self.long = []

    def cmd(self, line):
        """Queued; short ones go in batches, long ones through a command block, all in order at flush()."""
        self.pending.append(line)

    def flush(self):
        before = len(self.failures)
        self._flush()
        new = self.failures[before:]
        if new:
            kinds = {}
            for _, key, _ in new:
                kinds[key] = kinds.get(key, 0) + 1
            log('  %d commands failed: %s; first: %s' % (len(new), kinds, new[0]))

    def _flush(self):
        batch = []
        for line in self.pending:
            if len(line) <= 100:
                batch.append(line)
                continue
            if batch:
                self.failures += self.bot.commands(batch)
                batch = []
            self.failures += self.bot.long_command(line, at=self.scratch)
        if batch:
            self.failures += self.bot.commands(batch)
        self.pending = []

    def set(self, x, y, z, block, meta=0, tag=None):
        line = '/setblock %d %d %d %s %d replace' % (x, y, z, block, meta)
        if tag is not None:
            line += ' ' + mojangson(tag)
        self.cmd(line)

    def box(self, x1, y1, z1, x2, y2, z2, block, meta=0, hollow=False):
        for x in range(min(x1, x2), max(x1, x2) + 1):
            for y in range(min(y1, y2), max(y1, y2) + 1):
                for z in range(min(z1, z2), max(z1, z2) + 1):
                    edge = x in (x1, x2) or y in (y1, y2) or z in (z1, z2)
                    if not hollow or edge:
                        self.set(x, y, z, block, meta)

    def summon(self, kind, x, y, z, tag=None):
        line = '/summon %s %.4f %.4f %.4f' % (kind, x, y, z)
        if tag is not None:
            line += ' ' + mojangson(tag)
        self.cmd(line)

    def hanging(self, kind, wall_x, wall_y, wall_z, direction, **fields):
        """An item frame or painting on a wall block's face: 0 south (+z), 1 west (-x), 2 north (-z), 3 east (+x).

        Summoned 0.8125 out from the wall block's centre: 1.7.10's /summon sets a hanging entity's position after
        reading it (its box then 0.5 wide around it), and a box in the wall fails its surface check and drops it.
        On loading, the game puts it back from TileX/Y/Z and Direction.
        """
        dx, dz = {0: (0, 1), 1: (-1, 0), 2: (0, -1), 3: (1, 0)}[direction]
        x = wall_x + 0.5 + dx * 0.8125
        z = wall_z + 0.5 + dz * 0.8125
        tag = dict(Direction=byte(direction), TileX=int_(wall_x), TileY=int_(wall_y), TileZ=int_(wall_z))
        tag.update(fields)
        self.summon(kind, x, wall_y + 0.5, z, compound(**tag))

    def mob(self, kind, x, y, z, **fields):
        fields.setdefault('PersistenceRequired', byte(1))
        self.summon(kind, x + 0.5, y, z + 0.5, compound(**fields))

    def cell(self, x, y, z, w, d, h, kind, roof='stone', glass='glass', **fields):
        """A glass cell (inside w by d, h high) with a solid roof (no sun for the undead), the mob inside."""
        self.box(x - 1, y - 1, z - 1, x + w, y + h, z + d, glass, hollow=True)
        self.box(x - 1, y + h, z - 1, x + w, y + h, z + d, roof)
        if kind:
            self.mob(kind, x + (w - 1) / 2.0, y, z + (d - 1) / 2.0, **fields)


# ---------------------------------------------------------------- the buildings


def house(b, hx, hy, hz):
    """The overworld house (x 0 to 30, z 0 to 24): storage along the north wall, frames on the west wall, the pen and
    its beacon in the middle, rails at z 6, redstone at x 22, mob cells at z 22 and in the east wing (x 25 to 29).
    Nothing overlaps (a cell's glass replaced a brewing stand and a bed's head before, 2026-11-03). Returns its box."""
    X, Y, Z = hx, hy, hz
    b.scratch = (X + 12, Y + 9, Z + 30)
    # shell: stone brick floor and walls, a glass roof (the beacon sees the sky)
    b.box(X, Y, Z, X + 30, Y, Z + 24, 'stonebrick')
    for x in range(X, X + 31):
        for z in (Z, Z + 24):
            for y in range(Y + 1, Y + 6):
                b.set(x, y, z, 'stonebrick')
    for z in range(Z + 1, Z + 24):
        for x in (X, X + 30):
            for y in range(Y + 1, Y + 6):
                b.set(x, y, z, 'stonebrick')
    b.box(X, Y + 6, Z, X + 30, Y + 6, Z + 24, 'glass')
    for x in range(X + 1, X + 30, 4):
        b.set(x, Y + 5, Z + 12, 'glowstone')
    b.flush()
    y = Y + 1
    # storage row along the north wall, facing south
    b.set(X + 2, y, Z + 2, 'chest', 3, compound(Items=items(*[potion(d) for d in POTIONS[:27]])))
    b.set(X + 4, y, Z + 2, 'chest', 3, compound(Items=items(*[potion(d) for d in POTIONS[27:]], CUSTOM_POTION, SWORD,
                                                             BOOK, ENCHANTED_BOOK, LEATHER, HEAD, ROCKET)))
    b.set(X + 5, y, Z + 2, 'chest', 3, compound(Items=items(item(282), item(322, 2, 1), item(383, 3, 50), item(383, 1, 90),
                                                             item(349, 5, 2), item(2256), item(368, 16), item(264, 64))))
    b.set(X + 7, y, Z + 2, 'trapped_chest', 3, compound(Items=items(potion(16385, 3), potion(8197, 2))))
    b.set(X + 8, y, Z + 2, 'trapped_chest', 3, compound(Items=items(item(331, 64), item(76 - 0, 1))))
    b.set(X + 10, y, Z + 2, 'ender_chest', 3)
    b.set(X + 12, y, Z + 2, 'hopper', 0, compound(Items=items(item(266, 10), potion(8201))))
    b.set(X + 14, y, Z + 2, 'dispenser', 1, compound(Items=items(item(262, 64), potion(16388, 2))))
    b.set(X + 16, y, Z + 2, 'dropper', 1, compound(Items=items(item(4, 32))))
    b.set(X + 18, y, Z + 2, 'lit_furnace', 3, compound(Items=items(item(15, 16), item(263, 32)), BurnTime=short(32000),
                                                        CookTime=short(10)))
    b.set(X + 20, y, Z + 2, 'brewing_stand', 0, compound(Items=items(potion(16), potion(16), potion(16), item(372, 4)),
                                                          BrewTime=short(380)))
    b.set(X + 22, y, Z + 2, 'cauldron', 2)
    # item frames on the west wall's inside (facing east), and a painting on the east wall's inside
    framed = [potion(8193), potion(16385), SWORD, item(345), item(347), BOOK, HEAD, item(2257)]
    for i, stack in enumerate(framed):
        b.hanging('ItemFrame', X, y + 1, Z + 4 + i, 3, Item=stack, ItemRotation=byte(i % 4), ItemDropChance=float_(1.0))
    b.hanging('ItemFrame', X, y + 2, Z + 4, 3)
    b.hanging('Painting', X + 30, y + 1, Z + 10, 1, Motive=string('Kebab'))
    b.hanging('Painting', X + 30, y + 1, Z + 12, 1, Motive=string('Aztec'))
    # the beacon on a 3 by 3 of iron (level 1): speed
    b.box(X + 11, Y, Z + 11, X + 13, Y, Z + 13, 'iron_block')
    b.set(X + 12, y, Z + 12, 'beacon', 0, compound(Levels=int_(1), Primary=int_(1), Secondary=int_(0)))
    # signs, jukebox, note block, pots, skulls, a spawner that never wakes
    b.set(X + 2, y, Z + 10, 'standing_sign', 4, compound(Text1=string('Made in'), Text2=string('vanilla 1.7.10'),
                                                          Text3=string(''), Text4=string('by ' + BOT)))
    b.set(X + 1, y + 1, Z + 10, 'wall_sign', 5, compound(Text1=string('A wall sign'), Text2=string(''), Text3=string('old'),
                                                          Text4=string('format')))
    b.set(X + 2, y, Z + 12, 'jukebox', 1, compound(Record=int_(2258), RecordItem=item(2258)))
    b.set(X + 2, y, Z + 14, 'noteblock', 0, compound(note=byte(12)))
    b.set(X + 2, y, Z + 16, 'flower_pot', 0, compound(Item=int_(38), Data=int_(3)))
    b.set(X + 3, y, Z + 16, 'flower_pot', 0, compound(Item=int_(6), Data=int_(1)))
    b.set(X + 2, y, Z + 18, 'skull', 1, compound(SkullType=byte(3), Rot=byte(4),
                                                 Owner=compound(Name=string('Notch'), Id=string('069a79f4-44e9-4726-a5be-fca90e38aaf5'))))
    b.set(X + 3, y, Z + 18, 'skull', 1, compound(SkullType=byte(1), Rot=byte(8)))
    b.set(X + 2, y, Z + 20, 'mob_spawner', 0, compound(EntityId=string('Zombie'), Delay=short(20), MinSpawnDelay=short(200),
                                                       MaxSpawnDelay=short(800), SpawnCount=short(4), MaxNearbyEntities=short(6),
                                                       RequiredPlayerRange=short(0), SpawnRange=short(4)))
    b.set(X + 4, y, Z + 20, 'enchanting_table')
    b.set(X + 6, y, Z + 20, 'anvil', 9)
    b.set(X + 8, y, Z + 20, 'command_block', 0, compound(Command=string('/say made in vanilla 1.7.10')))
    b.set(X + 10, y, Z + 20, 'daylight_detector')
    b.set(X + 14, y, Z + 20, 'bed', 3)
    b.set(X + 15, y, Z + 20, 'bed', 11)
    b.set(X + 17, y, Z + 20, 'bookshelf')
    b.set(X + 18, y, Z + 20, 'crafting_table')
    b.set(X + 19, y, Z + 20, 'cake', 2)
    # doors in the south wall, a trapdoor on it, a fence gate
    b.set(X + 12, y, Z + 24, 'wooden_door', 3)
    b.set(X + 12, y + 1, Z + 24, 'wooden_door', 8)
    b.set(X + 14, y, Z + 24, 'iron_door', 3)
    b.set(X + 14, y + 1, Z + 24, 'iron_door', 8)
    b.set(X + 16, y + 2, Z + 23, 'trapdoor', 0)
    b.set(X + 18, y, Z + 22, 'fence_gate', 0)
    # redstone: a lever on, the piston it pushes out, an idle comparator, repeater and lamp
    b.set(X + 22, y, Z + 16, 'lever', 13)
    b.set(X + 22, y, Z + 15, 'sticky_piston', 1)
    b.set(X + 22, y, Z + 18, 'unpowered_comparator', 0)
    b.set(X + 22, y, Z + 19, 'unpowered_repeater', 2)
    b.set(X + 22, y, Z + 21, 'redstone_lamp')
    # rails and every minecart kind, along z 6
    b.set(X + 1, y, Z + 6, 'golden_rail', 1)
    for x in range(X + 2, X + 22):
        b.set(x, y, Z + 6, 'rail', 1)
    b.set(X + 22, y, Z + 6, 'detector_rail', 1)
    b.set(X + 23, y, Z + 6, 'activator_rail', 1)
    carts = [('MinecartRideable', {}), ('MinecartChest', dict(Items=items(potion(8198), item(264, 3)))),
             ('MinecartFurnace', dict(Fuel=short(0))), ('MinecartTNT', dict(TNTFuse=int_(-1))),
             ('MinecartHopper', dict(Items=items(item(331, 8)), Enabled=byte(1))),
             ('MinecartSpawner', dict(EntityId=string('Pig'), Delay=short(20), MinSpawnDelay=short(200), MaxSpawnDelay=short(800),
                                      SpawnCount=short(1), MaxNearbyEntities=short(1), RequiredPlayerRange=short(0), SpawnRange=short(1))),
             ('MinecartCommandBlock', dict(Command=string('/say a cart')))]
    for i, (kind, fields) in enumerate(carts):
        b.summon(kind, X + 3.5 + i * 2.5, y + 0.1, Z + 6.5, compound(**fields))
    b.summon('Boat', X + 6.5, y + 0.1, Z + 8.5)
    b.flush()
    # the pen (fences, z 9 to 18, x 5 to 19) and its animals
    for x in range(X + 5, X + 20):
        for z in (Z + 9, Z + 18):
            b.set(x, y, z, 'fence')
    for z in range(Z + 9, Z + 19):
        for x in (X + 5, X + 19):
            b.set(x, y, z, 'fence')
    owner = string(str(offline_uuid(BOT)))
    b.mob('Cow', X + 7, y, Z + 11, CustomName=string('Old Daisy'), CustomNameVisible=byte(1))
    b.mob('Pig', X + 9, y, Z + 11, Saddle=byte(1))
    b.mob('Sheep', X + 11, y, Z + 11, Color=byte(14), Sheared=byte(0))
    b.mob('Sheep', X + 13, y, Z + 11, Color=byte(3), Sheared=byte(1))
    b.mob('Chicken', X + 15, y, Z + 11)
    b.mob('MushroomCow', X + 17, y, Z + 11)
    b.mob('EntityHorse', X + 7, y, Z + 15, Type=int_(0), Variant=int_(513), Tame=byte(1), OwnerUUID=owner,
          SaddleItem=item(329), ArmorItem=item(419))
    b.mob('EntityHorse', X + 10, y, Z + 15, Type=int_(1), Tame=byte(1), ChestedHorse=byte(1), OwnerUUID=owner,
          Items=lst(COMPOUND, [dict(Slot=byte(2), **item(373, 1, 8193)[1]), dict(Slot=byte(3), **item(264, 5)[1])]))
    b.mob('EntityHorse', X + 13, y, Z + 15, Type=int_(2), Tame=byte(1), OwnerUUID=owner)
    b.mob('EntityHorse', X + 16, y, Z + 15, Type=int_(4), Tame=byte(1), OwnerUUID=owner)
    b.mob('EntityHorse', X + 17, y, Z + 13, Type=int_(3), Tame=byte(1), OwnerUUID=owner)
    # a horse on a lead to the pen's fence (the knot is made when the horse first updates)
    b.mob('EntityHorse', X + 6, y, Z + 17, Type=int_(0), Variant=int_(2), Leashed=byte(1),
          Leash=compound(X=int_(X + 5), Y=int_(y), Z=int_(Z + 17)))
    b.mob('Wolf', X + 8, y, Z + 13, OwnerUUID=owner, Sitting=byte(1), CollarColor=byte(11), Angry=byte(0))
    b.mob('Ozelot', X + 11, y, Z + 13, OwnerUUID=owner, Sitting=byte(1), CatType=int_(2))
    b.mob('Villager', X + 14, y, Z + 16, Profession=int_(2), Offers=compound(Recipes=lst(COMPOUND, [
        compound(buy=item(388, 5), sell=item(373, 1, 8193), uses=int_(0), maxUses=int_(7)),
        compound(buy=item(388, 2), buyB=item(340, 1), sell=item(403, 1, 0, StoredEnchantments=enchants((34, 3))),
                 uses=int_(1), maxUses=int_(7))])))
    b.flush()
    # mob cells along the east side, x 20 to 23 (stone roofs: no sun on the undead)
    b.cell(X + 21, y, Z + 9, 1, 1, 2, 'Zombie', IsBaby=byte(1), IsVillager=byte(0),
           Equipment=lst(COMPOUND, [item(267)[1], item(301)[1], {}, {}, item(298)[1]]),
           ActiveEffects=effects((1, 1, 1000000), (12, 0, 1000000)), CustomName=string('Speedy'))
    b.cell(X + 21, y, Z + 12, 1, 1, 2, 'Zombie', IsVillager=byte(1))
    b.cell(X + 14, y, Z + 22, 1, 1, 2, 'Skeleton', SkeletonType=byte(0), Equipment=lst(COMPOUND, [item(261)[1], {}, {}, {}, {}]))
    b.cell(X + 20, y, Z + 22, 1, 1, 2, 'Creeper', powered=byte(1))
    b.flush()
    # the rest of the cells in a row behind the pen (z 19 to 22 is busy): along x 5 to 13, z 22
    b.cell(X + 5, y, Z + 22, 1, 1, 3, 'Enderman', carried=short(2), carriedData=short(0))
    b.cell(X + 8, y, Z + 22, 1, 1, 2, 'Witch')
    b.cell(X + 11, y, Z + 22, 1, 1, 2, 'Slime', Size=int_(0))
    b.flush()
    # the east wing: an iron golem and a bat in their own cells, a squid in water, dropped potions behind glass
    b.cell(X + 26, y, Z + 3, 2, 2, 3, 'VillagerGolem', PlayerCreated=byte(1))
    b.cell(X + 26, y, Z + 8, 1, 1, 2, 'Bat', roof='glass')
    b.cell(X + 26, y, Z + 12, 1, 1, 2, None, roof='glass')
    b.set(X + 26, y, Z + 12, 'water')
    b.set(X + 26, y + 1, Z + 12, 'water')
    b.mob('Squid', X + 26, y + 0.2, Z + 12)
    b.cell(X + 26, y, Z + 16, 1, 1, 1, None, roof='glass')
    b.summon('Item', X + 26.5, y + 0.1, Z + 16.5, compound(Item=item(373, 1, 8262), Age=short(-32768), Health=short(5)))
    b.summon('Item', X + 26.5, y + 0.3, Z + 16.5, compound(Item=item(373, 1, 16396), Age=short(-32768), Health=short(5)))
    b.flush()
    return (X, Y, Z, X + 30, Y + 6, Z + 24)


def float_(v):
    return nbt.float_(v)


def _r(a, b):
    return list(range(a, b + 1))


# The metas vanilla 1.7.10 itself makes for each block it places (a world never holds others; some crash vanilla:
# a piston facing "6" indexes past the six directions, 2026-11-03). Left out: fluids, fire, portals, the spawner, the
# piston's moving block, ice and snow (they melt by the sweep's torches), and what changes or pops on random ticks
# (plants, farmland, lit redstone ore), as the check would race vanilla's ticking; and the pressed or powered states a
# scheduled tick undoes (buttons, pressure plates, detector rails), and tripwire hooks attached to no line (vanilla
# corrects them at their next update). Not listed: meta 0 only.
FACING6 = _r(0, 5) + _r(8, 13)
HORIZONTAL = _r(2, 5)
STAIRS = _r(0, 7)
ALL = _r(0, 15)
SWEEP_METAS = {
    3: [0, 1, 2], 5: _r(0, 5), 12: [0, 1], 17: ALL, 18: _r(0, 7), 23: FACING6, 24: [0, 1, 2], 26: _r(0, 3) + _r(8, 11),
    27: FACING6, 28: _r(0, 5), 29: _r(0, 5), 33: _r(0, 5), 34: FACING6, 35: ALL, 43: _r(0, 9), 44: ALL, 46: [0, 1],
    50: _r(1, 5), 53: STAIRS, 54: HORIZONTAL, 55: ALL, 61: HORIZONTAL, 62: HORIZONTAL, 63: ALL, 64: _r(0, 11),
    65: HORIZONTAL, 66: _r(0, 9), 67: STAIRS, 68: HORIZONTAL, 69: ALL, 70: [0], 71: _r(0, 11), 72: [0],
    75: _r(1, 5), 76: _r(1, 5), 77: _r(1, 5), 84: [0, 1], 86: _r(0, 4), 91: _r(0, 4), 92: _r(0, 6),
    93: ALL, 94: ALL, 95: ALL, 96: ALL, 97: _r(0, 5), 98: _r(0, 3), 99: _r(0, 10) + [14, 15], 100: _r(0, 10) + [14, 15],
    107: STAIRS, 108: STAIRS, 109: STAIRS, 114: STAIRS, 117: STAIRS, 118: _r(0, 3), 120: STAIRS, 125: _r(0, 5),
    126: _r(0, 5) + _r(8, 13), 128: STAIRS, 130: HORIZONTAL, 131: _r(0, 3), 132: [0], 134: STAIRS, 135: STAIRS, 136: STAIRS,
    139: [0, 1], 143: _r(1, 5), 144: _r(1, 5), 145: _r(0, 11), 146: HORIZONTAL, 147: [0], 148: [0],
    149: ALL, 150: ALL, 151: [0], 154: [0, 2, 3, 4, 5, 8, 10, 11, 12, 13], 155: _r(0, 4), 156: STAIRS, 157: FACING6,
    158: FACING6, 159: ALL, 160: ALL, 161: [0, 1, 4, 5], 162: [0, 1, 4, 5, 8, 9, 12, 13], 163: STAIRS, 164: STAIRS,
    170: [0, 4, 8], 171: ALL,
}
SWEEP_SKIP = {0, 8, 9, 10, 11, 51, 90, 119, 36, 52, 79, 78, 80, 165, 166, 167, 168, 169,
              6, 31, 32, 37, 38, 39, 40, 59, 60, 74, 81, 83, 104, 105, 106, 111, 115, 127, 141, 142, 175,
              # redstone torches tick randomly, and a torch's update reaches blocks 2 away (the sweep's spacing)
              75, 76}


def sweep(b, sx, sy, sz):
    """Every vanilla block with each meta vanilla makes for it, 2 apart on a stone floor (54 a row). Returns its box."""
    cells = []
    for block in range(1, 176):
        if block in SWEEP_SKIP:
            continue
        for meta in SWEEP_METAS.get(block, [0]):
            cells.append((block, meta))
    b.scratch = (sx - 4, sy + 6, sz - 4)
    for k, (block, meta) in enumerate(cells):
        x = sx + 2 * (k % 54)
        z = sz + 2 * (k // 54)
        b.cmd('/setblock %d %d %d stone 0 replace' % (x, sy - 1, z))
        b.cmd('/setblock %d %d %d %d %d replace' % (x, sy, z, block, meta))
    b.flush()
    rows = (len(cells) + 53) // 54
    log('sweep: %d blocks with their metas, %d rows' % (len(cells), rows))
    return (sx, sy - 1, sz, sx + 107, sy + 1, sz + 2 * rows - 1)


def nether_room(b, ax, ay, az):
    """A nether brick room by the arrival portal: brewing, chests, frames, a beacon, signs, the Nether's mobs."""
    X, Y, Z = ax + 4, ay - 1, az - 7
    b.scratch = (X + 7, Y + 3, Z + 7)
    W, H, D = 14, 8, 14
    b.box(X, Y, Z, X + W, Y + H, Z + D, 'nether_brick', hollow=True)
    b.flush()
    b.box(X + 1, Y + 1, Z + 1, X + W - 1, Y + H - 1, Z + D - 1, 'air')
    for x in range(X + 2, X + W - 1, 4):
        b.set(x, Y + H - 1, Z + 7, 'glowstone')
    b.flush()
    y = Y + 1
    b.set(X + 2, y, Z + 2, 'chest', 3, compound(Items=items(*[potion(d) for d in POTIONS[5:20]], SWORD, ENCHANTED_BOOK)))
    b.set(X + 4, y, Z + 2, 'brewing_stand', 0, compound(Items=items(potion(8193), potion(8257), potion(16385), item(331, 2))))
    b.set(X + 6, y, Z + 2, 'beacon', 0, compound(Levels=int_(0), Primary=int_(3), Secondary=int_(0)))
    b.set(X + 8, y, Z + 2, 'standing_sign', 0, compound(Text1=string('The Nether'), Text2=string(''), Text3=string('vanilla'),
                                                         Text4=string('1.7.10')))
    b.set(X + 10, y, Z + 2, 'ender_chest', 3)
    for i, stack in enumerate([potion(8195), item(369), item(370), item(377)]):
        b.hanging('ItemFrame', X, y + 1, Z + 4 + 2 * i, 3, Item=stack, ItemRotation=byte(i))
    b.flush()
    b.cell(X + 3, y, Z + 5, 1, 1, 3, 'Skeleton', SkeletonType=byte(1), Equipment=lst(COMPOUND, [item(272)[1], {}, {}, {}, {}]))
    b.cell(X + 6, y, Z + 5, 1, 1, 2, 'Blaze')
    b.cell(X + 9, y, Z + 5, 1, 1, 2, 'PigZombie', Anger=short(0), Equipment=lst(COMPOUND, [item(283)[1], {}, {}, {}, {}]))
    b.cell(X + 12, y, Z + 5, 1, 1, 2, 'LavaSlime', Size=int_(1))
    b.flush()
    # the ghast (4 by 4 by 4) in a cell its size
    b.cell(X + 6, y, Z + 8, 4, 4, 4, None)
    b.mob('Ghast', X + 7.5, y + 0.1, Z + 9.5)
    b.flush()
    return (X, Y, Z, X + W, Y + H, Z + D), (X + 2.5, y, Z + 12.5)


def end_hut(b, ex, ey, ez):
    """An obsidian hut by the End's arrival platform (the dragon breaks anything but obsidian, end stone, bedrock)."""
    X, Y, Z = ex + 5, ey - 1, ez - 6
    b.scratch = (X + 6, Y + 3, Z + 6)
    W, H, D = 12, 7, 12
    b.box(X, Y, Z, X + W, Y + H, Z + D, 'obsidian', hollow=True)
    b.box(X + 1, Y, Z + 1, X + W - 1, Y, Z + D - 1, 'end_stone')
    b.flush()
    b.box(X + 1, Y + 1, Z + 1, X + W - 1, Y + H - 1, Z + D - 1, 'air')
    for x in range(X + 2, X + W - 1, 4):
        b.set(x, Y + H - 1, Z + 6, 'glowstone')
    b.flush()
    y = Y + 1
    b.set(X + 2, y, Z + 2, 'chest', 3, compound(Items=items(*[potion(d) for d in POTIONS[18:]], BOOK, HEAD)))
    b.set(X + 4, y, Z + 2, 'ender_chest', 3)
    b.set(X + 6, y, Z + 2, 'standing_sign', 0, compound(Text1=string('The End'), Text2=string(''), Text3=string('vanilla'),
                                                         Text4=string('1.7.10')))
    b.set(X + 8, y, Z + 2, 'brewing_stand', 0, compound(Items=items(potion(8206), item(368))))
    b.set(X + 10, y, Z + 2, 'enchanting_table')
    for i, stack in enumerate([item(368), item(381), potion(8206)]):
        b.hanging('ItemFrame', X, y + 1, Z + 4 + 2 * i, 3, Item=stack, ItemRotation=byte(3 - i))
    b.flush()
    b.cell(X + 4, y, Z + 8, 1, 1, 3, 'Enderman', carried=short(3), carriedData=short(0))
    b.cell(X + 8, y, Z + 8, 1, 1, 2, 'Pig', CustomName=string('Pig in the End'), CustomNameVisible=byte(1))
    b.flush()
    return (X, Y, Z, X + W, Y + H, Z + D), (X + 6.5, y, Z + 5.5)


# ---------------------------------------------------------------- travel


def to_end(bot, b, x, y, z):
    """An end portal block at the player's feet (left in the world, outside the buildings)."""
    bot.teleport(x + 0.5, y, z + 0.5)
    before = bot.respawns
    b.cmd('/setblock %d %d %d stone 0 replace' % (x, y - 1, z))
    b.cmd('/setblock %d %d %d end_portal 0 replace' % (x, y, z))
    b.flush()
    bot.wait_dimension_change(before)
    log('in the End at %.1f %.1f %.1f' % (bot.x, bot.y, bot.z))


def leave_end(bot):
    """Out of the End as players do in a hurry: /kill, then respawn in the overworld."""
    before = bot.respawns
    bot.commands(['/kill'])
    bot.wait_dimension_change(before)
    log('back in the overworld at %.1f %.1f %.1f' % (bot.x, bot.y, bot.z))


def nether_portal(b, px, py, pz):
    """An obsidian frame (inside 2 wide, 3 high, along x) lit by fire."""
    for x in range(px - 1, px + 3):
        b.set(x, py - 1, pz, 'obsidian')
        b.set(x, py + 3, pz, 'obsidian')
    for yy in range(py, py + 3):
        b.set(px - 1, yy, pz, 'obsidian')
        b.set(px + 2, yy, pz, 'obsidian')
    for x in range(px - 2, px + 4):
        for z in range(pz - 1, pz + 2):
            b.set(x, py - 2, z, 'stone')
    b.flush()
    b.cmd('/setblock %d %d %d fire 0 replace' % (px, py, pz))
    b.flush()


def through_portal(bot, x, y, z, fallback=False):
    """Into a portal at this spot; with fallback, if that doesn't take, out of the Nether by dying (respawn)."""
    before = bot.respawns
    bot.teleport(x, y, z)
    try:
        bot.wait_dimension_change(before, timeout=15 if fallback else 90)
    except TimeoutError:
        if not fallback:
            raise
        log('the portal back didn\'t take at %.2f %.2f %.2f; out by /kill' % (x, y, z))
        before = bot.respawns
        bot.commands(['/kill'])
        bot.wait_dimension_change(before)
    log('through the portal: dimension %s at %.1f %.1f %.1f' % (bot.dimension, bot.x, bot.y, bot.z))


# ---------------------------------------------------------------- the player's things


def fill_inventory(bot):
    """As a creative player sets its own slots (5-8 armour, 9-35 main, 36-44 hotbar); NBT gzipped, as 1.7.10 sends."""
    def put(slot, stack):
        fields = stack[1]
        tag = fields.get('tag')
        bot.set_slot(slot, fields['id'][1], fields['Count'][1], fields['Damage'][1], tag)
    put(5, item(310, 1, 0, ench=enchants((0, 4), (5, 3))))
    put(6, item(307))
    put(7, item(316, 1, 40))
    put(8, LEATHER if False else item(301, 1, 0, display=compound(color=int_(0xAA2222))))
    hotbar = [SWORD, item(261, 1, 0, ench=enchants((48, 5), (51, 1))), potion(8193), potion(16385), potion(8198),
              BOOK, ENCHANTED_BOOK, item(322, 3, 1), item(368, 16)]
    for i, stack in enumerate(hotbar):
        put(36 + i, stack)
    main = [CUSTOM_POTION, potion(8257), potion(8225), potion(16396), potion(8270), potion(0), potion(16), item(264, 64),
            item(266, 12), item(262, 64), HEAD, ROCKET, item(2262), item(345), item(347), item(358, 1, 0)]
    for i, stack in enumerate(main):
        put(9 + i, stack)
    time.sleep(1.0)


def player_state(bot, mode):
    fill_inventory(bot)
    bot.commands(['/effect %s 1 1000000 0' % BOT, '/effect %s 16 1000000 0' % BOT, '/effect %s 12 1000000 1' % BOT,
                  '/effect %s 13 1000000 0' % BOT, '/xp 30L %s' % BOT])
    if mode == 0:
        bot.commands(['/gamemode 0 %s' % BOT])


# ---------------------------------------------------------------- a world


def make_world(spec):
    folder = spec['folder']
    log('==== %s (%s, seed %d)' % (folder, spec['type'], spec['seed']))
    serverdir = os.path.join(OLDSAVES, 'server', folder)
    if os.path.exists(os.path.join(serverdir, 'world')):
        aside = os.path.join(OLDSAVES, 'old', '%s-%s' % (folder, time.strftime('%Y%m%d-%H%M%S')))
        os.makedirs(os.path.dirname(aside), exist_ok=True)
        shutil.move(os.path.join(serverdir, 'world'), aside)
        log('the earlier world moved aside to', aside)
    server = Server(serverdir, JAR, spec['port'], spec['seed'], spec['type'], log=log)
    started = time.time()
    server.start()
    log('server up in %.0f s' % (time.time() - started))
    bot = Bot('127.0.0.1', spec['port'], BOT, log=log)
    buildings = []
    b = Builder(bot)
    try:
        bot.connect()
        sx, sy, sz = int(bot.x), int(bot.y), int(bot.z)
        log('joined at %d %d %d, dimension %s' % (sx, sy, sz, bot.dimension))
        bot.commands(['/gamemode 1 %s' % BOT, '/time set 1000', '/weather clear 1000000'])
        # the overworld: the house, the sweep above it
        HX, HY, HZ = sx - 12, 150, sz - 12
        bot.teleport(HX + 17.5, HY + 1, HZ + 21.5)
        house_box = house(b, HX, HY, HZ)
        buildings.append(('house', 0, house_box, (HX + 15.5, HY + 4, HZ + 22.5, 180.0, 20.0)))
        bot.teleport(sx + 0.5, 205, sz + 0.5)
        sweep_box = sweep(b, sx - 54, 200, sz - 50)
        buildings.append(('sweep', 0, sweep_box, (sx + 0.5, 215, sz - 60.0, 0.0, 35.0)))
        log('overworld built; %d commands failed so far' % len(b.failures))
        portal = (sx + 30, 141, sz + 40)
        pad = (sx + 30, 141, sz - 40)
        order = ['nether', 'end'] if spec['last'] == 'end' else ['end', 'nether']
        final = None
        for trip in order:
            if trip == 'end':
                to_end(bot, b, *pad)
                ex, ey, ez = int(bot.x), int(bot.y), int(bot.z)
                box, stand = end_hut(b, ex, ey, ez)
                buildings.append(('end_hut', 1, box, (stand[0], stand[1], stand[2] + 6.0, 180.0, 10.0)))
                log('End hut built')
                if spec['last'] == 'end':
                    final = (1, stand)
                    break
                leave_end(bot)
                # the overworld's end portal block goes again (the player is back)
                bot.teleport(pad[0] + 0.5, pad[1] + 3, pad[2] + 3.5)
                b.cmd('/setblock %d %d %d air 0 replace' % pad)
                b.flush()
            else:
                bot.teleport(portal[0] + 0.5, portal[1] + 2, portal[2] - 2.5)
                nether_portal(b, *portal)
                through_portal(bot, portal[0] + 0.5, portal[1], portal[2] + 0.5)
                arrival = (bot.x, bot.y, bot.z)
                ax, ay, az = int(bot.x // 1), int(bot.y), int(bot.z // 1)
                box, stand = nether_room(b, ax, ay, az)
                buildings.append(('nether_room', -1, box, (stand[0], stand[1], stand[2], 225.0, 10.0)))
                log('Nether room built')
                if spec['last'] == 'nether':
                    final = (-1, stand)
                    break
                # back the way it came: a portal block's middle (1.7.10 puts an arriving player on the portal's
                # edge, between its blocks; half a block on in x and z is inside one, whichever way it runs)
                through_portal(bot, arrival[0] + 0.5, arrival[1], arrival[2] + 0.5, fallback=True)
        if final is None:
            final = (0, (HX + 17.5, HY + 1, HZ + 21.5))
        dim, (fx, fy, fz) = final
        bot.teleport(fx, fy, fz)
        if spec['last'] == 'overworld':
            bot.commands(['/spawnpoint %s %d %d %d' % (BOT, HX + 17, HY + 1, HZ + 21)])
        player_state(bot, spec['mode'])
        bot.ticks(40)
        log('the player is left in dimension %s at %.1f %.1f %.1f; %d commands failed' % (bot.dimension, bot.x, bot.y, bot.z,
                                                                                           len(b.failures)))
        for line, key, args in b.failures[:40]:
            log('  failed: %s -> %s %s' % (line[:120], key, args))
    finally:
        try:
            bot.close()
        except OSError:
            pass
        time.sleep(2)
        server.save_and_stop()
        log('server stopped')
    return serverdir, buildings, b.failures


def make_save(spec, serverdir, buildings):
    """The server's world as a singleplayer save: the player in level.dat (without its UUID), named, cheats on."""
    folder = spec['folder']
    target = os.path.join(OUT, folder)
    if os.path.exists(target):
        aside = os.path.join(OLDSAVES, 'old', '%s-save-%s' % (folder, time.strftime('%Y%m%d-%H%M%S')))
        os.makedirs(os.path.dirname(aside), exist_ok=True)
        shutil.move(target, aside)
    os.makedirs(OUT, exist_ok=True)
    shutil.copytree(os.path.join(serverdir, 'world'), target)
    for lock in ('session.lock',):
        if os.path.exists(os.path.join(target, lock)):
            os.remove(os.path.join(target, lock))
    _, (_, player) = nbt.read_gzip(os.path.join(target, 'playerdata', '%s.dat' % offline_uuid(BOT)))
    player.pop('UUIDMost', None)
    player.pop('UUIDLeast', None)
    name, (kind, root) = nbt.read_gzip(os.path.join(target, 'level.dat'))
    data = root['Data'][1]
    data['Player'] = (COMPOUND, player)
    data['LevelName'] = string(spec['name'])
    data['allowCommands'] = byte(1)
    data['GameType'] = int_(spec['mode'])
    nbt.write_gzip(os.path.join(target, 'level.dat'), name, (kind, root))
    with open(os.path.join(OUT, folder + '.buildings'), 'w') as f:
        f.write('# made by oldsaves/make_vanilla_worlds.py on %s: name dim x1 y1 z1 x2 y2 z2 view x y z yaw pitch\n'
                % time.strftime('%Y-%m-%d %H:%M'))
        for bname, dim, box, view in buildings:
            f.write('%s %d %d %d %d %d %d %d view %.2f %.2f %.2f %.1f %.1f\n' % ((bname, dim) + tuple(box) + tuple(view)))
    return target, player


def check_save(target, buildings, player, spec):
    """What the saved region files hold in each building: blocks, tile entities, entities by kind."""
    want_dim = {'overworld': 0, 'nether': -1, 'end': 1}[spec['last']]
    problems = []
    if player['Dimension'][1] != want_dim:
        problems.append('the player is in dimension %d, not %d' % (player['Dimension'][1], want_dim))
    for bname, dim, (x1, y1, z1, x2, y2, z2), _ in buildings:
        blocks = tiles = 0
        kinds = {}
        for cx, cz, root in nbt.world_chunks(target, dim):
            if not (x1 >> 4 <= cx <= x2 >> 4 and z1 >> 4 <= cz <= z2 >> 4):
                continue
            level = root['Level'][1]
            for (x, y, z), _ in nbt.section_blocks(level).items():
                if x1 <= x <= x2 and y1 <= y <= y2 and z1 <= z <= z2:
                    blocks += 1
            for t in level.get('TileEntities', (nbt.LIST, (COMPOUND, [])))[1][1]:
                if x1 <= t['x'][1] <= x2 and y1 <= t['y'][1] <= y2 and z1 <= t['z'][1] <= z2:
                    tiles += 1
            for e in level.get('Entities', (nbt.LIST, (COMPOUND, [])))[1][1]:
                pos = e['Pos'][1][1]
                if x1 <= pos[0] <= x2 + 1 and y1 <= pos[1] <= y2 + 1 and z1 <= pos[2] <= z2 + 1:
                    kinds[e['id'][1]] = kinds.get(e['id'][1], 0) + 1
        log('  %s (dim %d): %d blocks, %d tile entities, entities %s' % (bname, dim, blocks, tiles,
                                                                         ', '.join('%s %d' % kv for kv in sorted(kinds.items()))))
        if blocks == 0:
            problems.append('%s: no blocks saved' % bname)
    return problems


def main():
    wanted = sys.argv[1:] or [w['folder'] for w in WORLDS]
    if not os.path.isfile(JAR):
        sys.exit('No server jar at %s (Mojang\'s 1.7.10 server, SHA-1 952438ac4e01b4d115c5fc38f891710c4941df29).' % JAR)
    report = []
    for spec in WORLDS:
        if spec['folder'] not in wanted:
            continue
        serverdir, buildings, failures = make_world(spec)
        target, player = make_save(spec, serverdir, buildings)
        log('saved as', target)
        problems = check_save(target, buildings, player, spec)
        report.append((spec['folder'], len(failures), problems))
    log('==== done')
    for folder, failed, problems in report:
        log('%s: %d commands failed; %s' % (folder, failed, '; '.join(problems) if problems else 'the buildings are in the save'))


if __name__ == '__main__':
    main()

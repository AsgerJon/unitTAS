# unitTAS
Unit testing for minecraft mods that relies on real TAS-like tests in real minecraft clients.

Tests that play the real game, in the manner of Python's `unittest`, for Minecraft 1.7.10 Forge mods. A real client
opens, a fresh test world is made, and test classes drive the game tick by tick (commands, typing in the chat, keys,
looking around) and check what happened (inventory, entities, blocks, chat, sounds). Screenshots on failure or on
request.

unitTAS is a mod of its own (mod id `unittas`, package `io.github.asgerjon.unittas`). It sleeps in an ordinary game
until a request file left by `./unittas.sh` wakes it. It needs a Mixin loader for 1.7.10 in the game (UniMixins, for
one); its mixins are in `mixins.unittas.json`, handed to Mixin by `core.UnitTasLoadingPlugin`.

## Running

```
./unittas.sh                     # every suite
./unittas.sh commands            # one suite
./unittas.sh commands,combat     # several
./unittas.sh commands Give       # only tests whose Class.method name contains "Give"
./unittas.sh self                # unitTAS's own tests
```

The script leaves a request in `run/client/unittas/request.properties`, starts `./gradlew runClient`, shows each
test as it finishes, and prints the report when the game quits. Everything lands in `unittas-results/<time>/`
(`unittas-results/latest` points at the newest):

- `report.txt`: one line per test (`ok`, `FAIL`, `ERROR`, `skipped`, `expected failure`, `unexpected success`,
  `NO RESULT`); for
  each that failed, the assertion and where in the test it failed (or the stack trace with its causes), the chat
  during the test and its screenshot; under any test, its warnings. unitTAS's own problems (a suite that doesn't
  exist, a class that can't run, a plugin that won't load, a run that stopped) are lines of their own, `problem`,
  counted apart from the tests: `Ran 16 tests in 41.0 s, 1 problem outside them`. Ends with `OK`,
  `OK (expected failures=2)` or `FAILED (failures=…, errors=…, unexpected successes=…, no results=…, problems=…)`, as
  unittest counts; the scripts' exit code follows it. Before each class's first line, the world it ran in (below).
- `NO RESULT` is a test that couldn't be run to a verdict: the game stopped ticking during it, or it ran past its time
  limit, or the watcher stopped it. It is never a FAIL or an ERROR, which are verdicts. A test's verdict depends on
  the game's ticks, never on how fast the machine is. A report with one says so before any test line: `NO TEST
  RESULT could be obtained for 1 test: …`. The run is FAILED.
- `screenshots/`: one per failed test (taken before its tearDown), plus the ones tests take on purpose.
- `progress.txt`, `gradle.log`: the run as it went.

**The window.** Each game runs inside gamescope (a small Wayland compositor with an Xwayland of its own), and is
seen in gamescope's window on your desktop. That window never takes focus: a Wayland compositor gives focus only to a
window that brings an activation token from something you did, and gamescope is started without one; the game's own
X11 focus requests stay inside gamescope's Xwayland. No desktop's settings or rules are involved.
`UNITTAS_DISPLAY=headless` runs the game with no window at all (the pictures still come from the game itself), and
`UNITTAS_DISPLAY=plain` straight on the desktop as before gamescope; `UNITTAS_WIDTH` and `UNITTAS_HEIGHT` size it
(854 by 480). Without gamescope, or on a desktop that isn't Wayland, the game goes on the desktop plain. The run needs
no focus either way: it ignores the real mouse and keyboard, never takes the mouse pointer, and doesn't pause when the
window is in the background. Close it with its window button or Ctrl+C in the terminal. (Plain on KDE, the window is
titled and classed `unitTAS`, and `./unittas-desktop.sh` moves it to virtual desktop 2.)

A run never starts beside a game already open in `run/client` (your own `runClient`, say): both would use its
options, saves and request, so the script refuses, and its report says why. The test world is
`run/client/saves/unittas`, made new each run; no other save is touched. The player's `options.txt` and the game's
`config/` are kept aside for the run (in `run/client/unittas/`) and put back as they were when the game quits, since
a test that changes an option or a mod's setting saves the whole file with the run's own settings in it: a file a
test changed is restored, one it made is removed. A run that dies before that puts them back first thing the next
time.

### When the game hangs

- A step the game doesn't run because it hasn't ticked for 15 s, and a test that runs past its `timeoutSeconds()`, are
  `NO RESULT`: no verdict. A wait for ticks gives up only when no tick has come for 15 s, so a game that is slow but
  ticking (a heavy test at 10 ticks a second) still gets there.
- When a test ends because the game stopped answering, the runner checks that the client and the server still tick.
  If one doesn't, the run stops there (the rest of the tests not run, said so in the report) and the threads are
  dumped into `hang-threads.txt`.
- The test world has 60 s to load; past that the run ends with `loading-trace.txt` (the local connection's steps)
  and `hang-threads.txt`, and the report says so.
- Every world opening is watched, in both runners: the game says which screen it shows. 1.7.10's integrated server
  sometimes drops its own local connection before the player joins, and the client then waits at the title screen
  for ever, its ticks still counting. A client back at the title screen while its own server runs with nobody in it,
  for 100 ticks of each side, is such a hung opening (it begins after the game has loaded, and counts ticks, so
  neither the mods' loading nor a slow game counts against it). It is pictured (`screenshots/loading-dropped-1.png`,
  or `<world>-dropped-1.png`), left, and opened again, once, and the progress says so. Hung twice, the world doesn't
  open: the run's tests are `NO RESULT`. A Python run also pictures the game as it comes up
  (`screenshots/opened.png`).
- A game unitTAS opens, unitTAS closes, and it never waits on one that shows no sign of life:
  - Before its probe says hello, the launch must keep saying what it does: the launcher names each file it fetches and
    each line of a loader's installer (NeoForge's, Forge's) as they come, a build its tasks. Two minutes with nothing
    new (`UNITTAS_HELLO_SECONDS`) and the game is stopped, said so. Once the agent has woken in the game (its first
    line, as the JVM starts), the hello must follow within 30 s; it takes about 2. A game that ends first is said at
    once, with its exit code.
  - An agent whose probe can't be loaded ends the game itself, saying why (exit code 70): a game no probe drives is
    no test, so it isn't left on its title screen for the run to wait on.
- A Python run (`unittas run`, plain `unittest`) watches the two stretches before its first world opens:
  - While the game loads its mods, its log grows. With nothing new in it for 1 minute, the terminal says so. After
    2 minutes (`UNITTAS_LOG_QUIET_SECONDS`) the game counts as hung while loading: it is stopped, and every test is
    `NO RESULT`, "the game didn't start". 10 minutes (`UNITTAS_READY_SECONDS`) is the most a loading that keeps
    going may take (a big modpack's).
  - Once the game is at its title screen, the run asks for its first world at once. If it hasn't asked 600 client
    ticks later (about 30 s), the terminal and `progress.txt` say so (`NO WORLD YET`). At 1200 ticks the run stops,
    every test `NO RESULT`, and the game quits. It counts the game's ticks, so a slow machine gets more time.
- A client joining a dedicated server (multiplayer, below) meets the same 1.7.10 race: the server drops the connection
  before its login, and the client waits at "Connecting..." for ever. After 200 client ticks there, the join is
  cancelled and tried once more, with a warning. Dropped twice, the join fails, naming the race. unitTAS leaves the
  game as 1.7.10 has it: it notices, says so and tries again, but never patches the game.
- Outside the game, `./unittas.sh` takes a run that writes nothing new to `progress.txt` for 10 minutes
  (`UNITTAS_STALL_SECONDS` to change it) to be stuck: `./hang-dump.sh` writes each game JVM's threads into the results
  (`hang-*.txt`) and the game is stopped. A game that doesn't quit within a minute of its report is stopped too.
- `./hang-dump.sh [folder]` takes the threads of every running dev client and server by hand.

A watched run (below) asks before it gives up on any of these.

## Watching a run

A run is meant to be watched by whoever started it, most likely an LLM in a coding session. Every run shows what it
is doing:

- `screenshots/watch-live.png`: the window, every 10 s (`UNITTAS_PICTURE_SECONDS`, 0 for none), and
  `watch-previous.png`, the one before it, to see whether anything moved.
- `watch.txt`, every 5 s: the test and how long it has run against its limit, what it is waiting for ("waiting for
  'the zombie dies' (tick 140 of 200, on the server)"), whether the client and the server tick, and the open alarm.

In a watched run (`UNITTAS_WATCHED=1`; the watcher's runs are), no fixed limit decides alone that the game is stuck.
Where unitTAS would otherwise give up, it raises an alarm instead:

- a test runs past its `timeoutSeconds()`;
- the test world hasn't loaded in 60 s, or a save hasn't loaded or closed in 180 s;
- the game stopped answering during a test (a step that never came back) and still doesn't tick.

The alarm is `alarm.txt` in the results folder: what it sees, what the run is doing, two pictures 3 s apart (or the
threads, when the client can't take pictures), and the answers to choose from. The answer is one line in
`decision.txt` next to it, starting with the alarm's number:

- `N wait <seconds>`: it is working, give it that long. If it is still at it then, a new alarm comes with new
  pictures.
- `N fail <why>`: stop the test, with the reason, and go on with the next. The test is `NO RESULT`: it never reached a
  verdict. For a game that stopped answering after a test, it means going on with the next test.
- `N abort <why>`: stop the whole run, with the reason; the report says so.

An answer for another alarm is dropped, and one that is none of the three is pointed out in `alarm.txt`. An alarm
whose situation passes by itself (the test finishes) closes on its own. `alarms.txt` keeps every alarm and its
answer, and each shows in `progress.txt`. Without an answer in 5 minutes (`UNITTAS_DECIDE_SECONDS`), unitTAS does what
it does unwatched, so a run nobody watches still ends. The quiet-game limit of `./unittas.sh` then counts `watch.txt`
too: only a game whose watch has stopped as well is stopped from outside.

A Python run (`unittas run`, below) has the same watch, with the same files, words and answers. Its `watch.txt` reads
the client and the server from the probe's heartbeat, which comes once a second even when the game doesn't tick, and
says when the probe has gone silent. It is watched with `--watched` or `UNITTAS_WATCHED=1`, and its alarms come for a
test past its `timeout_seconds` and for a test world not loaded in 60 s. A `fail` or no answer leaves that test, or
the world and every test after it, `NO RESULT`.

The watcher judges only whether the game is stuck, never whether a test passed. A test passes when its asserts hold,
and only then; `ticks(n)` and `waitUntil(…, maxTicks)` are part of what a test asserts and stay as they are.

## What tests share: the game, the world, the class

A run has four levels, each made and put away at its own time:

| Level | What it holds                                      | How many     | Set up and put away by                |
|-------|----------------------------------------------------|--------------|---------------------------------------|
| game  | the client: options, `config/`, mods' client state | 1 per run    | plugin `beforeRun` / `afterRun`       |
| world | the save: blocks, time, rules, the End, mods' data | 1 per class* | plugin `setUpWorld` / `tearDownWorld` |
| class | a test class                                       | 1            | `setUpClass` / `tearDownClass`        |
| test  | one instance of the class                          | 1 per test   | `setUp` / `tearDown`                  |

\* unless the class is `@SharedWorld`.

**The game** is shared by every test in the run; its options and `config/` are put back only when the run ends.

**The world:** the run makes it once (flat: bedrock, two dirt, grass, the surface at y 3, no structures of its own;
creative, cheats, seed 20261029, Easy; noon with the day's cycle off, no weather, no natural mob spawning, no fire
spread, no mob griefing) and keeps a copy of it as made. Every class gets that copy back before its setUpClass: a
fresh world, the same one byte for byte, whatever the classes before it did (blocks, the time, game rules, the End
and its shulkers). That costs reopening the world for every class, a few seconds each. A class marked
`@SharedWorld` skips it and runs in the world as the class before it left it: faster, and its tests see all of
that, so take the precautions that needs. The report says which, on a line before each class's first:
`world 3: fresh for GiveTests (the kept world put back, opened in 5.1 s)` or
`world 3, shared: GiveTests runs in it as ChatTests left it`; `worldNumber()` tells a test.

**A class that needs real terrain** (a map, a cartography table, a structure) asks for a world of its own:
`@TasWorld(type = "default", seed = 1234)` in Java, `world = {'type': 'default', 'seed': 1234}` in Python. Most tests
are fine in the superflat world; this is for the few that aren't. The class's world is made fresh for it with those
settings (the type `default`, `flat`, `large_biomes` or `amplified`; the seed, the run's own by default; a generator's
options; whether structures are made), in a save folder of its own, `saves/unittas-class`, so the run's superflat
world and its kept copy are never touched. It gets the same steady settings and world hooks as any fresh world. The
reset then puts the player where the game put it when the world was made, a safe spot at its spawn, since real
terrain has no fixed height to stand at. The class after it gets the superflat world back. With `@SharedWorld`
(`shared_world = True`) as well, a class runs on in the world the class before it left, if that class asked for the
same world. The report's line: `world 4: fresh for MapTests, made as it asks (type default, seed 1234; made in
9.2 s)`. A multiplayer class can't ask for one yet: its server's world is the run's superflat one.

**Within a class**, its tests share the world. Before each test unitTAS puts the player back, and only this: at
0.5 4 0.5 looking south in the overworld, in creative and not flying, out of any bed, not burning or riding, an empty
inventory, no experience, hotbar slot 1 selected, no effects, full health and food; the difficulty back at Easy; no
screen open, no key held, first person; every entity in a loaded chunk removed; the weather cleared. Not put back
between a class's tests: blocks, the time, game rules, entities in chunks that aren't loaded, a mod's own state (that
is the plugin's `resetPlayer`). Tests that build use their own spot. Undead burn at noon: give zombies and skeletons
a helmet when a test needs them to last.

### A new class, or a new method?

A class is a world, and a method is a turn in it. Before a new test, ask what the test before it may have left
behind, and whether the reset puts that back:

| What a test changes | Put back before the next test? | So |
|---|---|---|
| the player: where it is, its inventory, health, food, effects, game mode, experience | yes, by the reset | a new method |
| entities in loaded chunks, the weather, the screen, keys held, the difficulty | yes, by the reset | a new method |
| blocks in its own spot, which no other test reads | no, but nobody looks | a new method |
| blocks that other tests use (near the start, 0.5 4 0.5), the time, game rules, the world's spawn point, scoreboards | no | a new class, or put it back in `tearDown` |
| the End or the Nether (the dragon, the exit portal and gateways, shulkers), entities in far chunks that unload | no | a new class |
| a mod's own world data (what it saves with the world) | no; a fresh world does | a new class |
| options, key bindings, `config/`, a mod's static or client state | no, not even by a new class | put it back in `tearDown`, or in the plugin |

**The last row is the one to watch.** A new class gives a new world, not a new game, so what a test leaves in the game
outlasts every class after it. A test that changes an option puts it back itself.

**A new method** is right for most tests:

- one feature looked at from several sides: the same setup, many checks;
- tests that read what setUpClass made (a structure, a game rule, a killed dragon) without changing it;
- tests that build, each in its own spot.

**A new class** is right when:

- a test changes the world in a way that the reset doesn't put back, and another test could see it;
- a test needs the world as made, untouched, from its very first tick: a class of its own, even with one test in it.

**`@SharedWorld`** is for a class whose tests don't care what the world looks like: commands, the chat, the player's
own inventory. It saves the class's reopen, a few seconds. It is never a way to hand state from one class to the
next: a class that needs what another left fails when it runs alone. Make that state in its own setUpClass instead.

**Signs that two tests should be apart:**

- a test passes alone and fails in its class, or the other way round;
- a test passes or fails with the order of the methods (they run in name order);
- a test's setUp undoes what another test did. That is a class boundary, written by hand.

**What a class costs:** its fresh world, about 4 to 5 s. So a class isn't made for each test by reflex. Group the
tests that share a setup, and split where the table above says to.

## Writing tests

A test class extends `io.github.asgerjon.unittas.TasTestCase` and is marked `@TasSuite("name")` with the suite it
belongs to; unitTAS finds it through Forge's annotation table, so nothing else lists it. A suite's classes run in the
order of their names. Every public method whose name starts with `test` is a test, inherited ones too; they run in
name order, each on a new instance of the marked class, with `setUp()` before and `tearDown()` after. A test runs on
its own thread and asks the game for each step:

```java
@TasSuite("commands")
public class GiveTests extends TasTestCase {

	public void testRedWool() {
		assertSaid(command("/give @p wool 1 14"), "Given [Red Wool] * 1");
		assertEqual("minecraft:wool:14", id(held()));
	}

	public void testTabCompletesCommands() {
		TasChat chat = type("/tim").key(Keyboard.KEY_TAB);
		assertEqual("/time", chat.text());
		assertIn("/time", chat.suggestions());
		chat.close();
	}
}
```

- Commands: `command(text)` runs it as the player (as a typed command, without the chat's length limit) and returns a
  `TasCommand` (`lines()`, `errors()`, `result()`); `type(text)` opens the chat and types key by key, and the
  `TasChat` it returns has `text()`, `suggestions()` (in 1.7.10's own chat: the completions the server sent for the
  last Tab), `usage()` (the line above the input, for a mod's chat that has one), `key(Keyboard.KEY_TAB)`,
  `typeMore(text)`, `enter()`, `close()`.
- The game: `onServer(() -> …)` and `onClient(() -> …)` run a step on that thread at the end of its next tick and
  return its result (a step asked for from inside a step on the same thread runs at once). One step after another
  takes a tick each, so a test can sample once a tick with a step per sample. Inside a server step, `player()` and `world()` are the
  server's player and world. Never touch game objects outside a step, and don't wait for ticks inside one:
  `player()`, `world()`, `entitiesNear()` or `runCommand()` called outside a server step put a warning under the
  test in the report, with the line it came from (a warning for now, not a failure).
- Waiting: `ticks(n)`, `serverTicks(n)`, `waitUntil("what", () -> condition, maxTicks)` (checked on the server),
  `waitUntilOnClient(...)` (on the client: for what the server changed and the client must have before the test
  goes on, such as an item given with `setHeld` before a click).
- Sounds: `waitForSound("minecraft:random.bow", maxTicks)`, `soundsHeard()`, `clearSounds()`: every sound the client
  plays (muted or not), by name; each test starts with none. A sound the game doesn't have (no sounds.json names it)
  plays nothing, silently: a test that causes one fails.
- Things: `held()`, `inventory()`, `setHeld(stack)`, `id(stack)` (`minecraft:wool:14`), `spawn(EntityZombie::new, x,
  y, z)`, `entitiesNear(Type.class, radius)` (inside a server step), `difficulty(EnumDifficulty.PEACEFUL)`.
- Input: `look(yaw, pitch)`, `hold(mc().gameSettings.keyBindForward, ticks)`, `tap(key)`, `keyDown(key)` /
  `keyUp(key)` (held until let go, as right click for a raised shield), `cameraView(0|1|2)` (first person, third
  person from behind, from the front; each test starts in first person).
- `screenshot("name")` saves the screen as it is now; `resultsFolder()` is the run's results folder.
- Asserts, as unittest's, each with an optional message last: `assertEqual`, `assertNotEqual`, `assertTrue`,
  `assertFalse`, `assertIsNone`, `assertIsNotNone`, `assertIn`, `assertNotIn`, `assertGreater`, `assertAlmostEqual`
  (its third argument is the allowed difference, not unittest's number of places), `fail`, `skipTest`; for commands
  `assertSaid`, `assertError` (a red line), `assertNoError`. ItemStacks are never equal to one another: compare
  `id(stack)` and the stack size.
- `timeoutSeconds()` (default 60) stops a test that hangs.
- `setUpClass()` / `tearDownClass()`, as unittest's: once before the class's first test (in the class's world, after
  a reset of the player) and once after its last. They run on an instance of their own, so what setUpClass makes for
  the tests goes in static fields, and the reset before each test still runs: what it leaves must survive that
  (blocks, game rules, a mod's state), not entities, items or effects. Anything either throws is an error (a
  `Class.setUpClass` line, and the class's tests don't run); `skipTest` in setUpClass skips them all.
- `@SharedWorld` on a class: it runs in the world as the class before it left it (above); `worldNumber()` is the
  world a test runs in, as the report numbers them.
- `@TasWorld(type = "default", seed = 1234)` on a class: a world of its own, with real terrain, made fresh for it
  (above).
- `@ExpectedFailure("why")` on a test (or on its class), as unittest's `expectedFailure`: a failed assert or an
  exception from the test itself is an `expected failure`, and the run can still end OK; a pass is an
  `unexpected success`, which fails the run (the mark has done its work and should go). setUp and tearDown stay
  what they are, and unitTAS's own stops (out of time, a game that stopped answering, the watcher's fail) are
  `NO RESULT`: a marked test that couldn't run to its verdict hasn't failed as expected either.
- `TasLogErrors` listens to FML's logger and the root logger for errors and warnings (FML only logs the exception of
  an entity or tile entity that fails to load); `TasTrace` is the loading trace.

## Tests in Python

The same game, driven from outside it. The `unittas` Python package (in `python/`) starts the game an instance spec
names, with unitTAS's probe inside, and runs Python tests against it over a local socket (PROTOCOL.md). The four
levels are the ones above. The report has the Java runner's shape, so `unittas compare` can compare a Python run with
a Java one line by line. The Java front end stays: a test that lives in a mod's internals is still best written in
Java.

**The instance spec**, `unittas.toml` in the mod's repository, says which game:

```toml
minecraft = "1.7.10"
loader = { forge = "10.13.4.1614" }
client = "real"                                # or "gradle": said, never assumed
build = "./gradlew --console=plain remapJar"   # run first, without a shell
mods = ["build/libs/mymod-*.jar"]              # each matching exactly one file
libraries = ["maven:com.example:alib:1.0", "libs/unimixins-1.7.10-0.3.1.jar"]
repositories = ["https://maven.example.com/"]  # where maven: libraries come from (https only)
probe = "libs/unittas-0.1.0-dev19.jar"          # unitTAS's jar, the probe
config = "test-config"                         # copied into the game's config/ for the run
options = { autoJump = false }                 # set in options.txt for the run
game = "run/unittas"                           # the real client's game folder
window = { width = 854, height = 480, display = "nested" }   # or "headless", "plain"
```

- `client = "real"` is a real (not development) client. Its `mods/` holds the probe, the spec's mod jars and its
  libraries. What it needs comes from the Gradle cache where that has it. The rest is downloaded from Mojang's and
  Forge's own servers over HTTPS into `~/.cache/unittas` (or `UNITTAS_CACHE`), each file checked against its sha1.
  Java 8 is never downloaded: `java = "/path/to/java"`, `UNITTAS_JAVA8`, or the usual JDK folders.
- `client = "gradle"` is the mod's own development run, in a `[gradle]` table: `project` (its folder), `task`
  (`runClient`) and `game` (its run folder).
- **26.3**, **1.21.1** and **1.20.1** are the other versions a spec may name (`minecraft = "26.3"`, `"1.21.1"`,
  `"1.20.1"`), each with Fabric Loader 0.20.1 for a Fabric mod (`loader = { fabric = "0.20.1" }`), 1.21.1 and 26.3 with
  NeoForge for a NeoForge mod (`loader = { neoforge = "21.1.267" }`, `loader = { neoforge = "26.3.0.110" }`), 1.20.1
  with Forge for a Forge mod (`loader = { forge = "47.4.28" }`), or with no loader at all, as Mojang ships it. NeoForge
  and Forge are installed by their own installers into the download cache, once, as the launcher first needs them.
  Forge's installer refuses the jars it makes unless Java compressed them with classic zlib (its sha1s are of classic
  zlib's bytes, and Forge won't take any other zlib's:
  [Installer#77](https://github.com/MinecraftForge/Installer/pull/77) closed unmerged,
  [#80](https://github.com/MinecraftForge/Installer/issues/80) open), so on a system whose zlib is zlib-ng (Arch's,
  Fedora's) unitTAS runs it once more on classic zlib 1.3.1, built once into the download cache from zlib's own source
  (held to its sha1) by the system's C compiler (`cc`); without one it stops, saying so. A real client only for now (no
  `client = "gradle"` and no `[server]` yet). The probe is the version's agent jar
  (`probe = "path/to/unittas-probe-26.3.jar"`, `unittas-probe-1.21.1.jar`, `unittas-probe-1.20.1.jar`), on the game's
  command line, never in `mods/`; the version's Java (25 for 26.3, 21 for 1.21.1, 17 for 1.20.1) is found as it asks;
  the first launch's onboarding and tutorial hints are switched off in its `options.txt`. Tests that name things by
  mcdex member and places from `self.start` run on every version unchanged.
- Paths are taken from the spec's own folder. A mod jar of the spec's own project that is older than the newest file
  under its `src/` is refused, as not built from those sources. Every mistake names the file and the key.

**A test class** is a plain `unittest.TestCase`:

```python
from unittas.testcase import GameTestCase

class GiveTests(GameTestCase):

  def test_red_wool(self):
    said = self.command('/give @p wool 1 14')
    self.assertIn('Given [Red Wool] * 1', said.lines)
    held = self.held()
    self.assertEqual(('minecraft:wool', 14), (held.id, held.meta))
```

- `self.game` is the game (`unittas.api.Game`): `command`, `player`, `teleport`, `look`, `held`, `slot`,
  `inventory`, `setSlot`, `block`, `setBlock`, `spawn`, `entity`, `entities`, `remove`, the keys (`tap`, `keyDown`,
  `keyUp`, `key`), the screens (`openScreen`, `closeScreen`, `type`), `ticks(n)`, `waitUntil`, `screenshot`, and
  `reflect` by readable names (a real client's are translated). Its values are typed (`unittas.values`). An error
  from the game is the package's exception (`unittas.errors`): a mod that threw is a `GameError`.
- `command` gives back the command's `result` (1 for success in 1.7.10; from 1.13 on the command's own value, as
  `/time set 6000`'s 6000), `lines` (plain: in 1.7.10 the chat lines that came in while it ran; from 1.13 on what the
  command said back, at once) and `errors` (the red ones among them). A refusal's text is checked with a substring:
  `any('higher than the maximum' in line for line in said.errors)`.
- The levels are the Java runner's. Each class gets the kept world back unless it says `shared_world = True`, and
  a class that needs real terrain says `world = {'type': 'default', 'seed': 1234}` (above). The
  player is reset before every test, whatever its own `setUp` does. `setUpClass` (which calls
  `super().setUpClass()` first, as unittest has it) runs in the class's world. `self.chat()` and `self.sounds()` are
  this test's.
- A test's verdict depends on the game's ticks, never on the clock: wait with `self.game.ticks(n)`, or check once a
  tick for a bounded number of ticks. A game that stops ticking makes the test `NO RESULT`, never a FAIL.
- `timeout_seconds` (60) on a class stops a test of it that never ends. It is stopped with no result (`NO RESULT`),
  since a clock is no verdict, and in a watched run the watcher is asked first (below, "Watching a run").
- The game crashing is `NO RESULT` too: the test's line names the crash and its crash report, and the tests after it
  aren't run.

**Values across versions.** One class per value, in `unittas.values`, the same for every version. A field a version
hasn't holds its empty value, never None:

| value | field | 1.7.10 | 26.3 |
|---|---|---|---|
| `Item` | `meta` | its damage or kind (wool's colour) | `-1`, none: a colour is in the id, damage a component |
| `Item` | `snbt` (`nbt`, its tree) | its NBT as SNBT, `''` for none | `''` |
| `Item` | `components` | `''` | its data components as SNBT, `''` for none |
| `Block` | `meta` | its meta | `-1`, none |
| `Block` | `state` (`properties`, a dict) | `()` | its state's properties as `(name, value)` pairs |
| `Inventory` | `offhand`, `hasOffhand` | `Item.EMPTY`, `False` | the off hand's stack, `True` |
| `Effect` | `id` | its number | `-1`: its name is its id |
| `Entity` | `type` | 1.7.10's name (`Pig`) | its id (`minecraft:pig`) |

A thing named by its mcdex member (`MCBlocks.RedWool`) becomes each version's own value: wool of meta 14 in 1.7.10,
`minecraft:red_wool` in 26.3. A block given by its id alone (`'minecraft:stone'`) goes without meta, so the game puts
its own. 1.21.1's values are 26.3's (states, components); 1.20.1's too, but an item's data is its NBT (`Item.snbt`),
as 1.7.10's: data components came with 1.20.5. 1.20.1 writes a damageable item's damage into its NBT as it makes it, so
new boots set in a slot read back with `snbt='{Damage:0}'`, as the game holds them.

**Running:**

```
unittas run                                            # every test*.py under the current folder
unittas run tests.test_give                            # a module
unittas run tests.test_give.GiveTests.test_red_wool    # one test (or a class)
unittas run --instance other.toml --results out/
unittas run --watched                                  # alarms for a watcher where a limit would decide
unittas run tests.test_saves --saves run/oldsaves/vanilla   # save mode: each save opened twice (below, "Old saves")
unittas run tests.test_sync --multiplayer               # with its multiplayer classes (below, "Multiplayer tests")
unittas run --java oldsaves --saves run/oldsaves/vanilla    # a mod's Java suites, by java.run, here in save mode
unittas launch --world                                 # the game alone, in the test world, to look at
unittas watch                                          # the watcher, for a session that can't open windows
unittas compare before/report.txt after/report.txt
python -m unittest discover                            # plain unittest: the first GameTestCase starts the run
```

- `python -m unittas` is the same command.
- The spec is `--instance`'s, else `UNITTAS_INSTANCE`'s, else `unittas.toml` in the current folder.
- The tests are loaded before the game starts, so one that can't load costs no launch. A game that can't start
  leaves every test `NO RESULT`, under a `unitTAS.game` problem.
- Everything lands in `unittas-results/<time>/` beside the spec (`latest` points at the newest): `report.txt`,
  `screenshots/`, `progress.txt`, `watch.txt`, `unittest.txt` (unittest's own lines), and the game's output under
  `game/`. The terminal shows each test's line as it ends, numbered as the Java runner's
  (`test 3/40 GiveTests.test_red_wool ... ok`), then the report's verdict.
- The exit code: 0 for OK, 1 for FAILED, 2 for a mistake in the command or the spec, 130 after Ctrl+C.
- Ctrl+C (or SIGTERM) ends the run properly: the game quits, its folder's options and `config/` are put back, and
  the report has what ran. The tests it didn't reach are `NO RESULT`, not run.
- `launch` is for looking at the game, not playing it: the probe drops the real mouse and keyboard.
- Under plain unittest the run's `report.txt` is written at exit, into the same results folder. The class fixtures
  are then in unittest's own output only.

### Multiplayer tests

A test that needs a dedicated server and more than one player: a block one player places that another sees, a packet
a server must send, common code that reaches a client-only class (only a dedicated server shows that).

```python
from unittas.testcase import MultiplayerTestCase

class SyncTests(MultiplayerTestCase):
  clients = ('alice', 'bob')

  def test_bob_sees_alices_block(self):
    self.server.command('/setblock 2 3 2 minecraft:gold_block', as_='server')
    seen = self.bob.waitUntil('block.get', {'pos': [2, 3, 2]}, {'path': ['id'], 'eq': 'minecraft:gold_block'},
                              side='client', maxTicks=100)
    self.assertTrue(seen['held'], seen['value'])
```

- **The games:**
  - `self.server` is the dedicated server's game, and each name in `clients` is a client's: `self.alice`, `self.bob`.
  - The first is the run's own client. Its player keeps the name it was launched with (`unitTAS`). The others play
    under their own names: `self.bob.playerName()`.
  - On the server, `self.server.players()`, `self.server.player(name=...)`, `self.server.kick(name, reason)`, and
    `command(text, as_='server')` or `as_='bob'`.
  - On a client, `join(port)` and `leave()`. A run joins and leaves for you.
- **The levels:**
  - Each class gets a fresh server world: the server is restarted and makes it again from the same seed, and the
    clients join it. With `shared_world = True` a class runs on in the world the multiplayer class before it left.
  - Before each test the players are reset across the games, and a client a test put out (kicked) joins again.
  - A singleplayer class after a multiplayer one gets its own kept world back.
- **What a run needs:**
  - `unittas run --multiplayer` (or `UNITTAS_MULTIPLAYER=1`). Without it, multiplayer classes are skipped, saying
    why.
  - `client = "real"` in the spec: each client has a folder of its own, which a development `runClient` hasn't.
  - The spec's `[server]` table:

    ```toml
    [server]
    eula = true                        # you accept Mojang's EULA (https://aka.ms/MinecraftEULA): unitTAS never does
    exclude = ["client-only-*.jar"]    # mods the server leaves out (the clients' mods otherwise)
    memory = "2G"                      # the server's -Xmx
    ```

    Without `eula = true`, `--multiplayer` is refused before anything starts.
- **What it costs:** three games at once, the server's memory plus about 2 GB per extra client. Before they start,
  the machine's available memory is checked against that, plus 1 GB to spare. Short of it, that class's tests are
  `NO RESULT`, saying the numbers, and the run goes on.
- **Safety:** the server listens on 127.0.0.1 only. It reports every address it really listens on, and unitTAS stops
  it before any client joins if that is anything else. Its operators are the run's own players, written fresh each
  run.

### Scenarios: an agent that plays

A scenario sets up a place in the world, then has a player do things there: not exact inputs, but "turn the lever
off", "take the wool out of the chest". The player is the agent, a player and nothing more (SPEC.md 15). It works out
for itself how to walk there, look and click, with the keys and the mouse's look alone. A scenario is a
`ScenarioTestCase`: a `GameTestCase` with `self.scene` (places, from the block the run's start stands in) and
`self.agent`. The model scenario (python/tests/probe/modelsuite.py, run in the game by test_model.py):

```python
from mcdex import MCBlocks, MCItems
from unittas.scenario import ScenarioTestCase
from unittas.values import Block

A = (4, 0, 6)     # the lever
B = (0, 0, 6)     # the chest the hoppers fill
WOOL = '{Items:[{Slot:0b,id:35s,Count:1b,Damage:6s}]}'

class LeverAndChestTests(ScenarioTestCase):

  @classmethod
  def setUpClass(cls):
    super().setUpClass()
    # the setup is by command, not the agent: a line of hoppers into a chest; a lever, on,
    # locks the furthest; a chest of pink wool on it
    cls.scene.place(Block('minecraft:chest', 3), at=B)
    for x in (1, 2, 3):
      cls.scene.place(Block('minecraft:hopper', 4), at=(x, 0, 6))
    cls.scene.place(Block('minecraft:lever', 13), at=A)
    cls.scene.place(Block('minecraft:chest', 3, True, WOOL), at=(3, 1, 6))

  def test_a_the_wool_let_through(self):
    leverA = self.scene.thing(MCBlocks.Lever, at=A)
    chestB = self.scene.thing(MCBlocks.Chest, at=B)
    if leverA.isOn():
      leverA.activate()          # the agent walks over, looks at it, clicks
    self.agent.wait(40)          # a hopper passes an item on every 8 ticks
    self.assertIn(MCItems.PinkWool, chestB.contents())

  def test_b_the_wool_taken(self):
    chestB = self.scene.thing(MCBlocks.Chest, at=B)
    chestB.open()
    self.agent.take(MCItems.PinkWool)
    self.agent.close()
    self.assertIn(MCItems.PinkWool, self.agent.inventory())
```

- **Setup** is by command: `scene.place(block, at=(dx, dy, dz))` puts an mcdex member, or a `Block` as the game's
  version has it, and is done when both sides show it. `scene.thing(member, at=...)` names one already there.
- **Actions** are the agent's: a thing's `activate()`, `open()`, `breakIt()`; the agent's `walkTo`, `reach`, `lookAt`,
  `use`, `breakBlock`, `place` (from its hotbar), `take`, `put`, `close` and `wait(ticks)`. Its way goes around what
  is in it, up steps and slabs, jumps up a block, drops down three, opens doors, goes up and down ladders and swims;
  never into lava.
- **Examinations** are by command by default (`isOn()` or `bool(thing)`, `isThere()`, `contents()`, `stacks()`), or,
  as the author chooses, the agent's own: `inventory()`; `examine()`, the pixels a block covers in its view, and
  `identify()`, which block it is by its looks (`assertIdentifies`).
- **The report** says under each test's line what it examined and how: `examined by command: ...`, `known to the
  agent: ...`, `observed (pixels by the game's ray): ...`.
- **Outcomes:** an action the agent can't complete (no way there, out of reach, the tick budget spent, slipped off a
  ladder) raises `TesttimeError`, the test's ERROR, naming the step and what the agent saw. An examination that finds
  the world wrong is the test's FAIL. A game that stops ticking is `NO RESULT`, as ever.
- **Today** the agent plays 1.7.10 and 26.3: walking, verbs, containers, `examine()` and `identify()` pass their game
  tests on both (26.3 draws a block one of several ways at random, stone plain or mirrored: `identify()` compares
  each), and the scenarios run on a run of either.

## A mod's own part

What unitTAS can't know of a mod goes in a class that implements `TasHooks` and is marked `@TasPlugin` (a public
constructor without arguments), in the tests' source set so it's in no jar. Each method has a default that does
nothing:

- `beforeRun()` / `afterRun()` (client thread): the mod's own settings as its tests expect them for the run, and the
  player's put back after.
- `setUpWorld()` / `tearDownWorld()` (server thread): each time the test world opens (the run's, and each class's
  fresh one), before the class's setUpClass; and before it closes, after the last class too. What every world should
  hold for the mod's tests. Not in save mode, where the saves are what they are.
- `resetPlayer(EntityPlayerMP)` (server thread, between tests, after unitTAS's own reset): what the mod keeps of the
  player besides, as an off-hand slot.
- `chatText`, `chatSuggestions`, `chatUsage` (client thread): for a mod with a chat screen of its own; null leaves it
  to 1.7.10's.

A hook that can't be made, or that throws in `beforeRun` or `afterRun`, is a `problem` in the report.

## Old saves

Save mode opens saves instead of the fresh test world: `saves=` in the request names them (folders in the game's
saves), and each is opened from the main menu in turn, twice: as found, then after this game saved and quit it. The
suites run in each with none of the per-test resets and no game rule changes (they would change the save).
`TasSave.current()` is the save open now (its pristine copy, its building list, what was logged while it loaded).

`./unittas.sh oldsaves` runs a mod's `oldsaves` suite this way on vanilla 1.7.10's own worlds:

1. `python3 oldsaves/make_vanilla_worlds.py` makes them once: Mojang's 1.7.10 server, headless
   (`run/oldsaves/server/minecraft_server.1.7.10.jar`, and your own `run/oldsaves/server/eula.txt` if you accept the
   EULA; Java 8, `UNITTAS_JAVA8` to name one), and a small scripted client of 1.7.10's protocol that builds a house
   and a block sweep in the overworld, a room in the Nether and a hut in the End, then leaves the player in one of
   them. Each world becomes a singleplayer save in `run/oldsaves/vanilla/`, with its building list.
2. `./unittas.sh oldsaves` builds the release jar and runs it in a real client: its game folder `run/release/`
   holds the jar, `run/oldsaves/mods/*.jar` (its libraries: UniMixins at least, and unitTAS's release jar for a mod
   that takes unitTAS as a dependency) and fresh copies of the saves. `./unittas.sh oldsaves dev` does the same in
   the dev client; `./unittas.sh oldsaves inspect` only reports the real client's command and folder.

**The real client** is unitTAS's own launcher, `bin/launch_client.py`: Minecraft 1.7.10 with Forge 10.13.4.1614 on
Java 8 (`UNITTAS_JAVA8` to name one), made from what the Gradle cache already holds (Unimined's official client jar,
Forge's universal jar, every library, the natives, the assets), so nothing is downloaded and no other launcher is
needed. `./unittas.sh oldsaves instance` runs the release jar there with no saves, every suite its jars hold, in the
fresh test world: for unitTAS's own jar there are none, and the run is the check that the jar starts outside a
development run (`Ran 0 tests`, OK). Any other version is `--minecraft VERSION`, with a loader on top by `--loader
fabric|neoforge|forge --loader-version V`: Mojang's version JSON, Fabric's profile from its meta server, NeoForge's and
Forge's from their own installers, run headless once into the download cache; every file held to its sha1. When it
can't make the launch, it says why and exits 2, and leaves the reason in `$UNITTAS_RESULTS/launcher-failed.txt`: a test
that launched the game reports that as its error (in the test display the launch ends with gamescope's exit code).

**Through the orchestrator** (`unittas run`, "Tests in Python" above), in whatever game an instance spec names:

- `unittas run --java oldsaves --saves run/oldsaves/vanilla` runs a mod's Java `oldsaves` suite:
  - the saves go in as fresh copies (a copy of the same name already there goes into the results'
    `saves-before-this-run/`);
  - the Java runner's save mode runs inside the game (`java.run`), its lines shown as they come;
  - the saves as the game left them go into `saves-after/`.

  It is meant to replace `./unittas.sh oldsaves`'s real-client path. `--java` without `--saves` runs Java suites in
  the fresh test world, in any game a spec names.
- `unittas run tests.test_saves --saves DIR` runs Python tests in save mode, in the Java runner's order:
  - each save is opened twice, as found and again as this game saved it, and settled 60 ticks;
  - the tests run in it as they find it, with no resets and no world hooks;
  - each line is `Class.test [save, load N]`.

  `self.save()` is the save open: its `folder`, `load`, `pristine` copy and `buildings` list, and its `loadErrors`,
  `loadWarnings` and `loadSeconds`.
- unitTAS's own check needs no download. `python/tests/probe/test_oldsaves.py` makes `run/oldsaves/selfcheck/` (two
  test worlds with a gold marker each) and runs the self suite `oldsaves` on it three ways (the script, `--java`, and
  its Python twin). All three must come out the same.

## The watcher

A session that can't open windows itself (an LLM in a sandbox, say) asks for runs through `./unittas-watch.sh`, kept
running in a terminal. The watcher's runs are watched (above). The session:

1. removes `unittas-queue/done` and `unittas-queue/run`, then writes one line to `unittas-queue/request` (to a `.tmp`
   first, then moved): `"<suites> [filter]"`, or `""` for every suite;
2. waits for `unittas-queue/run`, which names the run's results folder as the run starts;
3. waits until either `unittas-queue/done` appears (the run is over: it holds the exit code, and `report.txt` is in
   the folder) or the folder's `alarm.txt` does. For an alarm, it reads the file, looks at its pictures, writes its
   answer to the folder's `decision.txt`, and goes back to waiting.

For the waiting in step 3:

```
until [ -f unittas-queue/done ] || [ -f "$(cat unittas-queue/run)/alarm.txt" ]; do sleep 2; done
```

A line appended to `unittas-queue/notify` is handed to your own `./request_task.sh`.

`unittas watch` is the same watcher in Python, with the same files, run from the folder the runs are made in. Its
request line is `unittas run`'s tests, and each run is watched. In unitTAS's own repository it takes the script's
lines as they are (`<suites> [filter]`, `probe [filter]`). It replaces `./unittas-watch.sh` once you restart into it.

The scripts run another project's game with a first word `@<folder>`: `./unittas.sh @../my-mod "end"`, or a watcher
request line `@<folder> <suites> [filter]`; the results stay in unitTAS's `unittas-results/`.

## Using unitTAS in a mod on GTNH's buildscript

Tried in a consumer check (a mod on GTNH's ExampleMod buildscript, with a coremod of its own), where unitTAS's tests
ran in that mod's development client and passed. Four pieces:

1. **The jar:** unitTAS's **release** jar (Searge names), not the `-dev` jar. RetroFuturaGradle renames it into the
   mod's own names; the `-dev` jar is in MCP `stable_12`'s names, which differ from that buildscript's
   (`getItemDamage` there is `getMetadata` in `stable_12`, and five more), so its calls would miss there.
2. **`repositories.gradle` and `dependencies.gradle`:** unitTAS from JitPack.

   ```groovy
   maven {
       name = 'JitPack'
       url = 'https://jitpack.io'
       content {
           includeGroup 'com.github.AsgerJon'
       }
   }
   ```

   ```groovy
   devOnlyNonPublishable(rfg.deobf('com.github.AsgerJon:unitTAS:0.1.0-dev19'))
   ```

   A jar on your own machine (unitTAS's `.local-maven/`, `~/.m2`) goes **as a file**: by module name from a local
   repository, RetroFuturaGradle 2.0.5 resolves it but silently doesn't rename it (it then matches only a file named
   `group-name-version.jar`), so the build compiles and the game fails at the first renamed call.

   ```groovy
   devOnlyNonPublishable(rfg.deobf(files('/path/to/unittas-0.1.0-dev19.jar')))
   ```

3. **`gradle.properties`:** Mixin on: `forceEnableMixins = true` (a mod with `usesMixins = true` has it already).
4. **`addon.gradle`:** the tests' own source set, `src/unittas/java`, compiled like the mod (Jabel included) and run
   in its development client, in no jar:

   ```groovy
   sourceSets {
       unittas {
           // lazily: the buildscript sets main's class paths (Minecraft on them) after this file is read
           compileClasspath += sourceSets.main.output + files({ sourceSets.main.compileClasspath })
           runtimeClasspath += sourceSets.main.output + files({ sourceSets.main.runtimeClasspath })
       }
   }
   configurations.unittasAnnotationProcessor.extendsFrom(configurations.annotationProcessor)
   tasks.named('runClient', JavaExec).configure {
       classpath(sourceSets.unittas.output)
   }
   ```

   No coremod argument: the buildscript's development run (`GradleStart`) finds unitTAS's coremod in its jar's
   manifest, as it finds UniMixins', beside the mod's own `coreModClass`. (Only `runClient` was tried; another run
   task, such as one for a newer Java, would take the same `classpath(...)` line.)

The mod's own code (what ships in its jar) must not name unitTAS's classes: unitTAS is a development-only
dependency, so such code compiles and then fails in a player's game. What the mod does differently during a run goes
into its `@TasPlugin`.

## Building unitTAS itself

unitTAS builds with Gradle on Unimined (nothing of GTNH's): `./gradlew build` makes `build/libs/unittas-<version>.jar`
(the release jar, in Searge names with its refmap, for a real game) and `unittas-<version>-dev.jar` (MCP
`stable_12` names). Gradle runs on Java 21 (8.10.2 runs on no newer than 23); the bytecode and the game are Java 8.
The scripts use the project's own Gradle cache, `.gradle-home/`; a session building inside its sandbox sets
`GRADLE_USER_HOME` to it too, so Minecraft is set up once, and runs `./gradlew --stop` before asking the watcher for
a run (a daemon left inside the sandbox could hold the cache's locks).

The probe for 26.3, 1.21.1 and 1.20.1 is a Java agent, built without Gradle: `python3 bin/build_agent.py [--minecraft
VERSION]` compiles it with Java 25's `javac` against the version's own client jar and libraries (from unitTAS's download
cache, each held to its sha1), for the version's Java (25 for 26.3, 21 for 1.21.1, 17 for 1.20.1), and makes
`agent/build/unittas-probe-VERSION.jar`. The code the versions share is `agent/src/modern/java`, compiled with each
version's own folder (`agent/src/v26`, `agent/src/v1_21_1`, `agent/src/v1_20_1`): its `Version` (what that version does
its own way, the same methods in each), what differs too widely to share (the view, the looks, the worlds), and its
hooks file. It needs no loader and no library: the game is started with `-javaagent:unittas-probe-VERSION.jar=GAME` (the
launcher's `--agent JAR`), and the probe puts its few hooks into the game's classes itself, naming only the JDK's
classes in them (a loader may hide the agent's jar from the game, as Fabric's does). It wraps each hooked method (the
original renamed `name$unittas` and made private, a method of the hooked one's name calling the hooks and then it), so
the game's own code is never edited, and the wrapping needs nothing but the JDK, on Java 17 and later: `python3 -m
unittest bin/tests/test_agent_wrap.py` checks it on every Java installed of 17, 21 and 25. For a version the game runs
under other names than Mojang's (before 26.1: obfuscated), the probe is written in Mojang's names all the same and
renamed as it loads, by a table of the version's names that the launcher writes once from the version's own obfuscation
log (`client_mappings`) and names to the agent (`-Dunittas.names=TABLE`); the log and the table stay in the download
cache, never shipped. `python3 -m unittest bin/tests/test_agent_names.py` checks the renaming on a small game of its
own, `bin/tests/test_agent_members.py` the names the probe reaches by reflection and the methods it hooks against
each obfuscated version's own, and `bin/tests/test_agent_reflectnames.py` a test's reflection by Mojang's names beside
each kind of table (beside Forge the classes keep Mojang's names, so the table, not the name, says a class is the
game's). Against an obfuscated version it is compiled against stubs of the version's classes in
Mojang's names, made once into the download cache from its client jar, never shipped. It runs in the version as Mojang
ships it, and beside whatever loader the mod under test brings (Fabric, NeoForge and Forge so far; before 26.1 Fabric
runs the game under its intermediary names, and the table goes on to them, from the intermediary jar Fabric's profile
names; NeoForge runs it under Mojang's, its installer having renamed 1.21.1 so, and needs no table; Forge 1.20.1 runs it
under Mojang's class names and SRG's member names (`m_91398_`), and the table goes on to those, from the MCP config's
names Forge's install keeps): a mod and its loader are the user's, taken as working. Its version is the root's
`mod_version`. The probe's version-free core, `src/probe-core/java`, is compiled into it and into the 1.7.10 jar.

The probe's own game tests (`python/tests/probe`) run with `python -m unittas.selftest [filter] [on PORT]` from the root
(through the watcher: `probe [filter] [on PORT]`). The port is a version and what runs it: `1.7.10-forge` (the
development client, the default), `26.3` (a real client from unitTAS's own launcher, as Mojang ships it), `26.3-fabric`
(the same with Fabric Loader, as a Fabric mod's tests would have it), `1.21.1` (a real client as Mojang ships it,
obfuscated), `1.21.1-fabric` (the same with Fabric Loader, under its intermediary names), `1.21.1-neoforge` (the same
with NeoForge, under Mojang's names), `26.3-neoforge` (26.3 with NeoForge), `1.20.1` or `1.20.1-fabric` (the same for
1.20.1), `1.20.1-forge` (1.20.1 with Forge, under SRG's names); on every port but 1.7.10's the probe is the Java agent.
A test written for every port names things by mcdex member and places from the port's start; one its version can't do
yet skips, saying which step brings it (`ports.py`). Every module runs on every port but those of 1.7.10 itself: its
live download (`test_download`), its release jar (`test_realclient`), the Java runner (`test_noresult`, `test_oldsaves`,
`test_core`'s `java.run`), its login race (`test_opening`), unitTAS's own 1.7.10 clients and test mod
(`test_specgames`, `test_mptest`), and its numbers for mcdex's members (`test_mcdexthings`). Multiplayer is 1.7.10's
so far (`test_server`, `test_join`, `test_players`, `test_multiplayer_run`).

unitTAS's own tests are in `src/self/java`: on `runClient`'s class path, in neither jar. `./unittas.sh self` must be
all ok. The `self-red` suite is red on purpose, in known ways (the report's outcomes and counts, the warnings, the
config put back): `./unittas.sh "self,self-red,nosuch"`, then `python3 bin/self_red_check.py` checks the report line
by line (`--python` for the Python twins' run, `--game DIR` for a run in another game folder than the development
client's). The development run starts Mixin as a real game does (UniMixins' `MixinTweaker`, `--tweakClass`) and names
the coremods FML doesn't find there on its own: UniMixins' (`AllCore`) and unitTAS's.

## Releasing

A release is a button: nine workflows, each a level (`micro`, `minor`, `major`) and a kind (`dev`, `rc`, `lts`),
run from GitHub's Actions tab ("Run workflow", on `main`: a press on any other branch is refused before anything is
read or written). Nobody sets the version or tags by hand. `bin/release_tooling/VERSION` holds what the buttons read:
the line of the last full release, the level locked for the next one (`LEVEL`), and its next dev and rc numbers. One
table, `release_state.py`, decides every press from it:

| State                         | Accepted                                                    | Needs its safety |
|-------------------------------|-------------------------------------------------------------|------------------|
| no cycle open (`LEVEL=none`)  | a level's `dev`: its version's `dev0`, the level locked     | yes              |
| a dev cycle open              | the locked level's `dev`: the next `devN`                   | no               |
|                               | a higher level's `dev`: its version's `dev0`, relocked      | yes              |
|                               | the locked level's `rc`: `rc0`, the dev cycle closed        | yes              |
| an rc cycle open              | the locked level's `rc`: the next `rcN`                     | no               |
|                               | the locked level's `lts`: the release, `LEVEL=none` again   | yes              |

A level leads to its version from the last full release `X.Y.Z`: micro to `X.Y.(Z+1)`, minor to `X.(Y+1).0`, major
to `(X+1).0.0`; a release always has an rc before it. Every other press is refused in the run's first job, which says
the state, why, and which buttons are accepted now, with the version each would make. Before the first full release
the counters stand at 0.0.1, so minor leads to 0.1.0: `minor-dev` makes its `0.1.0-devN`, then `minor-rc` and
`minor-lts` release it.

**Arming.** Each button has its own `.safety` file in `bin/release_tooling/` (`minor-rc.safety`, ...), all saying
`STOP`. For a press that needs its safety, write `ALLOW` in that button's file, commit, push, then press. The run's
first job decides the press from `VERSION` and that file as they stood in the commit the button was pressed on, sets
all nine back to `STOP` and pushes that whatever it decided, tests the release tooling (`python -B -m unittest discover
-s tests -t .` in `bin/release_tooling`), and only then stops the run unless the press may go on. So every press of
any button spends every arming.

**A run**, after the lock:

1. What can be checked without a display: the other tools' tests (`bin/tests`), the Python package's, that the version
   agrees across the tree (`version_stamp.py --check`), `./gradlew build`, and every version's probe
   (`bin/build_agent.py` on Java 25, for each version it knows). The game's own tests can't run there: run
   `./unittas.sh self` before pressing.
2. The version is named again from the branch tip (a press another run made obsolete meanwhile is refused there too)
   and stamped into `gradle.properties` (`mod_version`, which names both jars and goes into `mcmod.info`),
   `UnitTasMod.VERSION` (the `@Mod`'s), this README's recipes, and the Python package's `python/pyproject.toml` and
   `unittas.__version__` (as the version is, which the package's build spells as Python does: `0.1.0.dev3`); both jars
   are built, and every version's probe, and the Python package with the release's jars in it (`unittas/probes`,
   which a spec's `probe = "bundled"` uses); the counters advance by the same table. One commit (`dev X`, `rc X` or `LTS X`, as "Asger Jon Vistisen") and its tag
   `X` are pushed together, or neither is (if `main` moved meanwhile, or the tag is taken).
3. A GitHub release of that tag with both 1.7.10 jars, each version's probe (`unittas-probe-26.3-<version>.jar`, and
   1.21.1's and 1.20.1's the same way), and GitHub's generated notes (the commits and pull requests since the last
   release), titled `dev X` or `rc X` (pre-releases) or `X` (the latest release). For a draft you write yourself
   instead, the release step's `--generate-notes` becomes `--draft --notes ""`.
4. The Python package on PyPI (`pip install unittas`; a dev or rc release is a pre-release there, `pip install --pre
   unittas`), by a job of its own (`pypi`) with WorkToy's publish step (`pypa/gh-action-pypi-publish`), by trusted
   publishing: PyPI trusts the button's workflow, and no token is kept anywhere.

Pull after every press. If only the last jobs fail (the tag is pushed by then), "Re-run failed jobs" makes the
release, or the upload, from the same tag, jars and package; pressing the button again would make the next version.
The buttons run one at a time (one concurrency group), and need `main` open to pushes from Actions. They use
GitHub's own actions, the runner's `gh`, and PyPA's publish action.

**PyPI, once:** PyPI has to trust each button before its first upload. On pypi.org, under the account's publishing
settings, a trusted publisher for each of the nine: PyPI project `unittas`, owner `AsgerJon`, repository `unitTAS`,
workflow `minor-dev.yml` (and `micro-dev.yml`, ... each button's own file), no environment. Before the project's
first upload these are "pending" publishers, and the first upload makes the project.

`mod_version` isn't edited by hand: the stamp refuses when `gradle.properties`, `UnitTasMod.VERSION`, this README's
recipes, `python/pyproject.toml` and `unittas.__version__` disagree. JitPack builds a tag the first time someone asks for `com.github.AsgerJon:unitTAS:<tag>`
(`jitpack.yml` gives it Java 21); the tag's commit already carries its version. The state machine, the scripts and the
safeties are WorkToy's, adapted, and so is the PyPI upload: unitTAS's runs also push the version commit and its tag
together, make the release and the upload in jobs of their own, and paste no expression into a script.

## Other tools

- `./server-side-check.py` finds code a dedicated server can't load in a mod's built classes: references from its
  common classes changed on the branch (`--base REF`, or a file list with `--stdin`) to `@SideOnly(CLIENT)` members
  and classes and to `net.minecraft.client`.
- `./multiplayer-test.sh [name]` starts a dedicated server and two clients to try multiplayer by hand.
- `unittas compare before/report.txt after/report.txt` (or `python3 bin/compare_reports.py ...`, which needs nothing
  installed) compares two runs test by test: the tests only one ran, the outcomes that changed (a failure now marked
  `@ExpectedFailure` listed apart), every `NO RESULT` (no verdict is the same as nothing), unitTAS's problems; times
  and details don't count. For a change that must leave the results as they were. It reads Java and Python reports
  alike.

## License

Apache 2.0: see `LICENSE`.

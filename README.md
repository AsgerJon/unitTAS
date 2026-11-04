# unitTAS
Unit testing for minecraft mods that relies on real TAS-like tests in real minecraft clients.

Tests that play the real game, in the manner of Python's `unittest`, for Minecraft 1.7.10 Forge mods. A real client
opens, a fresh test world is made, and test classes drive the game tick by tick (commands, typing in the chat, keys,
looking around) and check what happened (inventory, entities, blocks, chat, sounds). Screenshots on failure or on
request.

unitTAS is a mod of its own (mod id `unittas`, package `io.github.asgerjon.unittas`). It sleeps in an ordinary game
until a request file left by `./unittas.sh` wakes it. It needs a Mixin loader for 1.7.10 in the game (UniMixins, for
one).

## Running

```
./unittas.sh                     # every suite
./unittas.sh commands            # one suite
./unittas.sh commands,combat     # several
./unittas.sh commands Give       # only tests whose Class.method name contains "Give"
./unittas.sh self                # unitTAS's own tests
```

The script starts `./gradlew runClient`, shows each test as it finishes and prints the report when the game quits.
Everything lands in `unittas-results/<time>/` (`unittas-results/latest` is the newest):

- `report.txt`: one line per test (`ok`, `FAIL`, `ERROR`, `skipped`, `expected failure`, `unexpected success`); for
  each that failed, the assertion and where (or the stack trace), the chat during the test and its screenshot; under
  any test, its warnings. unitTAS's own problems (a suite that doesn't exist, a class that can't run, a run that
  stopped) are lines of their own, `problem`, counted apart from the tests: `Ran 16 tests in 41.0 s, 1 problem
  outside them`. Ends with `OK (expected failures=2)` or `FAILED (failures=1, errors=…, unexpected successes=…,
  problems=…)`, as unittest counts.
- `screenshots/`: one per failed test (taken before its `tearDown`), plus the ones tests take on purpose.
- `progress.txt`, `gradle.log`: the run as it went.

The test world is `run/client/saves/unittas`, made new each run; no other save is touched, and your `options.txt` and
`config/` are kept aside and put back as they were (a file a test changed restored, one it made removed). A run
refuses to start beside a game already open in `run/client`. The run needs no focus; on KDE, `unittas.kwinrule` and
`./unittas-desktop.sh` keep its window (titled and classed `unitTAS`) off your desktop.

## Writing tests

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

A test class extends `io.github.asgerjon.unittas.TasTestCase` and is marked `@TasSuite("name")`; unitTAS finds it
through Forge's annotation table, so nothing else lists it. Public methods named `test…` (inherited ones too) are the
tests, run in name order, each on a new instance, with `setUp()` before and `tearDown()` after. A test runs on its own
thread and asks the game for each step.

- **Commands:** `command(text)` runs it as the player and returns a `TasCommand` (`lines()`, `errors()`, `result()`).
  `type(text)` opens the chat and types key by key; its `TasChat` has `text()`, `suggestions()`, `usage()`,
  `key(…)`, `typeMore(text)`, `enter()`, `close()`.
- **Steps:** `onServer(() -> …)` and `onClient(() -> …)` run a step on that thread and return its result; inside a
  server step `player()` and `world()` are the server's. Never touch game objects outside a step (`player()`,
  `world()`, `entitiesNear()` or `runCommand()` outside a server step put a warning in the report, with where), and
  never wait for ticks inside one.
- **Waiting:** `ticks(n)`, `serverTicks(n)`, `waitUntil("what", () -> condition, maxTicks)` (on the server),
  `waitUntilOnClient(…)`. A wait gives up only when no tick has come for 15 s, so a slow game still gets there.
- **Sounds:** `waitForSound("minecraft:random.bow", maxTicks)`, `soundsHeard()`, `clearSounds()`.
- **Things:** `held()`, `inventory()`, `setHeld(stack)`, `id(stack)` (`minecraft:wool:14`),
  `spawn(EntityZombie::new, x, y, z)`, `entitiesNear(Type.class, radius)`, `difficulty(EnumDifficulty.PEACEFUL)`.
- **Input:** `look(yaw, pitch)`, `hold(key, ticks)`, `tap(key)`, `keyDown(key)` / `keyUp(key)`,
  `cameraView(0|1|2)`.
- **Pictures:** `screenshot("name")`; `resultsFolder()` is the run's folder.
- **Asserts**, as unittest's, each with an optional message last: `assertEqual`, `assertNotEqual`, `assertTrue`,
  `assertFalse`, `assertIsNone`, `assertIsNotNone`, `assertIn`, `assertNotIn`, `assertGreater`, `assertAlmostEqual`
  (its third argument is the allowed difference), `fail`, `skipTest`; for commands `assertSaid`, `assertError`,
  `assertNoError`. ItemStacks are never equal to one another: compare `id(stack)` and the size.
- `timeoutSeconds()` (default 60) stops a test that hangs.
- `@ExpectedFailure("why")` on a test (or its class), as unittest's `expectedFailure`: a failure in the test itself is
  an `expected failure` and the run can still be OK; a pass is an `unexpected success`, which fails the run (the mark
  can go). setUp, tearDown and a test that ran out of time stay what they are.

**The world:** flat (the surface is y 3), creative, cheats, seed 20261029, Easy, always noon, no weather, no mob
spawning. Before every test the player is put back at 0.5 4 0.5 looking south (creative, not flying, empty inventory,
no experience, no effects, full health) and every other entity is removed. Blocks stay, so tests that build use their
own spot. Undead burn at noon: give zombies and skeletons a helmet.

## A mod's own part

What unitTAS can't know of a mod goes in a class that implements `TasHooks` and is marked `@TasPlugin` (public, no
constructor arguments). Every method defaults to doing nothing:

- `beforeRun()` / `afterRun()` (client thread): the mod's settings as its tests expect them, and back after.
- `resetPlayer(EntityPlayerMP)` (server thread, between tests): what the mod keeps of the player besides.
- `chatText`, `chatSuggestions`, `chatUsage` (client thread): for a mod with a chat screen of its own.

## Using unitTAS in a mod on GTNH's buildscript

Tried in a consumer check, where unitTAS's tests passed in another mod's development client. Take unitTAS's
**release** jar (Searge names): RetroFuturaGradle renames it into the mod's names, and the `-dev` jar's MCP names
differ from that buildscript's.

1. `repositories.gradle` and `dependencies.gradle`: unitTAS from JitPack.

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
   devOnlyNonPublishable(rfg.deobf('com.github.AsgerJon:unitTAS:0.1.0-dev2'))
   ```

   A jar on your own machine goes **as a file**: by module name from a local repository, RetroFuturaGradle 2.0.5
   resolves it but silently doesn't rename it.

   ```groovy
   devOnlyNonPublishable(rfg.deobf(files('/path/to/unittas-0.1.0-dev2.jar')))
   ```

2. `gradle.properties`: `forceEnableMixins = true` (a mod with `usesMixins = true` has it already).
3. `addon.gradle`: the tests' own source set, `src/unittas/java`, run in the development client and in no jar:

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

No coremod argument is needed: the development run finds unitTAS's coremod in its jar. From unitTAS's folder,
`./unittas.sh @../my-mod "suites"` runs that mod's game.

## Hangs, and watching a run

- A step the game doesn't run in 15 s is an error, a test past its `timeoutSeconds()` is stopped, and the world has
  60 s to load. A stuck game gets its threads dumped (`hang-threads.txt`). `./unittas.sh` stops a run that writes
  nothing for 10 minutes (`UNITTAS_STALL_SECONDS`); `./hang-dump.sh` dumps threads by hand.
- Every run shows what it's doing: `screenshots/watch-live.png` every 10 s, and `watch.txt` every 5 s (the test,
  what it waits for, whether the client and the server tick).
- A watched run (`UNITTAS_WATCHED=1`) raises an alarm instead of giving up: `alarm.txt` in the results, answered with
  one line in `decision.txt` (`N wait <seconds>`, `N fail <why>` or `N abort <why>`). Without an answer in 5 minutes
  it does what it does unwatched. The watcher judges only whether the game is stuck, never whether a test passed.
- `./unittas-watch.sh` takes runs through files in `unittas-queue/`, for a session that can't open windows itself
  (an LLM in a sandbox, say).

## Old saves

`./unittas.sh oldsaves` runs a mod's `oldsaves` suite in vanilla 1.7.10's own worlds, in a Prism Launcher instance
(`unitTAS_vanilla_1_7_10`: Forge 10.13.4.1614, Java 8). Make the worlds once with
`python3 oldsaves/make_vanilla_worlds.py`, which runs Mojang's 1.7.10 server headless (you accept its EULA in
`run/oldsaves/server/eula.txt`).

## Building and releasing

`./gradlew build` (Gradle on Unimined: Java 21 runs Gradle, the bytecode is Java 8) makes
`build/libs/unittas-<version>.jar` (the release jar, Searge names, with its refmap) and `unittas-<version>-dev.jar`
(MCP `stable_12` names).

unitTAS's own tests are in `src/self/java`, in neither jar. `./unittas.sh self` must be all ok. The `self-red` suite is
red on purpose, in known ways (the report's outcomes and counts, the warnings, the config put back):
`./unittas.sh "self,self-red,nosuch"`, then `python3 bin/self_red_check.py` checks the report line by line.

Releases are buttons in GitHub's Actions tab: `dev`, `rc`, `lts-micro`, `lts-minor` and `lts-major`. Nobody edits the
version or tags by hand; `bin/release_tooling/VERSION` holds the counters. `rc` and the `lts-*` buttons run only when
their `.safety` file in `bin/release_tooling/` said `ALLOW` in the pressed commit, and every press sets them all back
to `STOP`. A run tests, stamps the version into `gradle.properties`, `UnitTasMod.VERSION` and this README, builds,
pushes one commit with its tag, and makes the GitHub release with both jars. Pull after every press. JitPack:
`com.github.AsgerJon:unitTAS:<tag>`.

## Other tools

- `./server-side-check.py` finds code a dedicated server can't load in a mod's built classes (references to
  `@SideOnly(CLIENT)` members and to `net.minecraft.client`).
- `./multiplayer-test.sh [name]` starts a dedicated server and two clients to try multiplayer by hand.
- `python3 bin/compare_reports.py before/report.txt after/report.txt` compares two runs test by test: the tests only
  one ran, the outcomes that changed (a failure now marked `@ExpectedFailure` apart), unitTAS's problems. For a change
  that must leave the results as they were.

## License

Apache 2.0: see `LICENSE`.

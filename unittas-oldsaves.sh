#!/usr/bin/env bash
# unitTAS on old saves: the saves in run/oldsaves/vanilla/ (made by vanilla 1.7.10 with oldsaves/make_vanilla_worlds.py),
# opened by unitTAS's save mode twice each (as vanilla left them, then as the mod's game saved them) and checked
# against their pristine copies by the mod's `oldsaves` suite.
#   ./unittas.sh oldsaves            the release jar, in a real client (Forge, the mod, its libraries)
#   ./unittas.sh oldsaves dev        the dev client (runClient), to try the save mode itself
#   ./unittas.sh oldsaves dev@devcheck   another set of saves: run/oldsaves/devcheck/ (for trying the mode)
#   ./unittas.sh oldsaves inspect    only reports the real client: the launcher's command, its game folder
#   ./unittas.sh oldsaves instance   no saves: the release jar (and run/oldsaves/mods/*.jar) in the real client, a
#                                    normal run of every suite its jars hold, in the fresh test world. For unitTAS's own
#                                    jar that is none: the check that the jar starts outside a development run (the game
#                                    must reach the world and report "Ran 0 tests", OK)
# The watcher runs it as "oldsaves" (or "oldsaves dev"). Results: unittas-results/<time>/ as for any run, with the
# saves as the game left them in saves-after/ and the game's log in game.log.
# The real client: unitTAS's own launcher (bin/launch_client.py) starts Minecraft 1.7.10 with Forge 10.13.4.1614 on
# Java 8 from what the Gradle cache already holds (no other launcher, nothing downloaded), in run/release/. Each run its
# mods are the mod's release jar and run/oldsaves/mods/*.jar (its libraries, UniMixins at least; what was there goes
# into the results), and the saves are fresh copies, moved into the results after.
set -u
cd "$(dirname "$0")" || exit 1
ROOT=$(pwd)
# one Gradle cache for this project, whoever runs Gradle (the watcher outside a session's sandbox, the session inside
# it): Minecraft is downloaded and remapped once; UNITTAS_GRADLE_HOME names another
export GRADLE_USER_HOME="${UNITTAS_GRADLE_HOME:-$ROOT/.gradle-home}"
MODE=${1:-release}
SET=vanilla
case "$MODE" in
	*@*) SET=${MODE#*@}; MODE=${MODE%%@*} ;;
esac
PRISTINE="$ROOT/run/oldsaves/$SET"
GAME="$ROOT/run/release"
LAUNCHER="$ROOT/bin/launch_client.py"
START=$(date +%s)
clock() {
	local elapsed=$(( $(date +%s) - START ))
	printf '%02d:%02d' $((elapsed / 60)) $((elapsed % 60))
}
say() {
	printf '[%s] %s\n' "$(clock)" "$*"
}

# ---------------------------------------------------------------- the saves (inspect looks only at the real client)
SAVES=""
for dir in "$PRISTINE"/*/; do
	[ -f "$dir/level.dat" ] || continue
	name=$(basename "$dir")
	SAVES="${SAVES:+$SAVES,}$name"
done
if [ "$MODE" != "inspect" ] && [ "$MODE" != "instance" ]; then
	if [ -z "$SAVES" ]; then
		echo "No saves in $PRISTINE: make them first (python3 oldsaves/make_vanilla_worlds.py)."
		exit 1
	fi
	say "saves: $SAVES"
fi

# Fresh copies into a game folder's saves; a copy left by an earlier run goes into that run's results, not deleted.
copy_saves() {
	local game=$1 results=$2
	mkdir -p "$game/saves" "$results/saves-before-this-run"
	local name
	for name in ${SAVES//,/ }; do
		if [ -e "$game/saves/$name" ]; then
			mv "$game/saves/$name" "$results/saves-before-this-run/"
		fi
		cp -r "$PRISTINE/$name" "$game/saves/$name"
	done
	rmdir "$results/saves-before-this-run" 2>/dev/null
	return 0
}

# After the run: the copies as the game left them, into the results.
keep_saves() {
	local game=$1 results=$2
	mkdir -p "$results/saves-after"
	local name
	for name in ${SAVES//,/ }; do
		[ -e "$game/saves/$name" ] && mv "$game/saves/$name" "$results/saves-after/"
	done
	return 0
}

if [ "$MODE" = "dev" ]; then
	# the dev client: ./unittas.sh does the run, with the save list in its request
	STAMP=${UNITTAS_STAMP:-$(date +%Y-%m-%d_%H-%M-%S)}
	mkdir -p "$ROOT/unittas-results/$STAMP"
	copy_saves "$ROOT/run/client" "$ROOT/unittas-results/$STAMP"
	UNITTAS_EXTRA="saves=$SAVES
oldsaves=$PRISTINE" UNITTAS_STAMP="$STAMP" ./unittas.sh oldsaves
	CODE=$?
	keep_saves "$ROOT/run/client" "$ROOT/unittas-results/$STAMP"
	exit $CODE
fi
if [ "$MODE" = "inspect" ]; then
	STAMP=${UNITTAS_STAMP:-$(date +%Y-%m-%d_%H-%M-%S)}
	RESULTS="$ROOT/unittas-results/$STAMP"
	mkdir -p "$RESULTS"
	ln -sfn "$STAMP" "$ROOT/unittas-results/latest"
	{
		echo "== the launcher's command (bin/launch_client.py --dry-run)"
		python3 -I "$LAUNCHER" --game "$GAME" --dry-run 2>&1
		echo "== the game folder $GAME"
		ls -la "$GAME" 2>&1
		echo "-- mods"; ls -la "$GAME/mods" 2>&1
		echo "-- saves"; ls "$GAME/saves" 2>&1
		echo "-- the last game's log"
		tail -n 40 "$GAME/logs/latest.log" 2>&1
	} > "$RESULTS/inspect.txt" 2>&1
	echo "report: unittas-results/$STAMP/inspect.txt"
	echo "Ran 0 tests" > "$RESULTS/report.txt"
	exit 0
fi
if [ "$MODE" != "release" ] && [ "$MODE" != "instance" ]; then
	echo "Use: ./unittas.sh oldsaves [dev|release|inspect|instance]"
	exit 1
fi

STAMP=${UNITTAS_STAMP:-$(date +%Y-%m-%d_%H-%M-%S)}
RESULTS="$ROOT/unittas-results/$STAMP"
mkdir -p "$RESULTS"
ln -sfn "$STAMP" "$ROOT/unittas-results/latest"

# ---------------------------------------------------------------- the release jar
say "building the release jar (./gradlew assemble; its log: unittas-results/$STAMP/build.log)"
if ! ./gradlew --console=plain assemble > "$RESULTS/build.log" 2>&1; then
	echo "The build failed. The end of its log:"
	tail -n 25 "$RESULTS/build.log"
	exit 1
fi
# the newest jar the build made, but not its dev, sources, API or javadoc jars
JAR=$(ls -t build/libs/*.jar 2>/dev/null | grep -v -E -- '-(dev|sources|api|javadoc|preshadow)\.jar$' | head -n 1)
if [ -z "$JAR" ]; then
	echo "The build made no release jar in build/libs."
	exit 1
fi
say "the jar: $JAR"

# ---------------------------------------------------------------- the real client
if ! python3 -I "$LAUNCHER" --game "$GAME" --dry-run > "$RESULTS/launch-command.txt" 2>&1; then
	echo "unitTAS's launcher can't start the game:"
	cat "$RESULTS/launch-command.txt"
	exit 1
fi

# ---------------------------------------------------------------- filling the game folder
mkdir -p "$GAME/mods" "$GAME/unittas"
if [ -n "$(ls -A "$GAME/mods" 2>/dev/null)" ]; then
	mkdir -p "$RESULTS/mods-before-this-run"
	mv "$GAME/mods/"* "$RESULTS/mods-before-this-run/"
fi
cp "$JAR" "$GAME/mods/"
for lib in "$ROOT"/run/oldsaves/mods/*.jar; do
	[ -f "$lib" ] && cp "$lib" "$GAME/mods/"
done
say "mods: $(ls "$GAME/mods" | tr '\n' ' ')"
copy_saves "$GAME" "$RESULTS"
{
	if [ "$MODE" = "instance" ]; then
		# every suite the game folder's jars hold, in the fresh test world (no saves)
		echo "suites="
	else
		echo "suites=oldsaves"
		echo "saves=$SAVES"
		echo "oldsaves=$PRISTINE"
	fi
	echo "filter="
	echo "results=$RESULTS"
	[ "${UNITTAS_WATCHED:-0}" = 1 ] && echo "watched=true"
	echo "watch.pictures=${UNITTAS_PICTURE_SECONDS:-10}"
	echo "watch.decide=${UNITTAS_DECIDE_SECONDS:-300}"
} > "$GAME/unittas/request.properties"

# ---------------------------------------------------------------- the run
if [ "${UNITTAS_DISPLAY:-nested}" = plain ]; then
	say "$(./unittas-desktop.sh)"
else
	say "test window: in gamescope (UNITTAS_DISPLAY=${UNITTAS_DISPLAY:-nested}), never focused"
fi
say "starting the real client (its output: unittas-results/$STAMP/client.log)"
# the display and the launcher each become the next (exec), so this is the game's display's process id
"$ROOT/unittas-display.sh" python3 -I "$LAUNCHER" --game "$GAME" > "$RESULTS/client.log" 2>&1 &
GAME_PID=$!
SPIN='|/-\'
spin=0
shown=0
gone=""
launched=$(date +%s)
deadline=$(( launched + 2400 ))
while [ ! -f "$RESULTS/report.txt" ]; do
	if [ -f "$RESULTS/progress.txt" ]; then
		total=$(wc -l < "$RESULTS/progress.txt")
		if [ "$total" -gt "$shown" ]; then
			printf '\r\033[K'
			tail -n +$((shown + 1)) "$RESULTS/progress.txt" | head -n $((total - shown)) | while IFS= read -r line; do say "$line"; done
			shown=$total
		fi
	fi
	# no word from the game in 5 minutes, and still running: stuck before unitTAS woke
	if [ ! -f "$RESULTS/progress.txt" ] && [ "$(date +%s)" -gt "$(( launched + 300 ))" ]; then
		printf '\r\033[K'
		cp "$GAME/logs/latest.log" "$RESULTS/game.log" 2>/dev/null
		echo "The game didn't get to unitTAS in 5 minutes. Its output: $RESULTS/client.log; its log: $RESULTS/game.log"
		kill "$GAME_PID" 2>/dev/null
		rm -f "$GAME/unittas/request.properties"
		keep_saves "$GAME" "$RESULTS"
		exit 1
	fi
	# the game went away without a report (it crashed, before unitTAS woke or after): 30 s for the report, then stop
	if ! kill -0 "$GAME_PID" 2>/dev/null; then
		gone=${gone:-$(date +%s)}
		if [ $(( $(date +%s) - gone )) -gt 30 ] && [ ! -f "$RESULTS/report.txt" ]; then
			printf '\r\033[K'
			cp "$GAME/logs/latest.log" "$RESULTS/game.log" 2>/dev/null
			cp "$GAME/logs/fml-client-latest.log" "$RESULTS/fml-client.log" 2>/dev/null
			echo "The game ended without a report (a crash?). Its output: $RESULTS/client.log; its log: $RESULTS/game.log;"
			echo "crash reports in $GAME/crash-reports/"
			rm -f "$GAME/unittas/request.properties"
			keep_saves "$GAME" "$RESULTS"
			exit 1
		fi
	else
		gone=""
	fi
	if [ "$(date +%s)" -gt "$deadline" ]; then
		printf '\r\033[K'
		cp "$GAME/logs/latest.log" "$RESULTS/game.log" 2>/dev/null
		echo "No report in 40 minutes. Its output: $RESULTS/client.log; its log: $RESULTS/game.log"
		kill "$GAME_PID" 2>/dev/null
		rm -f "$GAME/unittas/request.properties"
		keep_saves "$GAME" "$RESULTS"
		exit 1
	fi
	printf '\r\033[K[%s] %s waiting for the game' "$(clock)" "${SPIN:$((spin++ % 4)):1}"
	sleep 0.5
done
printf '\r\033[K'
# the game quits after the report; its log is complete once it has
for _ in $(seq 1 120); do
	kill -0 "$GAME_PID" 2>/dev/null || break
	sleep 1
done
cp "$GAME/logs/latest.log" "$RESULTS/game.log" 2>/dev/null
cp "$GAME/logs/fml-client-latest.log" "$RESULTS/fml-client.log" 2>/dev/null
keep_saves "$GAME" "$RESULTS"
echo
grep -v ' \.\.\. ok (' "$RESULTS/report.txt"
echo
echo "Full report: unittas-results/latest/report.txt  (took $(clock))"
tail -n 1 "$RESULTS/report.txt" | grep -q '^OK' && exit 0 || exit 1

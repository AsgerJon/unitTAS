#!/usr/bin/env bash
# unitTAS on old saves: the saves in run/oldsaves/vanilla/ (made by vanilla 1.7.10 with oldsaves/make_vanilla_worlds.py),
# opened by unitTAS's save mode twice each (as vanilla left them, then as the mod's game saved them) and checked
# against their pristine copies by the mod's `oldsaves` suite.
#   ./unittas.sh oldsaves            the release jar, in a Prism instance (Forge, the mod, its libraries)
#   ./unittas.sh oldsaves dev        the dev client (runClient), to try the save mode itself
#   ./unittas.sh oldsaves dev@devcheck   another set of saves: run/oldsaves/devcheck/ (for trying the mode)
#   ./unittas.sh oldsaves inspect    only reports the Prism instance (components, Java, mods, saves) and Prism's log
# The watcher runs it as "oldsaves" (or "oldsaves dev"). Results: unittas-results/<time>/ as for any run, with the
# saves as the game left them in saves-after/ and the game's log in game.log.
# The Prism instance: unitTAS_vanilla_1_7_10 unless unittas-oldsaves.conf names another (INSTANCE_NAME; Minecraft
# 1.7.10, Forge 10.13.4.1614, Java 8). It is looked for where Prism's settings say its instances are, in
# ~/.local/share/PrismLauncher and the Flatpak's folder; unittas-oldsaves.conf may say instead (PRISM_CMD, PRISM_DIR:
# Prism's data folder, INSTANCES_DIR, INSTANCE: the instance's folder). Each run its mods are the mod's release jar
# and run/oldsaves/mods/*.jar (its libraries; what was there goes into the results), and the saves are fresh copies,
# moved into the results after (the instance's own saves stay as they are).
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
INSTANCE_NAME="unitTAS_vanilla_1_7_10"
PRISM_CMD="" PRISM_DIR="" INSTANCES_DIR="" INSTANCE=""
# shellcheck disable=SC1091
[ -f "$ROOT/unittas-oldsaves.conf" ] && . "$ROOT/unittas-oldsaves.conf"
START=$(date +%s)
clock() {
	local elapsed=$(( $(date +%s) - START ))
	printf '%02d:%02d' $((elapsed / 60)) $((elapsed % 60))
}
say() {
	printf '[%s] %s\n' "$(clock)" "$*"
}

# ---------------------------------------------------------------- the saves (inspect looks only at the instance)
SAVES=""
for dir in "$PRISTINE"/*/; do
	[ -f "$dir/level.dat" ] || continue
	name=$(basename "$dir")
	SAVES="${SAVES:+$SAVES,}$name"
done
if [ "$MODE" != "inspect" ]; then
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

# Prism's command, and the instance's folders, unless unittas-oldsaves.conf gave them.
find_prism() {
	if [ -z "$PRISM_CMD" ]; then
		if command -v prismlauncher >/dev/null; then
			PRISM_CMD=prismlauncher
		elif command -v flatpak >/dev/null && flatpak info org.prismlauncher.PrismLauncher >/dev/null 2>&1; then
			PRISM_CMD="flatpak run org.prismlauncher.PrismLauncher"
		fi
	fi
	if [ -z "$INSTANCES_DIR" ] || [ -z "$INSTANCE" ]; then
		# The instances folder the conf names, if it does; then Prism's data folders, whose prismlauncher.cfg says
		# (InstanceDir) where the instances are, maybe on another disk. An instance is found by its folder or by the
		# name in its instance.cfg. Answer: "data folder (or nothing)|instances folder|instance folder".
		local found found_data
		found=$(python3 -I - "$INSTANCE_NAME" "$INSTANCES_DIR" "$HOME/.local/share/PrismLauncher" \
			"$HOME/.var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher" <<'PY'
import os, sys
wanted, known = sys.argv[1], sys.argv[2]
places = [('', known)] if known else []
for base in sys.argv[3:]:
    cfg = os.path.join(base, 'prismlauncher.cfg')
    if not os.path.isfile(cfg):
        continue
    instances = 'instances'
    for line in open(cfg, encoding='utf-8', errors='replace'):
        if line.startswith('InstanceDir='):
            instances = line.split('=', 1)[1].strip()
    places.append((base, instances if os.path.isabs(instances) else os.path.join(base, instances)))
for base, instances in places:
    if not os.path.isdir(instances):
        continue
    for folder in sorted(os.listdir(instances)):
        name = folder
        instance_cfg = os.path.join(instances, folder, 'instance.cfg')
        if os.path.isfile(instance_cfg):
            for line in open(instance_cfg, encoding='utf-8', errors='replace'):
                if line.startswith('name='):
                    name = line.split('=', 1)[1].strip()
        if wanted in (folder, name):
            print('|'.join((base, instances, folder)))
            sys.exit(0)
PY
		)
		if [ -n "$found" ]; then
			IFS='|' read -r found_data INSTANCES_DIR INSTANCE <<< "$found"
			# found through the conf's instances folder: the conf's data folder (if any) stays
			[ -n "$found_data" ] && PRISM_DIR=$found_data
		fi
	fi
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
	find_prism
	DIR="$INSTANCES_DIR/$INSTANCE"
	{
		echo "== Prism: ${PRISM_CMD:-not found}, data folder ${PRISM_DIR:-unknown}"
		echo "== instance $INSTANCE_NAME: ${INSTANCE:-not found} in ${INSTANCES_DIR:-?}"
		ls -la "$DIR" 2>&1
		echo "== mmc-pack.json"
		cat "$DIR/mmc-pack.json" 2>&1
		echo "== instance.cfg (Java, memory, window, name)"
		grep -E '^(name|InstanceType|OverrideJava|JavaPath|JavaVersion|JavaArchitecture|OverrideMemory|MinMemAlloc|MaxMemAlloc|OverrideWindow|MinecraftWinWidth|MinecraftWinHeight|LaunchMaximized|JvmArgs|ManagedPack)' "$DIR/instance.cfg" 2>&1
		echo "== patches"
		ls -la "$DIR/patches" 2>&1
		for game in "$DIR/minecraft" "$DIR/.minecraft"; do
			[ -d "$game" ] || continue
			echo "== game folder $game"
			ls -la "$game" 2>&1
			echo "-- mods"; ls -la "$game/mods" 2>&1
			echo "-- saves"; ls "$game/saves" 2>&1
		done
		echo "== Prism's log (the last launches)"
		for log in "$PRISM_DIR/logs/PrismLauncher-0.log" "$PRISM_DIR/PrismLauncher-0.log"; do
			# not KDE's file-watcher lines (kf.kio): they name paths, unitTAS's among them, and drown the rest
			[ -f "$log" ] && grep -n -i -E 'metadata|meta\.|failed|error|unitTAS|Network|download' "$log" | grep -v 'kf\.kio' | tail -n 60
		done
	} > "$RESULTS/inspect.txt" 2>&1
	echo "report: unittas-results/$STAMP/inspect.txt"
	echo "Ran 0 tests" > "$RESULTS/report.txt"
	exit 0
fi
if [ "$MODE" != "release" ]; then
	echo "Use: ./unittas.sh oldsaves [dev|release|inspect]"
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

# ---------------------------------------------------------------- Prism and the instance
find_prism
if [ -z "$PRISM_CMD" ]; then
	echo "Prism Launcher is needed: install it. (Found no prismlauncher command and no Flatpak; a Prism started some other"
	echo "way goes in unittas-oldsaves.conf as PRISM_CMD=<its command>.)"
	exit 1
fi
if [ -z "$INSTANCES_DIR" ] || [ -z "$INSTANCE" ]; then
	echo "No Prism instance called $INSTANCE_NAME (looked where Prism's settings say its instances are, in"
	echo "~/.local/share/PrismLauncher and the Flatpak's folder). Make it in Prism (Minecraft 1.7.10, Forge 10.13.4.1614,"
	echo "Java 8) and launch it once; somewhere else, put INSTANCES_DIR and INSTANCE (its folder) in unittas-oldsaves.conf."
	exit 1
fi
DIR="$INSTANCES_DIR/$INSTANCE"
GAME="$DIR/minecraft"
[ -d "$GAME" ] || GAME="$DIR/.minecraft"
if [ ! -f "$DIR/mmc-pack.json" ] || [ ! -d "$GAME" ]; then
	echo "The Prism instance $INSTANCE_NAME ($DIR) has no game folder yet: launch it once in Prism."
	exit 1
fi
if ! grep -q '"net.minecraftforge"' "$DIR/mmc-pack.json"; then
	echo "The instance $INSTANCE_NAME has no Forge: Prism > Edit > Version > Install Forge (10.13.4.1614)."
	exit 1
fi

# ---------------------------------------------------------------- filling the test instance
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
	echo "suites=oldsaves"
	echo "filter="
	echo "results=$RESULTS"
	echo "saves=$SAVES"
	echo "oldsaves=$PRISTINE"
	[ "${UNITTAS_WATCHED:-0}" = 1 ] && echo "watched=true"
	echo "watch.pictures=${UNITTAS_PICTURE_SECONDS:-10}"
	echo "watch.decide=${UNITTAS_DECIDE_SECONDS:-300}"
} > "$GAME/unittas/request.properties"

# ---------------------------------------------------------------- the run
say "$(./unittas-desktop.sh)"
say "starting $INSTANCE_NAME"
# shellcheck disable=SC2086
$PRISM_CMD ${PRISM_DIR:+--dir "$PRISM_DIR"} --launch "$INSTANCE" > "$RESULTS/prism.log" 2>&1 &
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
	# no word from the game in 5 minutes: it never started (Prism's own trouble, as its metadata failing once)
	if [ ! -f "$RESULTS/progress.txt" ] && [ "$(date +%s)" -gt "$(( launched + 300 ))" ]; then
		printf '\r\033[K'
		cp "$GAME/logs/latest.log" "$RESULTS/game.log" 2>/dev/null
		tail -n 200 "$PRISM_DIR/logs/PrismLauncher-0.log" > "$RESULTS/prism-launcher.log" 2>/dev/null
		echo "The game didn't start in 5 minutes. Prism's log: $RESULTS/prism-launcher.log, its output: $RESULTS/prism.log"
		rm -f "$GAME/unittas/request.properties"
		keep_saves "$GAME" "$RESULTS"
		exit 1
	fi
	# the game started, then went away without a report (it crashed): 30 s for the report to land, then stop waiting
	if [ -f "$RESULTS/progress.txt" ] && ! pgrep -f "$DIR" >/dev/null; then
		gone=${gone:-$(date +%s)}
		if [ $(( $(date +%s) - gone )) -gt 30 ] && [ ! -f "$RESULTS/report.txt" ]; then
			printf '\r\033[K'
			cp "$GAME/logs/latest.log" "$RESULTS/game.log" 2>/dev/null
			cp "$GAME/logs/fml-client-latest.log" "$RESULTS/fml-client.log" 2>/dev/null
			echo "The game ended without a report (a crash?). Its log: $RESULTS/game.log; crash reports in $GAME/crash-reports/"
			keep_saves "$GAME" "$RESULTS"
			exit 1
		fi
	else
		gone=""
	fi
	if [ "$(date +%s)" -gt "$deadline" ]; then
		printf '\r\033[K'
		cp "$GAME/logs/latest.log" "$RESULTS/game.log" 2>/dev/null
		echo "No report in 40 minutes. Prism's log: $RESULTS/prism.log; the game's: $RESULTS/game.log"
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
	pgrep -f "$DIR" >/dev/null || break
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

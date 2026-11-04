#!/usr/bin/env bash
# unitTAS: runs the in-game tests in a real client (see README.md).
#   ./unittas.sh                     every suite
#   ./unittas.sh commands            one suite (several: commands,combat)
#   ./unittas.sh commands Give       only the tests whose Class.method name contains "Give"
#   UNITTAS_TASK=runClient17 ./unittas.sh    another Gradle run task
#   ./unittas.sh oldsaves [dev]      vanilla 1.7.10's worlds through the release jar (./unittas-oldsaves.sh)
#   ./unittas.sh @<folder> "<suites> [filter]"    another project's game (a folder relative to here, or absolute):
#                                    its runClient and run/client; the results, the helpers and the Gradle cache stay
#                                    here. The watcher passes a request line "@<folder> <suites> [filter]" so.
# Results: unittas-results/<time>/ (report.txt, screenshots/, gradle.log); unittas-results/latest points there.
# A game that goes quiet (no new line in progress.txt for UNITTAS_STALL_SECONDS, 600 unless set) is taken to be
# stuck: its threads go into the results (hang-*.txt) and it is stopped. So is a game that doesn't quit within a
# minute of writing its report.
# Watching (README.md, "Hangs, and watching a run"): every UNITTAS_PICTURE_SECONDS (10) the run saves the window as
# screenshots/watch-live.png and what it is doing as watch.txt. With UNITTAS_WATCHED=1 (the watcher sets it) the run
# raises alarms (alarm.txt) where it would otherwise go by a fixed limit, and waits UNITTAS_DECIDE_SECONDS (300) for
# the answer in decision.txt; the quiet-game limit above then counts watch.txt too, so only a game whose watch has
# stopped as well is stopped from here.
set -u
cd "$(dirname "$0")" || exit 1
ROOT=$(pwd)
# one Gradle cache for this project, whoever runs Gradle (the watcher outside a session's sandbox, the session inside
# it): Minecraft is downloaded and remapped once; UNITTAS_GRADLE_HOME names another
export GRADLE_USER_HOME="${UNITTAS_GRADLE_HOME:-$ROOT/.gradle-home}"
# the project whose game runs: this one, or the one "@<folder>" names
PROJECT=$ROOT
case "${1:-}" in
	@*)
		PROJECT=$(cd "$ROOT" && cd "${1#@}" 2>/dev/null && pwd) || { echo "unitTAS: no project folder '${1#@}'"; exit 1; }
		read -r SUITES FILTER <<< "${2:-}"
		;;
	*)
		SUITES=${1:-}
		FILTER=${2:-}
		;;
esac
# the old saves have their own script (it calls back here for the dev client, with the save list in UNITTAS_EXTRA)
if [ "$SUITES" = "oldsaves" ] && [ -z "${UNITTAS_EXTRA:-}" ]; then
	exec ./unittas-oldsaves.sh ${FILTER:+"$FILTER"}
fi
TASK=${UNITTAS_TASK:-runClient}
STAMP=${UNITTAS_STAMP:-$(date +%Y-%m-%d_%H-%M-%S)}
RESULTS="$ROOT/unittas-results/$STAMP"
REQUEST_DIR="$PROJECT/run/client/unittas"
REQUEST="$REQUEST_DIR/request.properties"
STALL=${UNITTAS_STALL_SECONDS:-600}
QUIT_SECONDS=60

mkdir -p "$RESULTS" "$REQUEST_DIR"
ln -sfn "$STAMP" "$ROOT/unittas-results/latest"
{
	echo "suites=$SUITES"
	echo "filter=$FILTER"
	echo "results=$RESULTS"
	[ "${UNITTAS_WATCHED:-0}" = 1 ] && echo "watched=true"
	echo "watch.pictures=${UNITTAS_PICTURE_SECONDS:-10}"
	echo "watch.decide=${UNITTAS_DECIDE_SECONDS:-300}"
	[ -n "${UNITTAS_EXTRA:-}" ] && printf '%s\n' "$UNITTAS_EXTRA"
} > "$REQUEST"
# the game uses the request up when it starts; this is for a run that never got that far
trap 'rm -f "$REQUEST"' EXIT

START=$(date +%s)
clock() {
	local elapsed=$(( $(date +%s) - START ))
	printf '%02d:%02d' $((elapsed / 60)) $((elapsed % 60))
}

# The game's JVM, found by its working directory (the Gradle daemon runs in the project root and is left alone).
game_jvms() {
	local pid cwd
	for pid in $(pgrep -x java 2>/dev/null); do
		cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null) || continue
		[ "$cwd" = "$PROJECT/run/client" ] && echo "$pid"
	done
}

# Asks the game to quit (SIGTERM), then makes it (SIGKILL) after 15 s; Gradle's run task ends with it.
stop_game() {
	printf '\r\033[K[%s] %s: stopping the game\n' "$(clock)" "$1"
	local jvms _
	jvms=$(game_jvms)
	[ -n "$jvms" ] || return 0
	# shellcheck disable=SC2086
	kill -TERM $jvms 2>/dev/null
	for _ in $(seq 1 30); do
		sleep 0.5
		jvms=$(game_jvms)
		[ -z "$jvms" ] && return 0
	done
	# shellcheck disable=SC2086
	kill -KILL $jvms 2>/dev/null
}

# Never beside a game already open in run/client (your own runClient, say): both would use its options.txt, its saves
# and the request. The report says why, for a session that only reads that.
open_games=$(game_jvms | tr '\n' ' ')
if [ -n "$open_games" ]; then
	{
		echo "unitTAS report: not run. A game is already open in run/client (java pid ${open_games% }); close it, then ask again."
		echo
		echo "Ran 0 tests"
		echo
		echo "FAILED (not run: a game is already open)"
	} > "$RESULTS/report.txt"
	echo "unitTAS: not run: a game is already open in run/client (pid ${open_games% }). Close it first."
	exit 1
fi

echo "unitTAS: suites ${SUITES:-all}${FILTER:+, only '$FILTER'}$([ "$PROJECT" != "$ROOT" ] && echo " in $PROJECT"); results in unittas-results/$STAMP"
# the game's window (unittas-display.sh): by default in gamescope's own window, which never takes focus; only a game
# straight on the desktop (UNITTAS_DISPLAY=plain) gets the desktop script that moves it to desktop 2
if [ "${UNITTAS_DISPLAY:-nested}" = plain ]; then
	./unittas-desktop.sh | tee "$RESULTS/desktop.txt"
else
	echo "test window: in gamescope (UNITTAS_DISPLAY=${UNITTAS_DISPLAY:-nested}), never focused" | tee "$RESULTS/desktop.txt"
fi
(cd "$PROJECT" && exec "$ROOT/unittas-display.sh" ./gradlew --console=plain "$TASK") > "$RESULTS/gradle.log" 2>&1 &
GRADLE=$!

SPIN='|/-\'
spin=0
shown=0
last_line=$(date +%s)
reported=""
stalled=""
show_new_progress() {
	[ -f "$RESULTS/progress.txt" ] || return
	local total
	total=$(wc -l < "$RESULTS/progress.txt")
	if [ "$total" -gt "$shown" ]; then
		printf '\r\033[K'
		tail -n +$((shown + 1)) "$RESULTS/progress.txt" | head -n $((total - shown)) | while IFS= read -r line; do
			printf '[%s] %s\n' "$(clock)" "$line"
		done
		shown=$total
		last_line=$(date +%s)
	fi
}

while kill -0 "$GRADLE" 2>/dev/null; do
	show_new_progress
	now=$(date +%s)
	# a watched run's watch writes watch.txt every few seconds while it can: the game's judge is the watcher
	if [ "${UNITTAS_WATCHED:-0}" = 1 ] && [ -f "$RESULTS/watch.txt" ]; then
		watched_at=$(stat -c %Y "$RESULTS/watch.txt" 2>/dev/null || echo 0)
		[ "$watched_at" -gt "$last_line" ] && last_line=$watched_at
	fi
	if [ -f "$RESULTS/report.txt" ]; then
		[ -n "$reported" ] || reported=$now
		if [ $((now - reported)) -gt "$QUIT_SECONDS" ]; then
			stop_game "the game didn't quit within $QUIT_SECONDS s of its report"
			reported=$now
		fi
	elif [ -f "$RESULTS/progress.txt" ] && [ $((now - last_line)) -gt "$STALL" ]; then
		printf '\r\033[K[%s] nothing new from the game in %s s: its threads go into the results\n' "$(clock)" "$STALL"
		UNITTAS_PROJECT="$PROJECT" ./hang-dump.sh "$RESULTS" | sed 's/^/    /'
		stop_game "the game is stuck"
		stalled=1
		last_line=$now
	fi
	if [ -f "$RESULTS/progress.txt" ]; then
		status="game running"
	else
		status=$(grep -E '^> Task ' "$RESULTS/gradle.log" 2>/dev/null | tail -n 1)
		status=${status:-starting Gradle}
	fi
	printf '\r\033[K[%s] %s %s' "$(clock)" "${SPIN:$((spin++ % 4)):1}" "$status"
	sleep 0.5
done
wait "$GRADLE"
CODE=$?
show_new_progress
printf '\r\033[K'

if [ ! -f "$RESULTS/report.txt" ]; then
	if [ -n "$stalled" ]; then
		why="the game went quiet for $STALL s and was stopped (its threads: hang-*.txt here)"
	else
		why="the game ended before the tests finished (Gradle exit $CODE; a build that failed says so in gradle.log)"
	fi
	# a report anyway, for a session that reads only this folder
	{
		echo "unitTAS report: no report from the game: $why."
		echo
		echo "The end of gradle.log:"
		tail -n 25 "$RESULTS/gradle.log" | sed 's/^/    /'
		echo
		echo "Ran 0 tests"
		echo
		echo "FAILED (no report from the game)"
	} > "$RESULTS/report.txt"
	echo "No report: $why. The end of gradle.log:"
	tail -n 25 "$RESULTS/gradle.log"
	exit 1
fi
echo
# the report without its "ok" lines; the whole one is in the file
grep -v ' \.\.\. ok (' "$RESULTS/report.txt"
echo
echo "Full report: unittas-results/latest/report.txt  (took $(clock))"
tail -n 1 "$RESULTS/report.txt" | grep -q '^OK' && exit 0 || exit 1

#!/usr/bin/env bash
# unitTAS watcher: runs the test runs Claude asks for, here in your own session (your display, your Gradle).
# Start it once in a terminal:  ./unittas-watch.sh      Stop it with Ctrl+C.
# Claude asks for a run by writing unittas-queue/request: one line, "<suites> [filter]", as ./unittas.sh takes them.
# As the run starts, unittas-queue/run holds its results folder; when it ends, unittas-queue/done holds its exit
# code. The runs are watched (UNITTAS_WATCHED=1): where one would go by a fixed limit, it raises an alarm in its
# results folder (alarm.txt, with pictures) and waits for Claude's answer there (decision.txt); see README.md,
# "Hangs, and watching a run".
# Notifications: each line appended to unittas-queue/notify is handed to ./request_task.sh (yours) as "$1", also
# mid-run. Claude writes there itself, and Claude Code's "waiting for you" alerts do too (the Notification hook in
# .claude/settings.local.json). Claude's own sandbox can't reach your desktop; this script runs outside it.
set -u
cd "$(dirname "$0")" || exit 1
QUEUE=unittas-queue
mkdir -p "$QUEUE"
notifier() {
	while true; do
		if [ -s "$QUEUE/notify" ] && mv "$QUEUE/notify" "$QUEUE/notify.sending" 2>/dev/null; then
			sleep 0.2
			while IFS= read -r line; do
				[ -n "$line" ] || continue
				echo "[$(date +%H:%M:%S)] Claude says: $line"
				if [ -x ./request_task.sh ]; then
					./request_task.sh "$line" </dev/null || echo "request_task.sh exited $? for that"
				else
					echo "(no executable ./request_task.sh, so only shown here)"
				fi
			done < "$QUEUE/notify.sending"
			rm -f "$QUEUE/notify.sending"
		fi
		sleep 2
	done
}
notifier &
NOTIFIER=$!
trap 'kill "$NOTIFIER" 2>/dev/null' EXIT
trap 'exit 130' INT TERM
echo "unitTAS watcher: waiting for requests in $QUEUE/, notifications from $QUEUE/notify (Ctrl+C to stop)"
while true; do
	if [ -f "$QUEUE/request" ]; then
		read -r SUITES FILTER < "$QUEUE/request"
		rm -f "$QUEUE/request" "$QUEUE/done" "$QUEUE/run"
		echo "[$(date +%H:%M:%S)] Claude asked for: ${SUITES:-every suite}${FILTER:+, only '$FILTER'}"
		# the run's folder, named here so Claude knows where its alarms will be before the game starts
		STAMP=$(date +%Y-%m-%d_%H-%M-%S)
		echo "$PWD/unittas-results/$STAMP" > "$QUEUE/run.tmp" && mv "$QUEUE/run.tmp" "$QUEUE/run"
		UNITTAS_WATCHED=1 UNITTAS_STAMP="$STAMP" ./unittas.sh "${SUITES:-}" "${FILTER:-}"
		code=$?
		echo "$code" > "$QUEUE/done.tmp" && mv "$QUEUE/done.tmp" "$QUEUE/done"
		echo "[$(date +%H:%M:%S)] finished (exit $code); waiting for the next request"
	fi
	sleep 2
done

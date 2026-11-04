#!/usr/bin/env bash
# Multiplayer check by hand: a dedicated server plus two clients on this computer.
#
# Starts ./gradlew runServer, waits until the server is up, then ./gradlew runClient as the gradle.properties user
# (developmentEnvironmentUserName) and, once that client has loaded, a second ./gradlew runClient with another name.
# Both players are made operators before the server starts, whatever ops.json already held. Join both with
# Multiplayer -> Direct Connect -> localhost. Ctrl+C here stops all three.
# The client windows are titled "client 1 - <name>" and "client 2 - <name>" (renamed with xprop once each window is
# up), so they can be told apart in KDE window rules.
#
# Usage:  ./multiplayer-test.sh [second player name]      (default: SB737)
# Output of each run goes to mp-logs/ next to this script.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS="$ROOT/mp-logs"
SERVER_DIR="$ROOT/run/server"
NAME1=$(sed -n 's/^developmentEnvironmentUserName *= *//p' "$ROOT/gradle.properties" | tr -d '[:space:]')
NAME1=${NAME1:-Developer}
NAME2="${1:-SB737}"
START=$(date +%s)
PIDS=()

elapsed() {
    local s=$(( $(date +%s) - START ))
    printf '%d:%02d' $((s / 60)) $((s % 60))
}

step() {
    printf '\n[%s/5] %s  (%s)\n' "$1" "$2" "$(elapsed)"
}

# The game JVMs are children of the Gradle daemon, not of this script, so Ctrl+C never reaches them and cancelling
# the wrappers does not always end them. They are found by their working directory (run/client, run/server).
game_jvms() {
    local pid cwd
    for pid in $(pgrep -x java 2>/dev/null); do
        cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null) || continue
        [[ $cwd == "$ROOT/run/client" || $cwd == "$ROOT/run/server" ]] && echo "$pid"
    done
}

stop_all() {
    trap '' INT TERM
    printf '\n\nStopping everything...\n'
    for pid in "${PIDS[@]}"; do
        kill -INT "$pid" 2>/dev/null
    done
    local jvms i
    jvms=$(game_jvms)
    if [[ -n $jvms ]]; then
        printf '      asking %s game JVM(s) to quit (SIGTERM, they save and stop)' "$(wc -w <<< "$jvms")"
        kill -TERM $jvms 2>/dev/null
        for i in $(seq 1 30); do
            sleep 0.5
            printf '.'
            jvms=$(game_jvms)
            [[ -z $jvms ]] && break
        done
        echo
        if [[ -n $jvms ]]; then
            echo "      still running after 15 s, killing: $jvms"
            kill -KILL $jvms 2>/dev/null
            sleep 1
        fi
        echo "      ✓ game JVMs gone"
    fi
    wait 2>/dev/null
    printf 'Stopped after %s.\n' "$(elapsed)"
    exit 0
}
trap stop_all INT TERM

# Waits until a log file contains the text, with a spinner. Gives up if the process ends or after the timeout.
wait_for() {
    local pid=$1 file=$2 text=$3 label=$4 timeout=$5
    local spin='|/-\' i=0 waited=0
    while ! grep -q "$text" "$file" 2>/dev/null; do
        if ! kill -0 "$pid" 2>/dev/null; then
            printf '\r      %s: the process ended. Last lines of %s:\n' "$label" "$file"
            tail -n 20 "$file"
            stop_all
        fi
        if (( waited >= timeout )); then
            printf '\r      %s: no "%s" after %ds, carrying on anyway.\n' "$label" "$text" "$timeout"
            return
        fi
        printf '\r      %s %s  %s ' "${spin:i++%4:1}" "$label" "$(elapsed)"
        sleep 1
        waited=$((waited + 1))
    done
    printf '\r      ✓ %s  %s      \n' "$label" "$(elapsed)"
}

# Retitles the client window that just came up: the one still called "Minecraft 1.7.10" (client 1 is renamed before
# client 2 starts). Needs xprop; F11 recreates the window with the vanilla title again.
name_window() {
    local title=$1 wid="" i
    if ! command -v xprop >/dev/null 2>&1; then
        echo "      (xprop not installed: the window keeps its vanilla title)"
        return
    fi
    for i in $(seq 1 20); do
        for wid in $(xprop -root _NET_CLIENT_LIST 2>/dev/null | grep -o '0x[0-9a-f]*'); do
            xprop -id "$wid" _NET_WM_NAME 2>/dev/null | grep -q '= "Minecraft 1.7.10"$' && break 2
            wid=""
        done
        sleep 1
    done
    if [[ -z $wid ]]; then
        echo "      ! no \"Minecraft 1.7.10\" window found, leaving the title alone"
        return
    fi
    if xprop -id "$wid" -f _NET_WM_NAME 8u -set _NET_WM_NAME "$title" && xprop -id "$wid" -f WM_NAME 8s -set WM_NAME "$title"; then
        echo "      ✓ window $wid is now \"$title\""
    else
        echo "      ! xprop could not rename window $wid"
    fi
}

cat <<EOF
Multiplayer test: dedicated server + "$NAME1" + "$NAME2"
This runs three Minecraft JVMs at once (several GB of RAM). Close other heavy programs first.
EOF
read -r -p "Continue? [y/N] " answer
[[ "$answer" =~ ^[Yy]$ ]] || exit 0

step 1 "Preparing the server folder ($SERVER_DIR)"
mkdir -p "$SERVER_DIR" "$LOGS"
if ! grep -q '^eula=true' "$SERVER_DIR/eula.txt" 2>/dev/null; then
    echo "      The server needs the Minecraft EULA accepted: https://aka.ms/MinecraftEULA"
    read -r -p "      Accept it for this test server? [y/N] " answer
    [[ "$answer" =~ ^[Yy]$ ]] || { echo "      Not accepted, stopping."; exit 0; }
    echo "eula=true" > "$SERVER_DIR/eula.txt"
fi
# Dev clients aren't logged in to Mojang, so the server must not check accounts.
if [[ -f "$SERVER_DIR/server.properties" ]]; then
    sed -i 's/^online-mode=.*/online-mode=false/' "$SERVER_DIR/server.properties"
    grep -q '^online-mode=' "$SERVER_DIR/server.properties" || echo "online-mode=false" >> "$SERVER_DIR/server.properties"
else
    echo "online-mode=false" > "$SERVER_DIR/server.properties"
fi
# Both players are operators (/gamemode, /give, /tp work): ops.json is rewritten with the two names, keeping any
# others it holds. The server reads it at startup. Offline servers use name-based UUIDs.
python3 - "$SERVER_DIR/ops.json" "$NAME1" "$NAME2" <<'PY'
import hashlib, json, sys, uuid
def offline_uuid(name):
    digest = bytearray(hashlib.md5(("OfflinePlayer:" + name).encode()).digest())
    digest[6] = digest[6] & 0x0f | 0x30
    digest[8] = digest[8] & 0x3f | 0x80
    return str(uuid.UUID(bytes=bytes(digest)))
path, names = sys.argv[1], sys.argv[2:]
try:
    with open(path) as f:
        ops = [o for o in json.load(f) if isinstance(o, dict) and o.get("name") not in names]
except (OSError, ValueError):
    ops = []
ops += [{"uuid": offline_uuid(n), "name": n, "level": 4} for n in names]
with open(path, "w") as f:
    json.dump(ops, f, indent=2)
PY
echo "      ✓ eula.txt, online-mode=false, ops.json ($NAME1 and $NAME2 are operators)"

step 2 "Starting the server (builds first if needed)"
(cd "$ROOT" && exec ./gradlew runServer) > "$LOGS/server.log" 2>&1 &
PIDS+=($!)
wait_for "${PIDS[0]}" "$LOGS/server.log" 'Done (' "server" 900
if [[ ! -f "$SERVER_DIR/server.properties" ]] || ! grep -q '^online-mode=false' "$SERVER_DIR/server.properties"; then
    echo "      ! The server didn't use $SERVER_DIR: set online-mode=false in its server.properties and restart."
fi

step 3 "Starting client 1 ($NAME1)"
(cd "$ROOT" && exec ./gradlew runClient) > "$LOGS/client-$NAME1.log" 2>&1 &
PIDS+=($!)
wait_for "${PIDS[1]}" "$LOGS/client-$NAME1.log" 'Sound engine started' "client $NAME1" 600
name_window "client 1 - $NAME1"

step 4 "Starting client 2 ($NAME2)"
(cd "$ROOT" && exec ./gradlew runClient --username="$NAME2") > "$LOGS/client-$NAME2.log" 2>&1 &
PIDS+=($!)
wait_for "${PIDS[2]}" "$LOGS/client-$NAME2.log" 'Sound engine started' "client $NAME2" 600
name_window "client 2 - $NAME2"

step 5 "All running"
cat <<EOF
      In each client: Multiplayer -> Direct Connect -> localhost
      Both players are operators (/gamemode, /give, /tp work).
      Logs: $LOGS
      Press Ctrl+C here to stop all three.
EOF
wait
printf '\nAll processes ended after %s.\n' "$(elapsed)"

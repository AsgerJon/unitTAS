#!/usr/bin/env bash
# Thread dumps of every running Minecraft dev JVM (runClient / runServer), for a game stuck at "Loading world" or
# anywhere else. Run it from another terminal while the game hangs (./unittas.sh runs it itself when a run goes
# quiet). Writes hang-<pid>-<time>.txt into the project root, or into the folder given, and says what it did. Uses the
# JDK the JVM itself runs on, so jstack matches the JVM version.
#   ./hang-dump.sh [folder]
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${1:-$ROOT}"
# the project whose game it is: this one, or the one ./unittas.sh runs (it sets UNITTAS_PROJECT)
PROJECT="${UNITTAS_PROJECT:-$ROOT}"
mkdir -p "$OUT_DIR"
STAMP=$(date +%H%M%S)

# The game JVMs are found by their working directory (run/client, run/server), which is how the test script finds
# them too; the Gradle daemon runs in the project root and is left alone.
PIDS=()
for pid in $(pgrep -x java 2>/dev/null); do
    cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null) || continue
    [[ $cwd == "$PROJECT/run/client" || $cwd == "$PROJECT/run/server" ]] && PIDS+=("$pid")
done
if [[ ${#PIDS[@]} -eq 0 ]]; then
    echo "No Minecraft dev JVM found. Java processes right now:"
    pgrep -af java | cut -c1-160 || true
    echo "If one of those is the game, run: jstack -l <pid> > hang-<pid>.txt"
    exit 1
fi

n=0
for pid in "${PIDS[@]}"; do
    n=$((n + 1))
    cmd="$(basename "$(readlink -f "/proc/$pid/cwd")"): $(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | cut -c1-100)"
    out="$OUT_DIR/hang-$pid-$STAMP.txt"
    exe=$(readlink -f "/proc/$pid/exe" 2>/dev/null || true)
    jstack_bin="$(dirname "$exe")/jstack"
    [[ -x $jstack_bin ]] || jstack_bin=$(command -v jstack || true)
    printf '[%d/%d] pid %s: %s\n' "$n" "${#PIDS[@]}" "$pid" "$cmd"
    if [[ -n $jstack_bin ]] && "$jstack_bin" -l "$pid" > "$out" 2>&1; then
        echo "      ✓ thread dump written to $out ($(wc -l < "$out") lines)"
        grep -q 'Found one Java-level deadlock' "$out" && echo "      ! jstack reports a Java-level deadlock, see the end of the file"
    else
        echo "      jstack failed; sending SIGQUIT instead, the dump goes to that JVM's own console or log"
        kill -3 "$pid" && echo "      ✓ SIGQUIT sent; for the multiplayer script look in mp-logs/, for runClient in its terminal"
        rm -f "$out"
    fi
done
echo "Done. Send the hang-*.txt file(s); the interesting threads are \"Client thread\" and \"Server thread\"."

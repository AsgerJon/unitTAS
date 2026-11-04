#!/usr/bin/env bash
# unitTAS: runs a game command (./gradlew runClient, or bin/launch_client.py) on unitTAS's display.
#   UNITTAS_DISPLAY=nested    (the default) inside gamescope, a small Wayland compositor with an Xwayland of its own. The
#                             game is seen in gamescope's window, and that window never takes focus: a Wayland
#                             compositor gives focus only to a window that brings an activation token from something
#                             the user did, and this one is started without any. The game's own X11 focus requests stay
#                             inside gamescope's Xwayland. No desktop's settings or rules are involved.
#   UNITTAS_DISPLAY=headless  inside gamescope with no window at all (the pictures still come from the game itself)
#   UNITTAS_DISPLAY=plain     straight on the desktop, as before gamescope (the window may take focus)
# UNITTAS_WIDTH and UNITTAS_HEIGHT size the game (854 by 480). Without gamescope, or without a Wayland desktop, the
# game goes on the desktop plain, and this says so on stderr. The command replaces this script (exec), so a caller's
# process id is the display's, and the display ends when the game does.
set -u
MODE=${UNITTAS_DISPLAY:-nested}
WIDTH=${UNITTAS_WIDTH:-854}
HEIGHT=${UNITTAS_HEIGHT:-480}
if [ $# -eq 0 ]; then
	echo "Use: ./unittas-display.sh <command> [args]" >&2
	exit 2
fi
case "$MODE" in
	nested|headless) ;;
	plain) exec "$@" ;;
	*) echo "unittas-display: UNITTAS_DISPLAY=$MODE is none of nested, headless or plain" >&2; exit 2 ;;
esac
if ! command -v gamescope >/dev/null; then
	echo "unittas-display: no gamescope, so the game goes straight on the desktop (it may take focus)" >&2
	exec "$@"
fi
BACKEND=headless
if [ "$MODE" = nested ]; then
	if [ -z "${WAYLAND_DISPLAY:-}" ]; then
		echo "unittas-display: not a Wayland desktop, so the game goes straight on it (it may take focus)" >&2
		exec "$@"
	fi
	BACKEND=wayland
fi
# no activation token for gamescope's window: it may be seen, not focused
unset XDG_ACTIVATION_TOKEN DESKTOP_STARTUP_ID
exec gamescope --backend "$BACKEND" -w "$WIDTH" -h "$HEIGHT" -W "$WIDTH" -H "$HEIGHT" -- "$@"

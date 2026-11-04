#!/usr/bin/env bash
# unitTAS: puts the test windows (whose class or title is "unitTAS") on virtual desktop $UNITTAS_DESKTOP (default
# 2). It does this with a small KWin script, loaded over D-Bus, that moves each test window as KWin adds it, before
# the window is drawn. A KWin window rule's desktop setting never took, so a rule only has to handle focus.
# ./unittas.sh and ./unittas-oldsaves.sh run this before each game starts, so a restarted KWin gets the script back. UNITTAS_DESKTOP=0 turns it off. Prints one line saying what it did.
set -u
cd "$(dirname "$0")" || exit 1
DESKTOP=${UNITTAS_DESKTOP:-2}
NAME=unittas-desktop
JS="$(pwd)/unittas-queue/kwin-desktop.js"
QDBUS=$(command -v qdbus6 || command -v qdbus || true)

case $DESKTOP in
	0) echo "test windows: left where KWin puts them (UNITTAS_DESKTOP=0)"; exit 0 ;;
	''|*[!0-9]*) echo "test windows: UNITTAS_DESKTOP=$DESKTOP isn't a desktop number, so left where KWin puts them"; exit 0 ;;
esac
if [ -z "$QDBUS" ]; then
	echo "test windows: no qdbus6 or qdbus, so left where KWin puts them"
	exit 0
fi

mkdir -p "$(dirname "$JS")"
cat > "$JS" <<EOF
// unitTAS (written by unittas-desktop.sh): each test window goes to virtual desktop $DESKTOP as KWin adds it.
var WANT = $DESKTOP;
function isTest(w) {
	if (!w) return false;
	return String(w.resourceClass).toLowerCase() === "unittas"
		|| String(w.resourceName).toLowerCase() === "unittas"
		|| String(w.caption) === "unitTAS";
}
// KWin marks a window that wanted focus and didn't get it (the rule's "Accept focus: No") as wanting attention, and
// Plasma's taskbar shows such a window, in orange, on every desktop. A test window never needs attention.
function quiet(w) {
	if (w.demandsAttention) w.demandsAttention = false;
}
function place(w) {
	if (!isTest(w)) return;
	if (w.demandsAttentionChanged) w.demandsAttentionChanged.connect(function () { quiet(w); });
	quiet(w);
	var ds = workspace.desktops;
	if (typeof ds === "number") {            // KWin 5: a count of desktops, and one desktop number per window
		if (WANT <= ds) w.desktop = WANT;
	} else if (ds && ds.length >= WANT) {    // KWin 6: a list of desktops
		w.desktops = [ds[WANT - 1]];
	}
}
if (workspace.windowAdded) workspace.windowAdded.connect(place);
else workspace.clientAdded.connect(place);
EOF

# drop the copy from the last run (KWin keeps a loaded script until it restarts), then load and start this one
"$QDBUS" org.kde.KWin /Scripting org.kde.kwin.Scripting.unloadScript "$NAME" >/dev/null 2>&1
load() { "$QDBUS" org.kde.KWin /Scripting org.kde.kwin.Scripting.loadScript "$JS" "$NAME" 2>&1; }
ID=$(load)
if [ "$ID" = "-1" ]; then # the old copy goes on KWin's next pass of its event loop
	sleep 0.5
	ID=$(load)
fi
case $ID in
	''|*[!0-9]*) echo "test windows: KWin wouldn't load the script (${ID:-no answer}), so left where KWin puts them"; exit 0 ;;
esac
if "$QDBUS" org.kde.KWin "/Scripting/Script$ID" org.kde.kwin.Script.run >/dev/null 2>&1 \
	|| "$QDBUS" org.kde.KWin /Scripting org.kde.kwin.Scripting.start >/dev/null 2>&1; then
	echo "test windows: go to desktop $DESKTOP (KWin script $NAME)"
else
	echo "test windows: KWin loaded the script but wouldn't start it, so left where KWin puts them"
fi

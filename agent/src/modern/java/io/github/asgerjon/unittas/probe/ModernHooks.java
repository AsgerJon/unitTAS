package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.ChatScreen;
import net.minecraft.client.gui.screens.LevelLoadingScreen;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.client.server.IntegratedServer;

import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.List;

/**
 * The 26.3 client's side of the probe (SPEC.md 12.3, step 3), as 1.7.10's ClientHooks: at the end of each client tick
 * the snapshot is brought up to date and the client side's steps run; the first tick once the game has loaded (the
 * loading overlay gone, a screen up) sends "ready". The integrated server's tick runs the server side's steps. Called
 * from the agent's hooks (ModernEntry), so no loader is needed. In 26.3 the screen and the overlay are Minecraft.gui's,
 * not Minecraft's.
 */
public final class ModernHooks {

	private static volatile boolean readySent;

	private ModernHooks() {
	}

	/** Minecraft is made: the client's own operations get their bodies (declared by ModernPort), the worlds' too. */
	static void register(Probe probe) {
		// the game's state, first in debug.threads (and a hang's dump), as 1.7.10's TasHang.state says it
		probe.gameState = ModernHooks::state;
		// the server the shared bodies act on: the integrated one, while a world is open; the client's own side
		ModernServer.foundBy(() -> Minecraft.getInstance().getSingleplayerServer());
		ModernThings.client = new ModernClientLookup();
		WorldOps.bind(probe);
		ModernThings.bind(probe);
		ModernScreens.bind(probe);
		ModernReset.bind(probe);
		ModernClientReset.bind(probe);
		ModernJoin.bind(probe);
		ModernInput.bind(probe);
		ModernMouse.bind(probe);
		ModernChat.bind(probe);
		ModernSounds.bind(probe);
		ModernPictures.bind(probe);
		ModernPerceive.bind(probe);
		ModernVerbs.bind(probe);
		Version.bindOwn(probe);
		// reflection (PROTOCOL.md 5.9; SPEC.md 19.7 step 4): the core's, by Mojang's names
		Reflect.game = new ModernReflect();
		probe.op("reflect.get").does(Reflect::get);
		probe.op("reflect.set").does(Reflect::set);
		probe.op("screen.get").does(call -> {
			Screen screen = Version.screen();
			if (screen == null) {
				return null;
			}
			return Json.object(
				"class", Members.className(screen.getClass()),
				"chat", screen instanceof ChatScreen,
				"container", screen instanceof AbstractContainerScreen,
				"pauses", screen.isPauseScreen());
		});
	}

	/** Whether the probe is awake: a test run, not an ordinary game the probe's jar happens to be in. */
	public static boolean awake() {
		return Probe.get() != null;
	}

	/**
	 * The window's title while the probe is awake (PROTOCOL.md 2.5), as the 1.7.10 probe's: "unitTAS", kept in the
	 * snapshot for ready and status; null in an ordinary game, whose title stays the game's own.
	 */
	public static String title() {
		Probe probe = Probe.get();
		if (probe == null) {
			return null;
		}
		probe.snapshot.windowTitle = "unitTAS";
		return "unitTAS";
	}

	/** The start of a client tick: the client thread is the one that ticks. */
	public static void clientTickStart() {
		if (Probe.get() != null) {
			Sides.get().noteThread(Side.CLIENT);
		}
	}

	/** The end of a client tick: the snapshot, then "ready" once, then the client side's steps (PROTOCOL.md 4.1). */
	public static void clientTickEnd(Minecraft mc) {
		Probe probe = Probe.get();
		if (probe == null) {
			return;
		}
		if (mc.level != null) {
			ModernTrace.once("the client has its level");
		}
		if (mc.player != null) {
			ModernTrace.once("the client has its player");
		}
		Sides sides = Sides.get();
		Snapshot snapshot = probe.snapshot;
		IntegratedServer server = mc.getSingleplayerServer();
		boolean stopped = server == null || server.isStopped();
		if (stopped && !snapshot.serverStopped) {
			// its world closed: nothing queued for that server runs on the next one
			sides.forget(Side.SERVER);
		}
		snapshot.serverStopped = stopped;
		snapshot.serverRunning = !stopped && sides.tickedAt(Side.SERVER) > 0;
		Screen screen = Version.screen();
		snapshot.inWorld = inWorld(mc, server, screen);
		// a server joined (SPEC.md 19.7 step 10c): in its world, a disconnected screen's reason, its leaving
		ModernJoin.ticked(probe, mc, screen);
		snapshot.worldFolder = stopped ? null : VersionCommon.worldFolder(server);
		snapshot.dimension = mc.level == null ? null : VersionCommon.id(mc.level.dimension());
		snapshot.menu = screen instanceof TitleScreen;
		snapshot.screen = screen == null ? null : Members.className(screen.getClass());
		snapshot.paused = mc.isPaused();
		snapshot.width = mc.getWindow().getWidth();
		snapshot.height = mc.getWindow().getHeight();
		// whether the window holds the pointer (SDL3's relative mouse mode, which the game's grab sets), as 1.7.10's
		// Mouse.isGrabbed(): never, while the probe is awake (PROTOCOL.md 2.5)
		snapshot.pointerGrabbed = Version.pointerGrabbed();
		// loading until the game has loaded (the loading overlay gone, a screen up), as ready says it: 1.21.1's client
		// ticks under its loading overlay, so a tick alone is no sign the game is up
		boolean loaded = readySent || !(Version.loading() || screen == null);
		if (!probe.quitting()) {
			snapshot.state = !loaded ? "loading" : snapshot.changing ? "changing" : mc.level == null ? "menu" : "world";
		}
		if (!readySent) {
			if (!loaded) {
				// still loading (the loading overlay is up): not ready, and no tick counted
				return;
			}
			readySent = true;
			snapshot.player = mc.getUser().getName();
			// the window never has focus: a game that paused for that would stop the tests
			mc.options.pauseOnLostFocus = false;
			snapshot.ready = true;
			// counted first, so ready comes at client tick 1 and the steps of this tick see the game as ready
			sides.ticked(Side.CLIENT);
			probe.event("ready", ready(snapshot));
			return;
		}
		// mouse.rate's turn up to this tick's end, before the steps that answer with the look (ModernMouse)
		ModernMouse.ticked();
		sides.ticked(Side.CLIENT);
	}

	/**
	 * The player is in the world on both sides, past the loading screen: the client's player and level, and the
	 * integrated server's player (read from the client thread as a guess, as 1.7.10's Worlds.inWorld does).
	 */
	private static boolean inWorld(Minecraft mc, IntegratedServer server, Screen screen) {
		return mc.player != null && mc.level != null && server != null
			&& !server.getPlayerList().getPlayers().isEmpty() && !(screen instanceof LevelLoadingScreen);
	}

	/** The client's screen changes (Gui.setScreen): a screen event when asked for (PROTOCOL.md 7). */
	public static void screen(Screen was, Screen to) {
		Probe probe = Probe.get();
		if (probe != null && probe.events.screen) {
			probe.event("screen", Json.object(
				"from", was == null ? null : Members.className(was.getClass()),
				"to", to == null ? null : Members.className(to.getClass())));
		}
	}

	/** The start of the integrated server's tick: its thread. */
	public static void serverTickStart() {
		if (Probe.get() != null) {
			Sides.get().noteThread(Side.SERVER);
			ModernTrace.once("the integrated server's first tick");
		}
	}

	/**
	 * The game's state as debug.threads says it first (on a thread of its own: Ops.threads): the screen, the client's
	 * level and player, the integrated server, and the world's loading so far (ModernTrace).
	 */
	static String state() {
		Minecraft mc = Minecraft.getInstance();
		Screen screen = Version.screen();
		IntegratedServer server = mc.getSingleplayerServer();
		StringBuilder out = new StringBuilder();
		out.append("screen: ").append(screen == null ? "none" : Members.className(screen.getClass())).append('\n');
		out.append("client world: ").append(mc.level != null).append(", client player: ").append(mc.player != null)
			.append('\n');
		out.append("integrated server: ").append(server == null ? "none" : "running " + server.isRunning()
			+ ", players " + server.getPlayerCount()).append('\n');
		out.append("\nthe world's loading so far (debug.trace):\n");
		for (String line : ModernTrace.lines()) {
			out.append(line).append('\n');
		}
		return out.toString();
	}

	/** The end of the integrated server's tick: its steps run (PROTOCOL.md 4.1). */
	public static void serverTickEnd() {
		if (Probe.get() != null) {
			Sides.get().ticked(Side.SERVER);
		}
	}

	private static JsonObject ready(Snapshot snapshot) {
		// the mods the loader beside the probe has (the mod under test's), none in vanilla
		List<Object> mods = new ArrayList<>();
		for (String[] mod : ModernLoaders.mods()) {
			mods.add(Json.object("id", mod[0], "name", mod[1], "version", mod[2]));
		}
		// the game's classes the agent hooks, rewritten as they loaded (each loaded as the probe wakes)
		// by their Mojang names, whatever the game runs under
		List<String> hooked = new ArrayList<>();
		for (String each : ModernEntry.hooked()) {
			hooked.add(Members.mojang(each));
		}
		List<String> rewritten = new ArrayList<>();
		for (String each : ModernEntry.rewritten()) {
			rewritten.add(Members.mojang(each));
		}
		List<String> missing = new ArrayList<>(hooked);
		missing.removeAll(rewritten);
		java.util.Collections.sort(rewritten);
		return Json.object(
			"screen", snapshot.screen,
			"load_ms", System.currentTimeMillis() - ManagementFactory.getRuntimeMXBean().getStartTime(),
			"mods", mods,
			"mixins", Json.object("applied", rewritten, "missing", missing),
			"window", Json.object("title", snapshot.windowTitle, "width", snapshot.width, "height", snapshot.height));
	}
}

package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import net.fabricmc.loader.api.FabricLoader;
import net.fabricmc.loader.api.ModContainer;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.ChatScreen;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.client.server.IntegratedServer;

import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * The 26.3 client's side of the probe (SPEC.md 12.3, step 3), as 1.7.10's ClientHooks: at the end of each client tick
 * the snapshot is brought up to date and the client side's steps run; the first tick once the game has loaded (the
 * loading overlay gone, a screen up) sends "ready". The integrated server's tick runs the server side's steps. Called
 * from the mixins (MixinMinecraft, MixinGui, MixinMinecraftServer), so no Fabric API is needed. In 26.3 the screen
 * and the overlay are Minecraft.gui's, not Minecraft's.
 */
public final class FabricHooks {

	/** The probe's mixins (unittas.mixins.json): each is required, so a game that is up has every one applied. */
	private static final List<String> MIXINS = Arrays.asList("MixinGui", "MixinMinecraft", "MixinMinecraftServer");

	private static volatile boolean readySent;

	private FabricHooks() {
	}

	/** Minecraft is made: the client's own operations get their bodies (declared by FabricPort). */
	static void register(Probe probe) {
		probe.op("screen.get").does(call -> {
			Screen screen = Minecraft.getInstance().gui.screen();
			if (screen == null) {
				return null;
			}
			return Json.object(
				"class", screen.getClass().getName(),
				"chat", screen instanceof ChatScreen,
				"container", screen instanceof AbstractContainerScreen,
				"pauses", screen.isPauseScreen());
		});
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
		snapshot.inWorld = mc.level != null;
		Screen screen = mc.gui.screen();
		snapshot.menu = screen instanceof TitleScreen;
		snapshot.screen = screen == null ? null : screen.getClass().getName();
		snapshot.paused = mc.isPaused();
		snapshot.width = mc.getWindow().getWidth();
		snapshot.height = mc.getWindow().getHeight();
		if (!probe.quitting()) {
			snapshot.state = snapshot.changing ? "changing" : mc.level == null ? "menu" : "world";
		}
		if (!readySent) {
			if (mc.gui.overlay() != null || screen == null) {
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
		sides.ticked(Side.CLIENT);
	}

	/** The client's screen changes (Gui.setScreen): a screen event when asked for (PROTOCOL.md 7). */
	public static void screen(Screen was, Screen to) {
		Probe probe = Probe.get();
		if (probe != null && probe.events.screen) {
			probe.event("screen", Json.object(
				"from", was == null ? null : was.getClass().getName(),
				"to", to == null ? null : to.getClass().getName()));
		}
	}

	/** The start of the integrated server's tick: its thread. */
	public static void serverTickStart() {
		if (Probe.get() != null) {
			Sides.get().noteThread(Side.SERVER);
		}
	}

	/** The end of the integrated server's tick: its steps run (PROTOCOL.md 4.1). */
	public static void serverTickEnd() {
		if (Probe.get() != null) {
			Sides.get().ticked(Side.SERVER);
		}
	}

	private static JsonObject ready(Snapshot snapshot) {
		List<Object> mods = new ArrayList<>();
		for (ModContainer mod : FabricLoader.getInstance().getAllMods()) {
			mods.add(Json.object("id", mod.getMetadata().getId(), "name", mod.getMetadata().getName(), "version",
				mod.getMetadata().getVersion().getFriendlyString()));
		}
		return Json.object(
			"screen", snapshot.screen,
			"load_ms", System.currentTimeMillis() - ManagementFactory.getRuntimeMXBean().getStartTime(),
			"mods", mods,
			"mixins", Json.object("applied", MIXINS, "missing", new ArrayList<String>()),
			"window", Json.object("title", snapshot.windowTitle, "width", snapshot.width, "height", snapshot.height));
	}
}

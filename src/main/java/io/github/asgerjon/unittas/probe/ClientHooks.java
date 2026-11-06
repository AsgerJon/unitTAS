package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonObject;
import cpw.mods.fml.common.FMLCommonHandler;
import cpw.mods.fml.common.Loader;
import cpw.mods.fml.common.ModContainer;
import cpw.mods.fml.common.discovery.ASMDataTable;
import cpw.mods.fml.common.eventhandler.SubscribeEvent;
import cpw.mods.fml.common.gameevent.TickEvent;
import io.github.asgerjon.unittas.TasPlugins;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.server.MinecraftServer;
import net.minecraft.util.IChatComponent;
import net.minecraft.client.gui.GuiScreen;
import net.minecraftforge.client.event.ClientChatReceivedEvent;
import net.minecraftforge.client.event.GuiOpenEvent;
import net.minecraftforge.common.MinecraftForge;
import org.lwjgl.input.Mouse;
import org.lwjgl.opengl.Display;

import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

/**
 * The probe's side in the game's client: its tick, from the mod's preInit on. At the start of each tick the real input
 * goes; at its end the snapshot is brought up to date, the first one sends "ready", and a quit asked for is carried out
 * the game's own way.
 */
public final class ClientHooks {

	/** unitTAS's own mixins and the classes each changes: every member a mixin adds is named unittas$... */
	private static final String[][] MIXINS = {
		{"MixinHandshakeTrace", "net.minecraft.client.network.NetHandlerHandshakeMemory", "net.minecraft.server.network.NetHandlerHandshakeTCP"},
		{"MixinLoginClientTrace", "net.minecraft.client.network.NetHandlerLoginClient"},
		{"MixinLoginServerTrace", "net.minecraft.server.network.NetHandlerLoginServer"},
		{"MixinMinecraft", "net.minecraft.client.Minecraft"},
		{"MixinMouseHelper", "net.minecraft.util.MouseHelper"},
		{"MixinNetworkManagerTrace", "net.minecraft.network.NetworkManager"},
		{"MixinNetworkSystemTrace", "net.minecraft.network.NetworkSystem"},
		{"MixinPlayClientTrace", "net.minecraft.client.network.NetHandlerPlayClient"},
		{"MixinSoundHandler", "net.minecraft.client.audio.SoundHandler"},
	};

	private final Probe probe;
	private boolean readySent;
	private volatile boolean quitAsked;

	private ClientHooks(Probe probe) {
		this.probe = probe;
	}

	/** From the mod's preInit, on the client, when the probe is awake; the table finds the mods' hooks. */
	public static void register(Probe probe, ASMDataTable table) {
		// Minecraft's constructor started the link already, unless MixinMinecraft didn't apply
		Probe.launched("preInit");
		ClientHooks hooks = new ClientHooks(probe);
		TasPlugins.find(table);
		// java.run's suites, as a request.properties run finds them
		io.github.asgerjon.unittas.TasSuites.find(table);
		ClientOps.bind(probe);
		JavaOps.bind(probe);
		probe.gameState = () -> io.github.asgerjon.unittas.TasHang.state(Minecraft.getMinecraft());
		WorldOps.bind(probe);
		GameOps.bind(probe);
		ResetOps.bind(probe);
		ThingOps.bind(probe);
		JoinOps.bind(probe);
		// reflection's side-specific parts: the client's player (or the named one on its server) and its Minecraft
		Reflect.players = GameOps::player;
		Reflect.clientGame = Minecraft::getMinecraft;
		io.github.asgerjon.unittas.UnitTasMode.soundListener = (id, known, from, volume, pitch, x, y, z) -> {
			if (probe.events.sound) {
				probe.event("sound", Json.object("id", id, "known", known, "from", from, "volume", (double) volume,
					"pitch", (double) pitch, "pos", java.util.Arrays.asList(x, y, z)));
			}
		};
		FMLCommonHandler.instance().bus().register(hooks);
		// the chat comes on Forge's own bus
		MinecraftForge.EVENT_BUS.register(hooks);
		probe.leaveBy(hooks::leave);
	}

	/**
	 * Quits the game the way it quits itself, from any thread. Once the client ticks: on its thread, at its next tick,
	 * the world left first. While it still loads: the game loop is told not to start, and the game exits as loading
	 * ends (Minecraft's own exit, which FML's security manager allows).
	 */
	private void leave() {
		if (probe.snapshot.ready) {
			quitAsked = true;
		} else {
			Minecraft.getMinecraft().shutdown();
		}
	}

	@SubscribeEvent
	public void onClientTick(TickEvent.ClientTickEvent event) {
		Minecraft mc = Minecraft.getMinecraft();
		Sides sides = Sides.get();
		if (event.phase == TickEvent.Phase.START) {
			sides.noteThread(Side.CLIENT);
			Window.ignoreRealInput(mc);
			return;
		}
		Snapshot snapshot = probe.snapshot;
		MinecraftServer server = MinecraftServer.getServer();
		boolean stopped = server == null || server.isServerStopped();
		if (stopped && !snapshot.serverStopped) {
			// its world closed: nothing queued for that server runs on the next one
			sides.forget(Side.SERVER);
		}
		snapshot.serverStopped = stopped;
		// a server side to run on: an integrated server up and ticking (its first tick gives it a thread)
		snapshot.serverRunning = !stopped && sides.tickedAt(Side.SERVER) > 0;
		snapshot.inWorld = Worlds.inWorld(mc);
		snapshot.remote = JoinOps.inRemoteWorld(mc);
		if (mc.currentScreen instanceof net.minecraft.client.gui.GuiDisconnected && snapshot.disconnected == null) {
			snapshot.disconnected = JoinOps.reason((net.minecraft.client.gui.GuiDisconnected) mc.currentScreen);
		}
		if (snapshot.joined != null && mc.theWorld == null) {
			// out of the server it joined: left, kicked, or the server gone (the disconnected screen says which)
			String was = snapshot.joined;
			snapshot.joined = null;
			String[] where = was.split(":", 2);
			probe.event("connection", Json.object("state", "left", "address", where[0], "port", Long.parseLong(where[1]),
				"reason", snapshot.disconnected));
		}
		snapshot.menu = mc.currentScreen instanceof net.minecraft.client.gui.GuiMainMenu;
		snapshot.worldFolder = stopped ? null : server.getFolderName();
		snapshot.dimension = mc.thePlayer == null ? null : Worlds.dimension(mc.thePlayer.dimension);
		snapshot.screen = mc.currentScreen == null ? null : mc.currentScreen.getClass().getName();
		snapshot.paused = mc.isGamePaused();
		snapshot.windowTitle = Display.getTitle();
		snapshot.width = mc.displayWidth;
		snapshot.height = mc.displayHeight;
		snapshot.pointerGrabbed = Mouse.isGrabbed();
		if (!probe.quitting()) {
			snapshot.state = snapshot.changing ? "changing" : mc.theWorld == null ? "menu" : "world";
		}
		if (!readySent) {
			readySent = true;
			snapshot.player = mc.getSession().getUsername();
			// the window never has focus: a game that paused for that would stop the tests
			mc.gameSettings.pauseOnLostFocus = false;
			snapshot.ready = true;
			// counted first, so ready comes at client tick 1 and the steps of this tick see the game as ready
			sides.ticked(Side.CLIENT);
			probe.event("ready", ready(snapshot));
		} else {
			sides.ticked(Side.CLIENT);
		}
		if (quitAsked) {
			quitAsked = false;
			if (mc.theWorld != null) {
				// as the pause menu's Save and Quit, before the title screen's Quit. Its title screen takes the game out of
				// focus: without it, the frame after the world went still turned the player as a focused game does, a player
				// that was gone (a NullPointerException in EntityRenderer: a crash at nearly every quit from a world, found by
				// the crash event, 2026-11-05)
				Worlds.close(mc);
			}
			mc.shutdown();
		}
	}

	/** The client's screen changes: a screen event when asked for (7), the screen it was and the one it becomes. */
	@SubscribeEvent
	public void onScreen(GuiOpenEvent event) {
		if (probe.events.screen) {
			GuiScreen was = Minecraft.getMinecraft().currentScreen;
			probe.event("screen", Json.object(
				"from", was == null ? null : was.getClass().getName(),
				"to", event.gui == null ? null : event.gui.getClass().getName()));
		}
	}

	/** A chat line the client received: kept for command.run, and sent as a chat event when asked for (7). */
	@SubscribeEvent
	public void onChat(ClientChatReceivedEvent event) {
		if (event.message == null) {
			return;
		}
		String plain = event.message.getUnformattedText();
		String formatted = event.message.getFormattedText();
		String json = IChatComponent.Serializer.componentToJson(event.message);
		probe.chat.add(plain, formatted, json);
		if (probe.events.chat) {
			probe.event("chat", Json.object("plain", plain, "formatted", formatted, "json", json));
		}
	}

	/** The integrated server's tick: its steps run at its end (PROTOCOL.md 4.1). */
	@SubscribeEvent
	public void onServerTick(TickEvent.ServerTickEvent event) {
		Sides sides = Sides.get();
		sides.noteThread(Side.SERVER);
		if (event.phase == TickEvent.Phase.END) {
			sides.ticked(Side.SERVER);
		}
	}

	private static JsonObject ready(Snapshot snapshot) {
		List<Object> mods = new ArrayList<>();
		for (ModContainer mod : Loader.instance().getActiveModList()) {
			mods.add(Json.object("id", mod.getModId(), "name", mod.getName(), "version", mod.getVersion()));
		}
		List<String> applied = new ArrayList<>();
		List<String> missing = new ArrayList<>();
		for (String[] mixin : MIXINS) {
			boolean all = true;
			for (int i = 1; i < mixin.length; i++) {
				all &= mixedIn(mixin[i]);
			}
			(all ? applied : missing).add(mixin[0]);
		}
		return Json.object(
			"screen", snapshot.screen,
			"load_ms", System.currentTimeMillis() - ManagementFactory.getRuntimeMXBean().getStartTime(),
			"mods", mods,
			"mixins", Json.object("applied", applied, "missing", missing),
			"window", Json.object("title", snapshot.windowTitle, "width", snapshot.width, "height", snapshot.height));
	}

	/** Whether the class (loaded, not initialised) carries a member one of unitTAS's mixins added. */
	private static boolean mixedIn(String className) {
		try {
			Class<?> target = Class.forName(className, false, Minecraft.class.getClassLoader());
			for (Method method : target.getDeclaredMethods()) {
				if (method.getName().contains("unittas$")) {
					return true;
				}
			}
			for (Field field : target.getDeclaredFields()) {
				if (field.getName().contains("unittas$")) {
					return true;
				}
			}
			return false;
		} catch (ClassNotFoundException | LinkageError e) {
			return false;
		}
	}
}

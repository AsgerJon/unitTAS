package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonObject;
import cpw.mods.fml.common.FMLCommonHandler;
import cpw.mods.fml.common.Loader;
import cpw.mods.fml.common.ModContainer;
import cpw.mods.fml.common.eventhandler.SubscribeEvent;
import cpw.mods.fml.common.gameevent.PlayerEvent;
import cpw.mods.fml.common.gameevent.TickEvent;
import io.github.asgerjon.unittas.probe.link.Json;
import io.netty.channel.ChannelFuture;
import net.minecraft.entity.player.EntityPlayerMP;
import net.minecraft.network.NetworkSystem;
import net.minecraft.server.MinecraftServer;

import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.util.ArrayList;
import java.util.List;

/**
 * The probe's side in a dedicated server (SPEC.md 11.3, step 2; PROTOCOL.md 9.2), from the mod's preInit on: its tick,
 * "ready" at the end of its world's first tick, and the quit as /stop. It names no client class, and nothing it calls
 * does: a dedicated server has none. "ready" says every address the server listens on, as its own network endpoints
 * have it (not as server.properties asked), for the orchestrator to check before any client joins.
 */
public final class ServerHooks {

	/** unitTAS's server mixins and the classes each changes: every member a mixin adds is named unittas$... */
	private static final String[][] MIXINS = {
		{"MixinDedicatedServer", "net.minecraft.server.dedicated.DedicatedServer"},
		{"MixinNetworkSystemDrop", "net.minecraft.network.NetworkSystem"},
	};

	private final Probe probe;
	private boolean readySent;

	private ServerHooks(Probe probe) {
		this.probe = probe;
	}

	/** From the mod's preInit on a dedicated server, when the probe is awake. */
	public static void register(Probe probe) {
		// the server's constructor started the link already, unless MixinDedicatedServer didn't apply
		Probe.launched("preInit");
		ServerOps.bind(probe);
		probe.gameState = ServerHooks::state;
		FMLCommonHandler.instance().bus().register(new ServerHooks(probe));
		probe.leaveBy(ServerHooks::leave);
	}

	/** As /stop: the server saves its world and stops, and the process ends with it. From any thread, loading or not. */
	private static void leave() {
		MinecraftServer server = MinecraftServer.getServer();
		if (server != null) {
			server.initiateShutdown();
		}
	}

	private static String state() {
		MinecraftServer server = MinecraftServer.getServer();
		if (server == null) {
			return "dedicated server: not made yet";
		}
		return "dedicated server: world " + server.getFolderName() + ", running " + server.isServerRunning() + ", players "
			+ server.getCurrentPlayerCount() + "/" + server.getMaxPlayers();
	}

	@SubscribeEvent
	public void onServerTick(TickEvent.ServerTickEvent event) {
		Sides sides = Sides.get();
		if (event.phase == TickEvent.Phase.START) {
			sides.noteThread(Side.SERVER);
			return;
		}
		Snapshot snapshot = probe.snapshot;
		MinecraftServer server = MinecraftServer.getServer();
		snapshot.serverStopped = false;
		snapshot.serverRunning = true;
		snapshot.worldFolder = server.getFolderName();
		if (!probe.quitting()) {
			snapshot.state = "world";
		}
		if (!readySent) {
			readySent = true;
			snapshot.ready = true;
			// counted first, so ready comes at server tick 1 and the steps of this tick see the server as ready
			sides.ticked(Side.SERVER);
			probe.event("ready", ready(server));
		} else {
			sides.ticked(Side.SERVER);
		}
	}

	/** A player in: the player.joined event (PROTOCOL.md 9.4), as the server's log says it joined. */
	@SubscribeEvent
	public void onJoined(PlayerEvent.PlayerLoggedInEvent event) {
		if (event.player instanceof EntityPlayerMP) {
			probe.players.add(event.player.getCommandSenderName());
			probe.event("player.joined", ServerOps.summary((EntityPlayerMP) event.player));
		}
	}

	/** A player gone: left, kicked, or its connection lost. */
	@SubscribeEvent
	public void onLeft(PlayerEvent.PlayerLoggedOutEvent event) {
		if (event.player instanceof EntityPlayerMP) {
			probe.players.remove(event.player.getCommandSenderName());
			probe.event("player.left", ServerOps.summary((EntityPlayerMP) event.player));
		}
	}

	private static JsonObject ready(MinecraftServer server) {
		List<Object> mods = new ArrayList<>();
		for (ModContainer mod : Loader.instance().getActiveModList()) {
			mods.add(Json.object("id", mod.getModId(), "name", mod.getName(), "version", mod.getVersion()));
		}
		List<String> applied = new ArrayList<>();
		List<String> missing = new ArrayList<>();
		for (String[] mixin : MIXINS) {
			(mixedIn(mixin[1]) ? applied : missing).add(mixin[0]);
		}
		List<Object> listening = new ArrayList<>();
		for (InetSocketAddress at : listening(server.getNetworkSystem())) {
			listening.add(Json.object("address", at.getAddress() == null ? at.getHostString() : at.getAddress().getHostAddress(),
				"port", at.getPort()));
		}
		JsonObject first = listening.isEmpty() ? null : (JsonObject) listening.get(0);
		return Json.object(
			"world", server.getFolderName(),
			"address", first == null ? null : first.get("address"),
			"port", first == null ? null : first.get("port"),
			"listening", listening,
			"load_ms", System.currentTimeMillis() - ManagementFactory.getRuntimeMXBean().getStartTime(),
			"mods", mods,
			"mixins", Json.object("applied", applied, "missing", missing));
	}

	/**
	 * Every address the server's network listens on, from its own endpoints: the List of the channels it bound, found
	 * by what it holds rather than by a name (the names differ between a development run and a real one).
	 */
	static List<InetSocketAddress> listening(NetworkSystem network) {
		List<InetSocketAddress> found = new ArrayList<>();
		for (Field field : NetworkSystem.class.getDeclaredFields()) {
			if (!List.class.isAssignableFrom(field.getType())) {
				continue;
			}
			try {
				field.setAccessible(true);
				Object value = field.get(network);
				if (!(value instanceof List)) {
					continue;
				}
				synchronized (value) {
					for (Object each : (List<?>) value) {
						if (each instanceof ChannelFuture) {
							SocketAddress local = ((ChannelFuture) each).channel().localAddress();
							if (local instanceof InetSocketAddress) {
								found.add((InetSocketAddress) local);
							}
						}
					}
				}
			} catch (IllegalAccessException | RuntimeException e) {
				Probe.LOG.warn("unitTAS probe: can't read the server's endpoints from {}: {}", field.getName(), e.toString());
			}
		}
		return found;
	}

	/** Whether the class (loaded, not initialised) carries a member one of unitTAS's mixins added. */
	private static boolean mixedIn(String className) {
		try {
			Class<?> target = Class.forName(className, false, MinecraftServer.class.getClassLoader());
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

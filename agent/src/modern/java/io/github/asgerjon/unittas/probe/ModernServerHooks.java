package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import io.netty.channel.ChannelFuture;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.network.ServerConnectionListener;
import net.minecraft.world.level.storage.LevelResource;

/**
 * The probe's side in a modern dedicated server (SPEC.md 19.7 step 10b), from the agent's server hooks
 * (ModernServerEntry), as 1.7.10's ServerHooks: the server starting (the probe dials, its quit the server's own halt,
 * which saves its world), its tick (the snapshot, the server side's steps), its first tick's ready, which names the
 * world and every address the server listens on, from its own endpoints, and its players coming and going. No client
 * class.
 */
final class ModernServerHooks {

	private static volatile MinecraftServer server;
	private static volatile boolean readySent;
	private static volatile Field channels;

	private ModernServerHooks() {
	}

	/**
	 * The server about to start (before DedicatedServer.initServer): its operations get their bodies (declared by
	 * ModernServerPort), the same as a client's integrated server's, on this server; its quit is the server's; the
	 * probe dials.
	 */
	static void starting(MinecraftServer starting) {
		server = starting;
		Probe probe = Probe.get();
		if (probe != null) {
			ModernServer.foundBy(() -> starting);
			WorldOps.bindServer(probe, VersionCommon.serverWorlds());
			ModernThings.bindDedicated(probe);
			ModernReset.bind(probe);
			// reflection (PROTOCOL.md 5.9), the server's side: a mod's own server-side state
			Reflect.game = new ModernReflect();
			probe.op("reflect.get").does(Reflect::get);
			probe.op("reflect.set").does(Reflect::set);
			// as /stop: the world saved, then the server and the process gone
			probe.leaveBy(() -> starting.halt(false));
		}
		Probe.launched(null);
	}

	static void tickStart() {
		if (Probe.get() != null) {
			Sides.get().noteThread(Side.SERVER);
		}
	}

	/** The end of the server's tick: the snapshot, the ready at the first, the server side's steps. */
	static void tickEnd(MinecraftServer ticking) {
		Probe probe = Probe.get();
		if (probe == null) {
			return;
		}
		Sides sides = Sides.get();
		Snapshot snapshot = probe.snapshot;
		snapshot.serverStopped = false;
		snapshot.serverRunning = true;
		snapshot.worldFolder = folder(ticking);
		if (!probe.quitting()) {
			snapshot.state = "world";
		}
		if (!readySent) {
			readySent = true;
			snapshot.ready = true;
			// counted first, so ready comes at server tick 1 and the steps of this tick see the server as ready
			sides.ticked(Side.SERVER);
			probe.event("ready", ready(ticking));
			return;
		}
		sides.ticked(Side.SERVER);
	}

	/**
	 * A player in, placed in the world (after PlayerList.placeNewPlayer, as the server's log says it joined): the
	 * player.joined event (PROTOCOL.md 9.4), and the status's players, as 1.7.10's ServerHooks has them.
	 */
	static void joined(ServerPlayer player) {
		Probe probe = Probe.get();
		if (probe != null) {
			probe.players.add(player.getName().getString());
			probe.event("player.joined", ModernThings.summary(player));
		}
	}

	/** A player gone (before PlayerList.remove): left, kicked, or its connection lost. */
	static void left(ServerPlayer player) {
		Probe probe = Probe.get();
		if (probe != null) {
			probe.players.remove(player.getName().getString());
			probe.event("player.left", ModernThings.summary(player));
		}
	}

	/** The world's folder's name (level-name), as the server holds it. */
	private static String folder(MinecraftServer of) {
		Path root = of.getWorldPath(LevelResource.ROOT).toAbsolutePath().normalize();
		return root.getFileName() == null ? root.toString() : root.getFileName().toString();
	}

	private static JsonObject ready(MinecraftServer of) {
		List<Object> mods = new ArrayList<>();
		for (String[] mod : ModernLoaders.mods()) {
			mods.add(Json.object("id", mod[0], "name", mod[1], "version", mod[2]));
		}
		List<String> hooked = new ArrayList<>();
		for (String each : ModernServerEntry.hooked()) {
			hooked.add(Members.mojang(each));
		}
		List<String> rewritten = new ArrayList<>();
		for (String each : ModernServerEntry.rewritten()) {
			rewritten.add(Members.mojang(each));
		}
		List<String> missing = new ArrayList<>(hooked);
		missing.removeAll(rewritten);
		java.util.Collections.sort(rewritten);
		List<Object> listening = new ArrayList<>();
		for (InetSocketAddress at : listening(of)) {
			listening.add(Json.object("address", at.getAddress() == null ? at.getHostString()
				: at.getAddress().getHostAddress(), "port", at.getPort()));
		}
		JsonObject first = listening.isEmpty() ? null : (JsonObject) listening.get(0);
		return Json.object(
			"world", folder(of),
			"address", first == null ? null : first.get("address"),
			"port", first == null ? null : first.get("port"),
			"listening", listening,
			"load_ms", System.currentTimeMillis() - ManagementFactory.getRuntimeMXBean().getStartTime(),
			"mods", mods,
			"mixins", Json.object("applied", rewritten, "missing", missing));
	}

	/** Every address the server listens on, from its own endpoints: the channels its connection listener bound. */
	@SuppressWarnings("unchecked")
	static List<InetSocketAddress> listening(MinecraftServer of) {
		List<InetSocketAddress> out = new ArrayList<>();
		ServerConnectionListener listener = of.getConnection();
		if (listener == null) {
			return out;
		}
		Field field = channels;
		if (field == null) {
			field = Members.field(ServerConnectionListener.class, "channels");
			channels = field;
		}
		List<ChannelFuture> bound = Members.get(field, listener);
		synchronized (bound) {
			for (ChannelFuture each : bound) {
				SocketAddress at = each.channel().localAddress();
				if (at instanceof InetSocketAddress address) {
					out.add(address);
				}
			}
		}
		return out;
	}

	/** The server the probe is in, once it is starting. */
	static MinecraftServer server() {
		return server;
	}
}

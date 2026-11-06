package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.TasHooks;
import io.github.asgerjon.unittas.TasPlugins;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.command.ICommandSender;
import net.minecraft.entity.player.EntityPlayerMP;
import net.minecraft.server.MinecraftServer;
import net.minecraft.util.ChunkCoordinates;
import net.minecraft.util.EnumChatFormatting;
import net.minecraft.util.IChatComponent;
import net.minecraft.world.World;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

/**
 * The bodies of a dedicated server's operations (SPEC.md 11.3, step 2), given at its preInit. Each runs on the server
 * thread, and none names a client class: a dedicated server has none.
 */
final class ServerOps {

	private ServerOps() {
	}

	static void bind(Probe probe) {
		probe.op("world.get").does(call -> ServerWorld.describe());
		probe.op("world.prepare").does(call -> {
			ServerWorld.prepare();
			return new JsonObject();
		});
		probe.op("command.run").does(ServerOps::command);
		// players by name (PROTOCOL.md 9.4; SPEC.md 11.3, step 4)
		probe.op("players.list").does(call -> {
			JsonArray list = new JsonArray();
			for (Object each : MinecraftServer.getServer().getConfigurationManager().playerEntityList) {
				list.add(summary((EntityPlayerMP) each));
			}
			return list;
		});
		probe.op("player.get").does(call -> Values.player(player(call.string("player", null))));
		// the reset across games (PROTOCOL.md 9.5; SPEC.md 11.3, step 5), and the mods' own hooks on the server
		probe.op("player.reset").does(ServerOps::resetPlayer);
		probe.op("world.reset").does(call -> {
			ServerReset.world();
			return new JsonObject();
		});
		probe.op("hooks.run").does(ServerOps::hooks);
		// reflection (PROTOCOL.md 5.9), the server's side: a mod's own server-side state
		probe.op("reflect.get").does(Reflect::get);
		probe.op("reflect.set").does(Reflect::set);
		probe.op("player.kick").does(call -> {
			String name = call.string("player", null);
			if (name == null) {
				throw ProbeException.badRequest("player", "player.kick names the player to kick");
			}
			EntityPlayerMP player = player(name);
			player.playerNetServerHandler.kickPlayerFromServer(call.string("reason", "kicked by unitTAS"));
			return new JsonObject();
		});
	}

	/**
	 * player.reset on a dedicated server, the player named (or the only one in): brought back to the overworld first if
	 * it is away, and that is all the call does (it answers respawned; the orchestrator waits on that player's client,
	 * then calls again). Otherwise the player's part, then the mods' resetPlayer unless "hooks": "after".
	 */
	private static JsonElement resetPlayer(Call call) throws ProbeException {
		EntityPlayerMP player = player(call.string("player", null));
		if (ServerReset.respawnIfAway(player)) {
			return Json.object("respawned", true);
		}
		double[] at = {ServerReset.START_X, ServerReset.START_Y, ServerReset.START_Z};
		if (call.has("at")) {
			JsonElement given = call.args.get("at");
			if (!given.isJsonArray() || given.getAsJsonArray().size() != 3) {
				throw ProbeException.badRequest("at", "at is [x, y, z]");
			}
			for (int i = 0; i < 3; i++) {
				at[i] = given.getAsJsonArray().get(i).getAsDouble();
			}
		}
		JsonObject look = call.object("look");
		float yaw = look != null && look.has("yaw") ? look.get("yaw").getAsFloat() : 0.0F;
		float pitch = look != null && look.has("pitch") ? look.get("pitch").getAsFloat() : 0.0F;
		String hooks = call.string("hooks", "now");
		if (!hooks.equals("now") && !hooks.equals("after")) {
			throw ProbeException.badRequest("hooks", "hooks is now or after, not " + hooks);
		}
		ServerReset.player(player, at[0], at[1], at[2], yaw, pitch);
		if (hooks.equals("now")) {
			for (Object[] outcome : TasPlugins.run(each -> each.resetPlayer(player))) {
				Throwable thrown = (Throwable) outcome[1];
				if (thrown != null) {
					throw new ProbeException("GameError", outcome[0] + ".resetPlayer threw " + thrown + ": the player isn't"
						+ " fully reset", Json.object("plugin", outcome[0], "exception", thrown.getClass().getName(),
						"trace", Probe.trace(thrown)));
				}
			}
		}
		return Json.object("respawned", false);
	}

	/**
	 * hooks.run on a dedicated server: its own hooks (setUpWorld, tearDownWorld, resetPlayer for the player named or
	 * every one in). beforeRun and afterRun are the clients' (PROTOCOL.md 9.2). How each plugin went, as a client's.
	 */
	private static JsonElement hooks(Call call) throws ProbeException {
		String hook = call.string("hook", null);
		Consumer<TasHooks> run;
		if ("setUpWorld".equals(hook)) {
			run = TasHooks::setUpWorld;
		} else if ("tearDownWorld".equals(hook)) {
			run = TasHooks::tearDownWorld;
		} else if ("resetPlayer".equals(hook)) {
			List<EntityPlayerMP> players = new ArrayList<>();
			if (call.has("player")) {
				players.add(player(call.string("player", null)));
			} else {
				for (Object each : MinecraftServer.getServer().getConfigurationManager().playerEntityList) {
					players.add((EntityPlayerMP) each);
				}
			}
			run = hooks -> {
				for (EntityPlayerMP player : players) {
					hooks.resetPlayer(player);
				}
			};
		} else if ("beforeRun".equals(hook) || "afterRun".equals(hook)) {
			throw ProbeException.badRequest("hook", hook + " is a client's hook: a dedicated server runs setUpWorld,"
				+ " tearDownWorld and resetPlayer");
		} else {
			throw ProbeException.badRequest("hook", "hook is setUpWorld, tearDownWorld or resetPlayer on a server, not "
				+ hook);
		}
		JsonArray plugins = new JsonArray();
		for (Object[] outcome : TasPlugins.run(run)) {
			Throwable thrown = (Throwable) outcome[1];
			plugins.add(thrown == null ? Json.object("class", outcome[0], "ok", true) : Json.object("class", outcome[0],
				"ok", false, "error", Json.object("message", String.valueOf(thrown), "exception", thrown.getClass().getName(),
					"trace", Probe.trace(thrown))));
		}
		return Json.object("plugins", plugins);
	}

	/** A player in players.list and in its events: name, uuid, entity id, dimension, where it stands. */
	static JsonObject summary(EntityPlayerMP player) {
		List<Double> pos = new ArrayList<>();
		pos.add(player.posX);
		pos.add(player.posY);
		pos.add(player.posZ);
		return Json.object("name", player.getCommandSenderName(), "uuid", player.getUniqueID().toString(), "entity",
			player.getEntityId(), "dimension", ServerWorld.dimension(player.dimension), "pos", pos);
	}

	/**
	 * command.run on a dedicated server. As the console ("server"), its answer is recorded, so its lines come back as a
	 * client's command's do. As a player, its answer goes to that player's client, which is where it is read.
	 */
	private static JsonElement command(Call call) throws ProbeException {
		String text = call.string("command", null);
		if (text == null) {
			throw ProbeException.badRequest("command", "command.run needs the command");
		}
		MinecraftServer server = MinecraftServer.getServer();
		JsonElement as = call.args.get("as");
		ICommandSender sender;
		Console console = null;
		if (as != null && as.isJsonPrimitive() && "server".equals(as.getAsString())) {
			console = new Console(server);
			sender = console;
		} else if (as == null || as.isJsonNull() || (as.isJsonPrimitive() && "player".equals(as.getAsString()))) {
			sender = player(call.string("player", null));
		} else if (as.isJsonObject() && Json.string(as.getAsJsonObject(), "player") != null) {
			sender = player(Json.string(as.getAsJsonObject(), "player"));
		} else {
			throw ProbeException.badRequest("as", "as is \"player\", {\"player\": name} or \"server\", not " + as);
		}
		int result = server.getCommandManager().executeCommand(sender, text);
		JsonArray lines = new JsonArray();
		JsonArray errors = new JsonArray();
		if (console != null) {
			for (IChatComponent line : console.said) {
				lines.add(Json.of(line.getUnformattedText()));
				if (line.getChatStyle().getColor() == EnumChatFormatting.RED) {
					errors.add(Json.of(line.getUnformattedText()));
				}
			}
		}
		return Json.object("result", result, "lines", lines, "errors", errors);
	}

	/**
	 * The player a request names, or the only one in. NotReady with nobody in; BadRequest naming them when several are
	 * in and none is named (PROTOCOL.md 9.4); NotFound for a name that isn't in.
	 */
	static EntityPlayerMP player(String name) throws ProbeException {
		List<?> players = MinecraftServer.getServer().getConfigurationManager().playerEntityList;
		if (players.isEmpty()) {
			throw new ProbeException("NotReady", "no player is in this server", Json.object("players", new JsonArray()));
		}
		List<String> names = new ArrayList<>();
		for (Object each : players) {
			names.add(((EntityPlayerMP) each).getCommandSenderName());
		}
		if (name == null) {
			if (players.size() > 1) {
				throw new ProbeException("BadRequest", "several players are in, so a request names one: " + names,
					Json.object("field", "player", "players", names));
			}
			return (EntityPlayerMP) players.get(0);
		}
		for (Object each : players) {
			if (((EntityPlayerMP) each).getCommandSenderName().equals(name)) {
				return (EntityPlayerMP) each;
			}
		}
		throw new ProbeException("NotFound", "no player " + name + " is in this server (in: " + names + ")",
			Json.object("player", name, "players", names));
	}

	/** The console, as a command sees it, with what it is told kept: the server itself in all else. */
	private static final class Console implements ICommandSender {
		private final MinecraftServer server;
		final List<IChatComponent> said = new ArrayList<>();

		Console(MinecraftServer server) {
			this.server = server;
		}

		@Override
		public String getCommandSenderName() {
			return server.getCommandSenderName();
		}

		@Override
		public IChatComponent getFormattedCommandSenderName() {
			return server.getFormattedCommandSenderName();
		}

		@Override
		public void addChatMessage(IChatComponent message) {
			said.add(message);
			server.addChatMessage(message);
		}

		@Override
		public boolean canCommandSenderUseCommand(int level, String command) {
			return server.canCommandSenderUseCommand(level, command);
		}

		@Override
		public ChunkCoordinates getCommandSenderPosition() {
			return server.getCommandSenderPosition();
		}

		@Override
		public World getEntityWorld() {
			return server.getEntityWorld();
		}
	}
}

package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
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

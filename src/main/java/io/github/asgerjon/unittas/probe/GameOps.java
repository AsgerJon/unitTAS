package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.TasHooks;
import io.github.asgerjon.unittas.TasPlugins;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiChat;
import net.minecraft.client.gui.GuiIngameMenu;
import net.minecraft.client.gui.GuiScreen;
import net.minecraft.client.gui.inventory.GuiContainer;
import net.minecraft.client.gui.inventory.GuiContainerCreative;
import net.minecraft.client.gui.inventory.GuiInventory;
import net.minecraft.command.ICommandSender;
import net.minecraft.entity.Entity;
import net.minecraft.entity.player.EntityPlayer;
import net.minecraft.entity.player.EntityPlayerMP;
import net.minecraft.entity.player.InventoryPlayer;
import net.minecraft.inventory.Container;
import net.minecraft.inventory.Slot;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.Teleporter;
import net.minecraft.world.World;
import net.minecraft.world.WorldServer;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.function.Consumer;

/**
 * The bodies of step 5a's operations (PROTOCOL.md 8.4 to 8.9), given at preInit: command.run, player.get and
 * player.teleport, inventory.get, container.get, entity.list, screen.open and screen.close, hooks.run. Each body runs on
 * the side its request named; what an operation waits for after (chat lines, the client arriving, a tick) is its settle
 * phase, on the probe's thread.
 */
final class GameOps {

	private static final String RED = "§c";
	/** How long the client may take to arrive in another dimension, in its ticks (as the reset allows). */
	private static final int ARRIVE_TICKS = 200;

	private GameOps() {
	}

	static void bind(Probe probe) {
		probe.op("command.run").does(GameOps::command).settles(GameOps::commandLines);
		probe.op("player.get").does(call -> {
			JsonObject value = Values.player(player(call));
			if (call.side == Side.CLIENT) {
				// the client's own: its camera (0 first person, 1 from behind, 2 from the front)
				value.addProperty("camera", Minecraft.getMinecraft().gameSettings.thirdPersonView);
			}
			return value;
		});
		probe.op("player.teleport").does(GameOps::teleport).settles(GameOps::arrive);
		probe.op("inventory.get").does(GameOps::inventory);
		probe.op("container.get").does(GameOps::container);
		probe.op("entity.list").does(GameOps::entities);
		probe.op("screen.open").does(GameOps::openScreen).settles(GameOps::oneTick);
		probe.op("screen.close").does(GameOps::closeScreen).settles(GameOps::oneTick);
		probe.op("hooks.run").does(GameOps::hooks);
	}

	// ---------------------------------------------------------------- players

	/** The side's player: the client's own, or on the server the one named by "player" (the only one when unnamed). */
	static EntityPlayer player(Call call) throws ProbeException {
		if (call.side == Side.CLIENT) {
			EntityPlayer own = Minecraft.getMinecraft().thePlayer;
			if (own == null) {
				throw new ProbeException("NotReady", "the client has no player: no world is open", null);
			}
			return own;
		}
		return serverPlayer(call, call.string("player", null));
	}

	/** A player on the server by name; with no name, the only one (PROTOCOL.md 9.4). */
	static EntityPlayerMP serverPlayer(Call call, String name) throws ProbeException {
		List<?> players = MinecraftServer.getServer().getConfigurationManager().playerEntityList;
		if (name == null) {
			if (players.size() == 1) {
				return (EntityPlayerMP) players.get(0);
			}
			if (players.isEmpty()) {
				throw new ProbeException("NotReady", "no player is in the world", null);
			}
			List<String> names = new ArrayList<>();
			for (Object each : players) {
				names.add(((EntityPlayerMP) each).getCommandSenderName());
			}
			throw ProbeException.badRequest("player", "name the player: " + String.join(", ", names) + " are in");
		}
		for (Object each : players) {
			if (((EntityPlayerMP) each).getCommandSenderName().equals(name)) {
				return (EntityPlayerMP) each;
			}
		}
		throw new ProbeException("NotFound", "no player " + name + " is in the world", Json.object("what", name));
	}

	// ---------------------------------------------------------------- commands

	/** Runs the command as the server runs a typed one, without the chat's 256-character limit (8.6). */
	private static JsonElement command(Call call) throws ProbeException {
		String text = call.string("command", null);
		if (text == null) {
			throw ProbeException.badRequest("command", "command.run needs the command");
		}
		ICommandSender sender;
		JsonElement as = call.args.get("as");
		if (as == null || as.isJsonNull() || (as.isJsonPrimitive() && "player".equals(as.getAsString()))) {
			sender = serverPlayer(call, call.string("player", null));
		} else if (as.isJsonPrimitive() && "server".equals(as.getAsString())) {
			sender = MinecraftServer.getServer();
		} else if (as.isJsonObject() && Json.string(as.getAsJsonObject(), "player") != null) {
			sender = serverPlayer(call, Json.string(as.getAsJsonObject(), "player"));
		} else {
			throw ProbeException.badRequest("as", "as is \"player\", {\"player\": name} or \"server\", not " + as);
		}
		call.mark = call.probe.chat.mark();
		int result = MinecraftServer.getServer().getCommandManager().executeCommand(sender, text);
		return Json.object("result", result, "lines", new JsonArray(), "errors", new JsonArray());
	}

	/** After the command, settle_ticks client ticks for its answer to reach the chat; its lines are those that came. */
	private static JsonElement commandLines(Call call, JsonElement value) throws ProbeException, InterruptedException {
		long ticks = call.number("settle_ticks", 3, 0, 1200);
		waitClient(call, ticks);
		JsonArray lines = new JsonArray();
		JsonArray errors = new JsonArray();
		for (JsonObject line : call.probe.chat.since(call.mark)) {
			lines.add(line.get("plain"));
			if (Json.string(line, "formatted").startsWith(RED)) {
				errors.add(line.get("plain"));
			}
		}
		JsonObject answer = value.getAsJsonObject();
		answer.add("lines", lines);
		answer.add("errors", errors);
		return answer;
	}

	private static void waitClient(Call call, long ticks) throws ProbeException, InterruptedException {
		try {
			Sides.get().waitTicks(Side.CLIENT, ticks, Sides.STALL_SECONDS);
		} catch (Sides.Stalled stalled) {
			throw Ops.stalled(call.probe, stalled);
		}
	}

	// ---------------------------------------------------------------- teleporting

	/** A teleporter that builds and looks for no portal: the player is placed where the operation says, after. */
	private static final class Placed extends Teleporter {
		Placed(WorldServer world) {
			super(world);
		}

		@Override
		public void placeInPortal(Entity entity, double x, double y, double z, float yaw) {
			entity.motionX = entity.motionY = entity.motionZ = 0.0D;
		}

		@Override
		public boolean placeInExistingPortal(Entity entity, double x, double y, double z, float yaw) {
			return true;
		}

		@Override
		public boolean makePortal(Entity entity) {
			return true;
		}

		@Override
		public void removeStalePortalLocations(long time) {
		}
	}

	private static JsonElement teleport(Call call) throws ProbeException {
		EntityPlayerMP player = (EntityPlayerMP) player(call);
		double[] pos = null;
		if (call.has("pos")) {
			JsonElement given = call.args.get("pos");
			if (!given.isJsonArray() || given.getAsJsonArray().size() != 3) {
				throw ProbeException.badRequest("pos", "pos is [x, y, z]");
			}
			pos = new double[3];
			for (int i = 0; i < 3; i++) {
				pos[i] = given.getAsJsonArray().get(i).getAsDouble();
			}
		}
		JsonObject look = call.object("look");
		float yaw = look != null && look.has("yaw") ? look.get("yaw").getAsFloat() : player.rotationYaw;
		float pitch = look != null && look.has("pitch") ? look.get("pitch").getAsFloat() : player.rotationPitch;
		int to = player.dimension;
		if (call.has("dimension")) {
			Integer named = WorldOps.dimensionNumber(call.args.get("dimension"));
			if (named == null || MinecraftServer.getServer().worldServerForDimension(named) == null) {
				throw new ProbeException("NotFound", "no dimension " + call.args.get("dimension"),
					Json.object("what", call.args.get("dimension")));
			}
			to = named;
		}
		call.note = null;
		if (to != player.dimension) {
			if (call.inBatch) {
				throw ProbeException.badRequest("dimension", "a teleport to another dimension waits for the client: it can't be in a batch");
			}
			MinecraftServer server = MinecraftServer.getServer();
			server.getConfigurationManager().transferPlayerToDimension(player, to, new Placed(server.worldServerForDimension(to)));
			call.note = Worlds.dimension(to);
		} else if (pos == null) {
			throw ProbeException.badRequest("pos", "a teleport within the dimension needs pos");
		}
		if (pos != null) {
			player.playerNetServerHandler.setPlayerLocation(pos[0], pos[1], pos[2], yaw, pitch);
		}
		return new JsonObject();
	}

	/** After a teleport to another dimension: the client there, past the terrain screen (up to 200 of its ticks). */
	private static JsonElement arrive(Call call, JsonElement value) throws ProbeException, InterruptedException {
		String dimension = call.note;
		if (dimension == null) {
			return value;
		}
		Snapshot snapshot = call.probe.snapshot;
		Sides sides = Sides.get();
		long until = sides.ticks(Side.CLIENT) + ARRIVE_TICKS;
		while (!(dimension.equals(snapshot.dimension) && snapshot.inWorld)) {
			if (sides.ticks(Side.CLIENT) > until) {
				throw new ProbeException("TimedOut", "the client didn't arrive in " + dimension + " within " + ARRIVE_TICKS
					+ " ticks", Json.object("seconds", ARRIVE_TICKS / 20, "screen", snapshot.screen));
			}
			Thread.sleep(50);
		}
		return value;
	}

	// ---------------------------------------------------------------- the inventory, containers

	private static JsonElement inventory(Call call) throws ProbeException {
		InventoryPlayer inventory = player(call).inventory;
		String slot = call.string("slot", null);
		if (slot != null) {
			return Values.item(slot(inventory, slot));
		}
		JsonArray main = new JsonArray();
		for (int i = 0; i < inventory.mainInventory.length; i++) {
			main.add(Values.item(inventory.mainInventory[i]));
		}
		return Json.object(
			"selected", inventory.currentItem,
			"main", main,
			"armor", Json.object(
				"feet", Values.item(inventory.armorInventory[0]),
				"legs", Values.item(inventory.armorInventory[1]),
				"chest", Values.item(inventory.armorInventory[2]),
				"head", Values.item(inventory.armorInventory[3])),
			"cursor", Values.item(inventory.getItemStack()));
	}

	/** The stack in a named slot (PROTOCOL.md 8.5): main.N, armor.feet ... head, held, cursor. */
	static net.minecraft.item.ItemStack slot(InventoryPlayer inventory, String name) throws ProbeException {
		if (name.equals("held")) {
			return inventory.getCurrentItem();
		}
		if (name.equals("cursor")) {
			return inventory.getItemStack();
		}
		if (name.startsWith("main.")) {
			try {
				int index = Integer.parseInt(name.substring(5));
				if (index >= 0 && index < inventory.mainInventory.length) {
					return inventory.mainInventory[index];
				}
			} catch (NumberFormatException e) {
				// not a slot
			}
		}
		String[] armor = {"armor.feet", "armor.legs", "armor.chest", "armor.head"};
		for (int i = 0; i < armor.length; i++) {
			if (armor[i].equals(name)) {
				return inventory.armorInventory[i];
			}
		}
		throw ProbeException.badRequest("slot", "a slot is main.0 to main.35, armor.feet, .legs, .chest or .head, held or"
			+ " cursor (1.7.10 has no off hand), not " + name);
	}

	private static JsonElement container(Call call) throws ProbeException {
		EntityPlayer player = player(call);
		Container open = player.openContainer;
		JsonArray slots = new JsonArray();
		int first = -1;
		int last = -1;
		for (Object each : open.inventorySlots) {
			Slot slot = (Slot) each;
			slots.add(Json.object("index", slot.slotNumber, "item", Values.item(slot.getStack())));
			if (slot.inventory == player.inventory) {
				first = first < 0 ? slot.slotNumber : Math.min(first, slot.slotNumber);
				last = Math.max(last, slot.slotNumber);
			}
		}
		List<Integer> own = new ArrayList<>();
		if (first >= 0) {
			own.add(first);
			own.add(last);
		}
		return Json.object(
			"class", open.getClass().getName(),
			"window", open.windowId,
			"player_own", open == player.inventoryContainer,
			"slots", slots,
			"player_slots", first >= 0 ? own : null);
	}

	// ---------------------------------------------------------------- entities

	private static JsonElement entities(Call call) throws ProbeException {
		EntityPlayer player = player(call);
		World world = player.worldObj;
		double[] at = null;
		double radius = Double.MAX_VALUE;
		JsonObject near = call.object("near");
		if (near != null) {
			JsonElement pos = near.get("pos");
			if (pos != null && pos.isJsonPrimitive() && "player".equals(pos.getAsString())) {
				List<Double> feet = Values.pos(player);
				at = new double[]{feet.get(0), feet.get(1), feet.get(2)};
			} else if (pos != null && pos.isJsonArray() && pos.getAsJsonArray().size() == 3) {
				at = new double[]{pos.getAsJsonArray().get(0).getAsDouble(), pos.getAsJsonArray().get(1).getAsDouble(),
					pos.getAsJsonArray().get(2).getAsDouble()};
			} else {
				throw ProbeException.badRequest("near", "near's pos is [x, y, z] or \"player\"");
			}
			radius = near.has("radius") ? near.get("radius").getAsDouble() : 16.0;
		}
		List<String> types = new ArrayList<>();
		JsonElement type = call.args.get("type");
		if (type != null && type.isJsonArray()) {
			for (JsonElement each : type.getAsJsonArray()) {
				types.add(each.getAsString());
			}
		} else if (type != null && !type.isJsonNull()) {
			types.add(type.getAsString());
		}
		Class<?> kind = null;
		String className = call.string("class", null);
		if (className != null) {
			try {
				kind = Class.forName(className, false, Entity.class.getClassLoader());
			} catch (ClassNotFoundException e) {
				throw new ProbeException("NotFound", "no class " + className, Json.object("what", className));
			}
		}
		boolean players = call.flag("players", false);
		double[] from = at != null ? at : new double[]{player.posX, player.posY - player.yOffset, player.posZ};
		List<Entity> found = new ArrayList<>();
		for (Object each : new ArrayList<Object>(world.loadedEntityList)) {
			Entity entity = (Entity) each;
			if (!players && entity instanceof EntityPlayer) {
				continue;
			}
			if (!types.isEmpty() && !types.contains(Values.type(entity))) {
				continue;
			}
			if (kind != null && !kind.isInstance(entity)) {
				continue;
			}
			if (at != null && distance(entity, at) > radius) {
				continue;
			}
			found.add(entity);
		}
		found.sort(Comparator.comparingDouble(entity -> distance(entity, from)));
		JsonArray summaries = new JsonArray();
		for (Entity entity : found) {
			summaries.add(Values.entity(entity));
		}
		return summaries;
	}

	private static double distance(Entity entity, double[] to) {
		double dx = entity.posX - to[0];
		double dy = entity.posY - entity.yOffset - to[1];
		double dz = entity.posZ - to[2];
		return Math.sqrt(dx * dx + dy * dy + dz * dz);
	}

	// ---------------------------------------------------------------- screens

	private static JsonElement openScreen(Call call) throws ProbeException {
		Minecraft mc = Minecraft.getMinecraft();
		JsonElement given = call.args.get("screen");
		if (given != null && given.isJsonObject()) {
			Object made = Reflect.make(call, given.getAsJsonObject());
			if (!(made instanceof GuiScreen)) {
				throw ProbeException.badRequest("screen", made.getClass().getName() + " is no screen");
			}
			mc.displayGuiScreen((GuiScreen) made);
			return new JsonObject();
		}
		String name = call.string("screen", null);
		GuiScreen screen;
		if ("chat".equals(name)) {
			screen = new GuiChat(call.string("text", ""));
		} else if ("inventory".equals(name)) {
			screen = new GuiInventory(mc.thePlayer);
		} else if ("creative".equals(name)) {
			screen = new GuiContainerCreative(mc.thePlayer);
		} else if ("pause".equals(name)) {
			screen = new GuiIngameMenu();
		} else {
			throw ProbeException.badRequest("screen", "screen is chat, inventory, creative or pause, not " + name);
		}
		if (mc.thePlayer == null && !"pause".equals(name)) {
			throw new ProbeException("NotReady", name + " needs a world", null);
		}
		mc.displayGuiScreen(screen);
		return new JsonObject();
	}

	/** As Esc closes it: a container's screen through the player's own close, which tells the server too (8.9). */
	private static JsonElement closeScreen(Call call) {
		Minecraft mc = Minecraft.getMinecraft();
		if (mc.currentScreen instanceof GuiContainer && mc.thePlayer != null) {
			mc.thePlayer.closeScreen();
		} else {
			mc.displayGuiScreen(null);
		}
		return new JsonObject();
	}

	private static JsonElement oneTick(Call call, JsonElement value) throws ProbeException, InterruptedException {
		waitClient(call, 1);
		return value;
	}

	// ---------------------------------------------------------------- the mods' hooks

	private static JsonElement hooks(Call call) throws ProbeException {
		String hook = call.string("hook", null);
		Consumer<TasHooks> run;
		Side needs;
		if ("beforeRun".equals(hook)) {
			run = TasHooks::beforeRun;
			needs = Side.CLIENT;
		} else if ("afterRun".equals(hook)) {
			run = TasHooks::afterRun;
			needs = Side.CLIENT;
		} else if ("setUpWorld".equals(hook)) {
			run = TasHooks::setUpWorld;
			needs = Side.SERVER;
		} else if ("tearDownWorld".equals(hook)) {
			run = TasHooks::tearDownWorld;
			needs = Side.SERVER;
		} else if ("resetPlayer".equals(hook)) {
			List<EntityPlayerMP> players = new ArrayList<>();
			if (call.has("player")) {
				players.add(serverPlayer(call, call.string("player", null)));
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
			needs = Side.SERVER;
		} else {
			throw ProbeException.badRequest("hook", "hook is beforeRun, afterRun, setUpWorld, tearDownWorld or resetPlayer, not " + hook);
		}
		if (call.side != needs) {
			throw ProbeException.badRequest("side", hook + " runs on the " + needs.wire);
		}
		JsonArray plugins = new JsonArray();
		for (Object[] outcome : TasPlugins.run(run)) {
			Throwable thrown = (Throwable) outcome[1];
			plugins.add(thrown == null ? Json.object("class", outcome[0], "ok", true) : Json.object("class", outcome[0],
				"ok", false, "error", Json.object("type", "GameError", "message", outcome[0] + "." + hook + " threw " + thrown,
					"exception", thrown.getClass().getName(), "trace", Probe.trace(thrown))));
		}
		return Json.object("plugins", plugins);
	}
}

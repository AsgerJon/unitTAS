package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.ChatFormatting;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.ChatScreen;
import net.minecraft.client.gui.screens.PauseScreen;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.client.gui.screens.inventory.CreativeModeInventoryScreen;
import net.minecraft.client.gui.screens.inventory.InventoryScreen;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.commands.CommandSource;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.arguments.blocks.BlockStateParser;
import net.minecraft.core.BlockPos;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.TextColor;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.util.ProblemReporter;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntitySpawnReason;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.portal.TeleportTransition;
import net.minecraft.world.level.storage.TagValueInput;
import net.minecraft.world.level.storage.TagValueOutput;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * The game's things in 26.3 (SPEC.md 12.3, step 5): the bodies of command.run, the players, the inventory and
 * containers, the blocks, the entities, the screens and hooks.run (PROTOCOL.md 8.4 to 8.9), as 1.7.10's GameOps and
 * ThingOps have them, by 26.3's own calls and values (V26Values). Each body runs on the side its request named;
 * what an operation waits for after (the client arriving, a tick) is its settle phase, on the probe's thread.
 */
final class V26Things {

	/** How long the client may take to arrive in another dimension, in its ticks (as the reset allows). */
	private static final int ARRIVE_TICKS = 200;
	private static final TextColor RED = TextColor.fromLegacyFormat(ChatFormatting.RED);
	private static final String[] ARMOR = {"armor.feet", "armor.legs", "armor.chest", "armor.head"};
	private static final EquipmentSlot[] ARMOR_SLOTS = {EquipmentSlot.FEET, EquipmentSlot.LEGS, EquipmentSlot.CHEST,
		EquipmentSlot.HEAD};

	private V26Things() {
	}

	static void bind(Probe probe) {
		probe.op("command.run").does(V26Things::command).settles(V26Things::settled);
		probe.op("player.get").does(call -> {
			JsonObject value = V26Values.player(player(call));
			if (call.side == Side.CLIENT) {
				// the client's own: its camera (0 first person, 1 from behind, 2 from the front)
				value.addProperty("camera", Minecraft.getInstance().options.getCameraType().ordinal());
			}
			return value;
		});
		probe.op("player.teleport").does(V26Things::teleport).settles(V26Things::arrive);
		probe.op("inventory.get").does(V26Things::inventory);
		probe.op("inventory.set").does(V26Things::inventorySet);
		probe.op("container.get").does(V26Things::container);
		probe.op("block.get").does(V26Things::blockGet);
		probe.op("block.set").does(V26Things::blockSet);
		probe.op("entity.list").does(V26Things::entities);
		probe.op("entity.spawn").does(V26Things::spawn);
		probe.op("entity.get").does(call -> {
			Entity entity = entity(call);
			JsonObject value = V26Values.entity(entity);
			if (call.flag("nbt", false)) {
				TagValueOutput data = TagValueOutput.createWithContext(ProblemReporter.DISCARDING, registries(call));
				entity.saveWithoutId(data);
				value.addProperty("nbt", data.buildResult().toString());
			}
			return value;
		});
		probe.op("entity.remove").does(call -> {
			entity(call).discard();
			return new JsonObject();
		});
		probe.op("screen.open").does(V26Things::openScreen).settles(V26Things::oneTick);
		probe.op("screen.close").does(V26Things::closeScreen).settles(V26Things::oneTick);
		probe.op("hooks.run").does(V26Things::hooks);
	}

	// ---------------------------------------------------------------- the sides

	static MinecraftServer server() throws ProbeException {
		MinecraftServer server = Minecraft.getInstance().getSingleplayerServer();
		if (server == null) {
			throw new ProbeException("NotReady", "no world is open", null);
		}
		return server;
	}

	/** The side's registries: the server's, or the client's level's. */
	static HolderLookup.Provider registries(Call call) throws ProbeException {
		if (call.side == Side.CLIENT) {
			ClientLevel level = Minecraft.getInstance().level;
			if (level == null) {
				throw new ProbeException("NotReady", "the client has no world", null);
			}
			return level.registryAccess();
		}
		return server().registryAccess();
	}

	/** The side's player: the client's own, or on the server the one named by "player" (the only one when unnamed). */
	static Player player(Call call) throws ProbeException {
		if (call.side == Side.CLIENT) {
			LocalPlayer own = Minecraft.getInstance().player;
			if (own == null) {
				throw new ProbeException("NotReady", "the client has no player: no world is open", null);
			}
			return own;
		}
		return serverPlayer(call.string("player", null));
	}

	/** A player on the server by name; with no name, the only one (PROTOCOL.md 9.4). */
	static ServerPlayer serverPlayer(String name) throws ProbeException {
		List<ServerPlayer> players = server().getPlayerList().getPlayers();
		if (name == null) {
			if (players.size() == 1) {
				return players.get(0);
			}
			if (players.isEmpty()) {
				throw new ProbeException("NotReady", "no player is in the world", null);
			}
			List<String> names = new ArrayList<>();
			for (ServerPlayer each : players) {
				names.add(each.getName().getString());
			}
			throw ProbeException.badRequest("player", "name the player: " + String.join(", ", names) + " are in");
		}
		for (ServerPlayer each : players) {
			if (each.getName().getString().equals(name)) {
				return each;
			}
		}
		throw new ProbeException("NotFound", "no player " + name + " is in the world", Json.object("what", name));
	}

	static JsonElement waitClient(Call call, long ticks, JsonElement value) throws ProbeException, InterruptedException {
		try {
			Sides.get().waitTicks(Side.CLIENT, ticks, Sides.STALL_SECONDS);
		} catch (Sides.Stalled stalled) {
			throw Ops.stalled(call.probe, stalled);
		}
		return value;
	}

	private static JsonElement oneTick(Call call, JsonElement value) throws ProbeException, InterruptedException {
		return waitClient(call, 1, value);
	}

	// ---------------------------------------------------------------- commands

	/**
	 * Runs the command as the server runs a typed one (8.6), its feedback still going where it would. Its lines are
	 * what the command said back to its source, those in red its errors (26.3's failures are red, as 1.7.10's are).
	 */
	private static JsonElement command(Call call) throws ProbeException {
		String text = call.string("command", null);
		if (text == null) {
			throw ProbeException.badRequest("command", "command.run needs the command");
		}
		MinecraftServer server = server();
		JsonElement as = call.args.get("as");
		CommandSourceStack source;
		CommandSource said;
		if (as == null || as.isJsonNull() || (as.isJsonPrimitive() && "player".equals(as.getAsString()))) {
			ServerPlayer player = serverPlayer(call.string("player", null));
			source = player.createCommandSourceStack();
			said = player.commandSource();
		} else if (as.isJsonPrimitive() && "server".equals(as.getAsString())) {
			source = server.createCommandSourceStack();
			said = server;
		} else if (as.isJsonObject() && Json.string(as.getAsJsonObject(), "player") != null) {
			ServerPlayer player = serverPlayer(Json.string(as.getAsJsonObject(), "player"));
			source = player.createCommandSourceStack();
			said = player.commandSource();
		} else {
			throw ProbeException.badRequest("as", "as is \"player\", {\"player\": name} or \"server\", not " + as);
		}
		JsonArray lines = new JsonArray();
		JsonArray errors = new JsonArray();
		int[] result = {0};
		CommandSource heard = new CommandSource() {
			@Override
			public void sendSystemMessage(Component message) {
				String plain = message.getString();
				lines.add(plain);
				boolean error = RED.equals(message.getStyle().getColor());
				if (error) {
					errors.add(plain);
				}
				if (error ? said.acceptsFailure() : said.acceptsSuccess()) {
					said.sendSystemMessage(message);
				}
			}

			@Override
			public boolean acceptsSuccess() {
				return true;
			}

			@Override
			public boolean acceptsFailure() {
				return true;
			}

			@Override
			public boolean shouldInformAdmins() {
				return said.shouldInformAdmins();
			}
		};
		String typed = text.startsWith("/") ? text : "/" + text;
		server.getCommands().performPrefixedCommand(source.withSource(heard)
			.withCallback((success, value) -> result[0] = value), typed);
		return Json.object("result", result[0], "lines", lines, "errors", errors);
	}

	/** After the command, settle_ticks client ticks, so what it changed has reached the client (as 1.7.10's does). */
	private static JsonElement settled(Call call, JsonElement value) throws ProbeException, InterruptedException {
		return waitClient(call, call.number("settle_ticks", 3, 0, 1200), value);
	}

	// ---------------------------------------------------------------- teleporting

	private static double[] vec(Call call, String key) throws ProbeException {
		JsonElement given = call.args.get(key);
		if (given == null || !given.isJsonArray() || given.getAsJsonArray().size() != 3) {
			throw ProbeException.badRequest(key, key + " is [x, y, z]");
		}
		double[] out = new double[3];
		for (int i = 0; i < 3; i++) {
			out[i] = given.getAsJsonArray().get(i).getAsDouble();
		}
		return out;
	}

	/** The level a protocol name names; NotFound for none. */
	static ServerLevel level(MinecraftServer server, JsonElement dimension) throws ProbeException {
		Identifier id = dimension.isJsonPrimitive() ? Identifier.tryParse(dimension.getAsString()) : null;
		ServerLevel level = id == null ? null : server.getLevel(ResourceKey.create(Registries.DIMENSION, id));
		if (level == null) {
			throw new ProbeException("NotFound", "no dimension " + dimension, Json.object("what", dimension));
		}
		return level;
	}

	private static JsonElement teleport(Call call) throws ProbeException {
		ServerPlayer player = serverPlayer(call.string("player", null));
		double[] pos = call.has("pos") ? vec(call, "pos") : null;
		JsonObject look = call.object("look");
		float yaw = look != null && look.has("yaw") ? look.get("yaw").getAsFloat() : player.getYRot();
		float pitch = look != null && look.has("pitch") ? look.get("pitch").getAsFloat() : player.getXRot();
		ServerLevel to = call.has("dimension") ? level(server(), call.args.get("dimension")) : player.level();
		call.note = null;
		if (to != player.level()) {
			if (call.inBatch) {
				throw ProbeException.badRequest("dimension", "a teleport to another dimension waits for the client: it can't be in a batch");
			}
			Vec3 at = pos == null ? player.position() : new Vec3(pos[0], pos[1], pos[2]);
			player.teleport(new TeleportTransition(to, at, Vec3.ZERO, yaw, pitch, TeleportTransition.DO_NOTHING));
			call.note = to.dimension().identifier().toString();
			return new JsonObject();
		}
		if (pos == null) {
			throw ProbeException.badRequest("pos", "a teleport within the dimension needs pos");
		}
		player.connection.teleport(pos[0], pos[1], pos[2], yaw, pitch);
		return new JsonObject();
	}

	/** After a teleport to another dimension: the client there, in the world (up to 200 of its ticks). */
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
		Player player = player(call);
		HolderLookup.Provider registries = registries(call);
		String slot = call.string("slot", null);
		if (slot != null) {
			return V26Values.item(slot(player, slot), registries);
		}
		Inventory inventory = player.getInventory();
		JsonArray main = new JsonArray();
		for (ItemStack stack : inventory.getNonEquipmentItems()) {
			main.add(V26Values.item(stack, registries));
		}
		return Json.object(
			"selected", inventory.getSelectedSlot(),
			"main", main,
			"armor", Json.object(
				"feet", V26Values.item(player.getItemBySlot(EquipmentSlot.FEET), registries),
				"legs", V26Values.item(player.getItemBySlot(EquipmentSlot.LEGS), registries),
				"chest", V26Values.item(player.getItemBySlot(EquipmentSlot.CHEST), registries),
				"head", V26Values.item(player.getItemBySlot(EquipmentSlot.HEAD), registries)),
			"offhand", V26Values.item(player.getItemBySlot(EquipmentSlot.OFFHAND), registries),
			"cursor", V26Values.item(player.containerMenu.getCarried(), registries));
	}

	/** The stack in a named slot (PROTOCOL.md 8.5): main.N, armor.feet ... head, offhand, held, cursor. */
	static ItemStack slot(Player player, String name) throws ProbeException {
		Inventory inventory = player.getInventory();
		if (name.equals("held")) {
			return inventory.getSelectedItem();
		}
		if (name.equals("cursor")) {
			return player.containerMenu.getCarried();
		}
		if (name.equals("offhand")) {
			return player.getItemBySlot(EquipmentSlot.OFFHAND);
		}
		int main = mainIndex(inventory, name);
		if (main >= 0) {
			return inventory.getNonEquipmentItems().get(main);
		}
		for (int i = 0; i < ARMOR.length; i++) {
			if (ARMOR[i].equals(name)) {
				return player.getItemBySlot(ARMOR_SLOTS[i]);
			}
		}
		throw ProbeException.badRequest("slot", "a slot is main.0 to main.35, armor.feet, .legs, .chest or .head,"
			+ " offhand, held or cursor, not " + name);
	}

	private static int mainIndex(Inventory inventory, String name) {
		if (!name.startsWith("main.")) {
			return -1;
		}
		try {
			int index = Integer.parseInt(name.substring(5));
			return index >= 0 && index < inventory.getNonEquipmentItems().size() ? index : -1;
		} catch (NumberFormatException e) {
			return -1;
		}
	}

	private static JsonElement inventorySet(Call call) throws ProbeException {
		ServerPlayer player = serverPlayer(call.string("player", null));
		JsonObject items = call.object("items");
		if (items == null) {
			if (!call.has("slot")) {
				throw ProbeException.badRequest("slot", "inventory.set needs a slot and an item, or items");
			}
			items = new JsonObject();
			items.add(call.string("slot", null), call.args.get("item"));
		}
		// every slot and item checked before any is set
		List<Object[]> changes = new ArrayList<>();
		for (Map.Entry<String, JsonElement> entry : items.entrySet()) {
			slot(player, entry.getKey());
			changes.add(new Object[]{entry.getKey(), V26Values.stack(entry.getValue(), player.registryAccess())});
		}
		for (Object[] change : changes) {
			set(player, (String) change[0], (ItemStack) change[1]);
		}
		player.inventoryMenu.broadcastChanges();
		player.containerMenu.broadcastChanges();
		return new JsonObject();
	}

	/** Puts the stack in the named slot; the caller sends the changes. */
	static void set(ServerPlayer player, String slot, ItemStack stack) {
		Inventory inventory = player.getInventory();
		if (slot.equals("held")) {
			inventory.setItem(inventory.getSelectedSlot(), stack);
		} else if (slot.equals("cursor")) {
			player.containerMenu.setCarried(stack);
		} else if (slot.equals("offhand")) {
			player.setItemSlot(EquipmentSlot.OFFHAND, stack);
		} else if (slot.startsWith("main.")) {
			inventory.setItem(Integer.parseInt(slot.substring(5)), stack);
		} else {
			for (int i = 0; i < ARMOR.length; i++) {
				if (ARMOR[i].equals(slot)) {
					player.setItemSlot(ARMOR_SLOTS[i], stack);
				}
			}
		}
	}

	private static JsonElement container(Call call) throws ProbeException {
		Player player = player(call);
		HolderLookup.Provider registries = registries(call);
		AbstractContainerMenu open = player.containerMenu;
		JsonArray slots = new JsonArray();
		int first = -1;
		int last = -1;
		for (Slot slot : open.slots) {
			slots.add(Json.object("index", slot.index, "item", V26Values.item(slot.getItem(), registries)));
			if (slot.container == player.getInventory()) {
				first = first < 0 ? slot.index : Math.min(first, slot.index);
				last = Math.max(last, slot.index);
			}
		}
		List<Integer> own = new ArrayList<>();
		if (first >= 0) {
			own.add(first);
			own.add(last);
		}
		return Json.object(
			"class", open.getClass().getName(),
			"window", open.containerId,
			"player_own", open == player.inventoryMenu,
			"slots", slots,
			"player_slots", first >= 0 ? own : null);
	}

	// ---------------------------------------------------------------- blocks

	static BlockPos blockPos(Call call) throws ProbeException {
		JsonElement given = call.args.get("pos");
		if (given == null || !given.isJsonArray() || given.getAsJsonArray().size() != 3) {
			throw ProbeException.badRequest("pos", "pos is [x, y, z]");
		}
		return new BlockPos(given.getAsJsonArray().get(0).getAsInt(), given.getAsJsonArray().get(1).getAsInt(),
			given.getAsJsonArray().get(2).getAsInt());
	}

	private static JsonElement blockGet(Call call) throws ProbeException {
		BlockPos pos = blockPos(call);
		Level level = player(call).level();
		JsonObject value = V26Values.block(level.getBlockState(pos));
		if (call.flag("tile", false)) {
			BlockEntity tile = level.getBlockEntity(pos);
			if (tile == null) {
				value.add("tile", com.google.gson.JsonNull.INSTANCE);
			} else {
				value.addProperty("tile", tile.saveWithoutMetadata(level.registryAccess()).toString());
			}
		}
		return value;
	}

	/**
	 * Sets a block as /setblock does: its id and its state's properties read by the game's own parser (an unknown
	 * property or value is BadRequest, as /setblock refuses it); its block entity's data loaded over its own.
	 */
	private static JsonElement blockSet(Call call) throws ProbeException {
		BlockPos pos = blockPos(call);
		JsonObject block = call.object("block");
		String id = block == null ? null : Json.string(block, "id");
		if (id == null) {
			throw ProbeException.badRequest("block", "block is {\"id\": ..., \"state\": {...}}");
		}
		if (block.has("meta")) {
			throw ProbeException.badRequest("block", "26.3's blocks have no meta: a colour is in the id"
				+ " (minecraft:red_wool), the rest is the state's properties");
		}
		Identifier key = Identifier.tryParse(id);
		if (key == null || !BuiltInRegistries.BLOCK.containsKey(key)) {
			throw new ProbeException("NotFound", "this game has no block " + id, Json.object("what", id));
		}
		StringBuilder text = new StringBuilder(id);
		JsonObject properties = block.has("state") && block.get("state").isJsonObject() ? block.getAsJsonObject("state")
			: new JsonObject();
		if (properties.size() > 0) {
			List<String> pairs = new ArrayList<>();
			for (Map.Entry<String, JsonElement> property : properties.entrySet()) {
				pairs.add(property.getKey() + "=" + property.getValue().getAsString());
			}
			text.append('[').append(String.join(",", pairs)).append(']');
		}
		BlockState state;
		try {
			state = BlockStateParser.parseForBlock(BuiltInRegistries.BLOCK, text.toString(), false).blockState();
		} catch (CommandSyntaxException e) {
			throw ProbeException.badRequest("block", "the game doesn't read " + text + ": " + e.getMessage());
		}
		CompoundTag tileData = call.has("tile") ? V26Values.compound(call.string("tile", null), "tile") : null;
		String update = call.string("update", "default");
		int flags;
		switch (update) {
			case "default":
				// neighbours told, and the clients sent it, as a player's placing does
				flags = Block.UPDATE_ALL;
				break;
			case "none":
				// no neighbour updates; still sent, or the client would never see it
				flags = Block.UPDATE_CLIENTS;
				break;
			default:
				throw ProbeException.badRequest("update", "update is default or none, not " + update);
		}
		Level level = player(call).level();
		level.setBlock(pos, state, flags);
		if (tileData != null) {
			BlockEntity tile = level.getBlockEntity(pos);
			if (tile == null) {
				throw ProbeException.badRequest("tile", id + " has no block entity to take the data");
			}
			tile.loadWithComponents(TagValueInput.create(ProblemReporter.DISCARDING, level.registryAccess(), tileData));
			tile.setChanged();
			level.sendBlockUpdated(pos, state, state, Block.UPDATE_ALL);
		}
		return new JsonObject();
	}

	// ---------------------------------------------------------------- entities

	private static Entity entity(Call call) throws ProbeException {
		if (!call.has("entity")) {
			throw ProbeException.badRequest("entity", "the entity's id is needed: {\"entity\": n}");
		}
		int id = (int) call.number("entity", 0, Integer.MIN_VALUE, Integer.MAX_VALUE);
		Entity found = player(call).level().getEntity(id);
		if (found == null || found.isRemoved()) {
			throw new ProbeException("NotFound", "no entity " + id + " in the world (gone, or never there)",
				Json.object("what", id));
		}
		return found;
	}

	/** Made by its type, placed and added, as /summon does; refused where no chunk is loaded (8.8). */
	private static JsonElement spawn(Call call) throws ProbeException {
		String type = call.string("type", null);
		if (type == null) {
			throw ProbeException.badRequest("type", "entity.spawn needs the type");
		}
		double[] at = vec(call, "pos");
		ServerLevel level = serverPlayer(call.string("player", null)).level();
		Identifier key = Identifier.tryParse(type);
		Optional<EntityType<?>> kind = key == null ? Optional.empty() : BuiltInRegistries.ENTITY_TYPE.getOptional(key);
		if (kind.isEmpty()) {
			throw new ProbeException("NotFound", "this game has no entity " + type, Json.object("what", type));
		}
		if (!level.isLoaded(BlockPos.containing(at[0], at[1], at[2]))) {
			throw new ProbeException("NotReady", "no chunk is loaded at " + at[0] + " " + at[1] + " " + at[2]
				+ ": the " + type + " would have nowhere to be", Json.object("what", type));
		}
		Entity entity = kind.get().create(level, EntitySpawnReason.COMMAND);
		if (entity == null) {
			throw ProbeException.badRequest("type", type + " can't be made by a command");
		}
		JsonObject look = call.object("look");
		float yaw = look != null && look.has("yaw") ? look.get("yaw").getAsFloat() : 0.0F;
		float pitch = look != null && look.has("pitch") ? look.get("pitch").getAsFloat() : 0.0F;
		if (call.has("nbt")) {
			// the given data over the entity's own, as /summon's does
			CompoundTag given = V26Values.compound(call.string("nbt", null), "nbt");
			TagValueOutput own = TagValueOutput.createWithContext(ProblemReporter.DISCARDING, level.registryAccess());
			entity.saveWithoutId(own);
			CompoundTag data = own.buildResult().merge(given);
			entity.load(TagValueInput.create(ProblemReporter.DISCARDING, level.registryAccess(), data));
		}
		entity.snapTo(at[0], at[1], at[2], yaw, pitch);
		if (call.flag("initialize", false) && entity instanceof Mob mob) {
			mob.finalizeSpawn(level, level.getCurrentDifficultyAt(entity.blockPosition()), EntitySpawnReason.COMMAND, null);
		}
		if (!level.addFreshEntity(entity)) {
			throw new ProbeException("NotReady", "the world refused the " + type + " at " + at[0] + " " + at[1] + " "
				+ at[2], null);
		}
		return V26Values.entity(entity);
	}

	private static JsonElement entities(Call call) throws ProbeException {
		Player player = player(call);
		Level level = player.level();
		double[] at = null;
		double radius = Double.MAX_VALUE;
		JsonObject near = call.object("near");
		if (near != null) {
			JsonElement pos = near.get("pos");
			if (pos != null && pos.isJsonPrimitive() && "player".equals(pos.getAsString())) {
				at = new double[]{player.getX(), player.getY(), player.getZ()};
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
		double[] from = at != null ? at : new double[]{player.getX(), player.getY(), player.getZ()};
		Iterable<Entity> all = level instanceof ServerLevel server ? server.getAllEntities()
			: ((ClientLevel) level).entitiesForRendering();
		List<Entity> found = new ArrayList<>();
		for (Entity entity : all) {
			if (entity.isRemoved() || (!players && entity instanceof Player)) {
				continue;
			}
			if (!types.isEmpty() && !types.contains(V26Values.type(entity))) {
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
			summaries.add(V26Values.entity(entity));
		}
		return summaries;
	}

	private static double distance(Entity entity, double[] to) {
		double dx = entity.getX() - to[0];
		double dy = entity.getY() - to[1];
		double dz = entity.getZ() - to[2];
		return Math.sqrt(dx * dx + dy * dy + dz * dz);
	}

	// ---------------------------------------------------------------- screens

	private static JsonElement openScreen(Call call) throws ProbeException {
		Minecraft mc = Minecraft.getInstance();
		JsonElement given = call.args.get("screen");
		if (given != null && given.isJsonObject()) {
			Object made = Reflect.make(call, given.getAsJsonObject());
			if (!(made instanceof Screen)) {
				throw ProbeException.badRequest("screen", made.getClass().getName() + " is no screen");
			}
			mc.gui.setScreen((Screen) made);
			return new JsonObject();
		}
		String name = call.string("screen", null);
		if (!"pause".equals(name) && mc.player == null) {
			throw new ProbeException("NotReady", name + " needs a world", null);
		}
		Screen screen;
		if ("chat".equals(name)) {
			screen = new ChatScreen(call.string("text", ""), false);
		} else if ("inventory".equals(name)) {
			screen = new InventoryScreen(mc.player);
		} else if ("creative".equals(name)) {
			screen = new CreativeModeInventoryScreen(mc.player, mc.player.connection.enabledFeatures(),
				mc.options.operatorItemsTab().get());
		} else if ("pause".equals(name)) {
			screen = new PauseScreen(true);
		} else {
			throw ProbeException.badRequest("screen", "screen is chat, inventory, creative or pause, not " + name);
		}
		mc.gui.setScreen(screen);
		return new JsonObject();
	}

	/** As Esc closes it: a container's screen through the player's own close, which tells the server too (8.9). */
	private static JsonElement closeScreen(Call call) {
		Minecraft mc = Minecraft.getInstance();
		if (mc.gui.screen() instanceof AbstractContainerScreen && mc.player != null) {
			mc.player.closeContainer();
		} else {
			mc.gui.setScreen(null);
		}
		return new JsonObject();
	}

	// ---------------------------------------------------------------- the mods' hooks

	/** hooks.run (8.13): 26.3 has no plugins of its own yet, so every hook runs none; its arguments are checked alike. */
	private static JsonElement hooks(Call call) throws ProbeException {
		String hook = call.string("hook", null);
		Side needs;
		if ("beforeRun".equals(hook) || "afterRun".equals(hook)) {
			needs = Side.CLIENT;
		} else if ("setUpWorld".equals(hook) || "tearDownWorld".equals(hook) || "resetPlayer".equals(hook)) {
			needs = Side.SERVER;
		} else {
			throw ProbeException.badRequest("hook", "hook is beforeRun, afterRun, setUpWorld, tearDownWorld or resetPlayer, not " + hook);
		}
		if (call.side != needs) {
			throw ProbeException.badRequest("side", hook + " runs on the " + needs.wire);
		}
		if ("resetPlayer".equals(hook) && call.has("player")) {
			serverPlayer(call.string("player", null));
		}
		return Json.object("plugins", new JsonArray());
	}
}

package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.ChatFormatting;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.arguments.blocks.BlockStateParser;
import net.minecraft.core.BlockPos;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.TextColor;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
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
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * The game's things in 26.3 (SPEC.md 12.3, step 5): the bodies of command.run, the players, the inventory and
 * containers, the blocks, the entities, the screens and hooks.run (PROTOCOL.md 8.4 to 8.9), as 1.7.10's GameOps and
 * ThingOps have them, by 26.3's own calls and values (ModernValues). Each body runs on the side its request named;
 * what an operation waits for after (the client arriving, a tick) is its settle phase, on the probe's thread. No
 * client class (SPEC.md 19.7 step 10b): a dedicated server's probe runs these bodies too, and the client's own side is
 * asked through ModernClientSide; the screens are a client's alone (ModernScreens).
 */
final class ModernThings {

	/** How long the client may take to arrive in another dimension, in its ticks (as the reset allows). */
	private static final int ARRIVE_TICKS = 200;
	private static final TextColor RED = TextColor.fromLegacyFormat(ChatFormatting.RED);
	private static final String[] ARMOR = {"armor.feet", "armor.legs", "armor.chest", "armor.head"};
	private static final EquipmentSlot[] ARMOR_SLOTS = {EquipmentSlot.FEET, EquipmentSlot.LEGS, EquipmentSlot.CHEST,
		EquipmentSlot.HEAD};

	private ModernThings() {
	}

	/** The client's own side: a client's hooks give it (ModernHooks.register); a dedicated server has none. */
	static volatile ModernClientSide client;

	/** A client's: every operation here, on its integrated server's side and on its own. */
	static void bind(Probe probe) {
		bindShared(probe);
		probe.op("player.teleport").does(ModernThings::teleport).settles(ModernThings::arrive);
		probe.op("inventory.get").does(ModernThings::inventory);
		probe.op("inventory.set").does(ModernThings::inventorySet);
		probe.op("container.get").does(ModernThings::container);
		probe.op("block.get").does(ModernThings::blockGet);
		probe.op("block.set").does(ModernThings::blockSet);
		probe.op("entity.list").does(ModernThings::entities);
		probe.op("entity.spawn").does(ModernThings::spawn);
		probe.op("entity.get").does(call -> {
			Entity entity = entity(call);
			JsonObject value = ModernValues.entity(entity);
			if (call.flag("nbt", false)) {
				value.addProperty("nbt", VersionCommon.save(entity, registries(call)).toString());
			}
			return value;
		});
		probe.op("entity.remove").does(call -> {
			entity(call).discard();
			return new JsonObject();
		});
	}

	/**
	 * A dedicated server's (SPEC.md 19.7 step 10b), as 1.7.10's ServerOps: the server's commands, the players by name
	 * and their kick, the server's hooks.
	 */
	static void bindDedicated(Probe probe) {
		bindShared(probe);
		probe.op("players.list").does(call -> {
			JsonArray list = new JsonArray();
			for (ServerPlayer each : ModernServer.get().getPlayerList().getPlayers()) {
				list.add(summary(each));
			}
			return list;
		});
		probe.op("player.kick").does(ModernThings::kick);
	}

	/** Both a client's and a dedicated server's. */
	private static void bindShared(Probe probe) {
		probe.op("command.run").does(ModernThings::command).settles(ModernThings::settled);
		probe.op("player.get").does(call -> {
			JsonObject value = ModernValues.player(player(call));
			if (call.side == Side.CLIENT) {
				// the client's own: its camera (0 first person, 1 from behind, 2 from the front)
				value.addProperty("camera", client().camera());
			}
			return value;
		});
		probe.op("hooks.run").does(ModernThings::hooks);
	}

	// ---------------------------------------------------------------- the sides

	/** The client's own side; a dedicated server has none (its core refuses a client's request before a body runs). */
	static ModernClientSide client() {
		ModernClientSide given = client;
		if (given == null) {
			throw new IllegalStateException("no client side here: a dedicated server's probe has none");
		}
		return given;
	}

	/** The side's registries: the server's, or the client's level's. */
	static HolderLookup.Provider registries(Call call) throws ProbeException {
		if (call.side == Side.CLIENT) {
			return client().registries();
		}
		return ModernServer.get().registryAccess();
	}

	/** The side's player: the client's own, or on the server the one named by "player" (the only one when unnamed). */
	static Player player(Call call) throws ProbeException {
		if (call.side == Side.CLIENT) {
			return client().player();
		}
		return serverPlayer(call.string("player", null));
	}

	/** A player on the server by name; with no name, the only one (PROTOCOL.md 9.4). */
	static ServerPlayer serverPlayer(String name) throws ProbeException {
		List<ServerPlayer> players = ModernServer.get().getPlayerList().getPlayers();
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

	// ---------------------------------------------------------------- commands

	/** The command running now on this (the server's) thread, whose source's messages are its lines (heard). */
	private static final ThreadLocal<Heard> HEARING = new ThreadLocal<>();

	/** What a command's source was told while it ran: its lines, those in red its errors. */
	private static final class Heard {

		final Object source;
		final JsonArray lines = new JsonArray();
		final JsonArray errors = new JsonArray();

		Heard(Object source) {
			this.source = source;
		}
	}

	/**
	 * Runs the command as the server runs a typed one (8.6), from the source a typed one has (the player's own, or
	 * the server's), so the game does as it would: its feedback to that source, its notice to the other operators (a
	 * player's own command is not told back to it in grey). Its lines are what reached that source meanwhile (the hook
	 * command.heard on its sendSystemMessage), those in red its errors (26.3's failures are red, as 1.7.10's are).
	 */
	private static JsonElement command(Call call) throws ProbeException {
		String text = call.string("command", null);
		if (text == null) {
			throw ProbeException.badRequest("command", "command.run needs the command");
		}
		MinecraftServer server = ModernServer.get();
		JsonElement as = call.args.get("as");
		CommandSourceStack source;
		Object told;
		if (as == null || as.isJsonNull() || (as.isJsonPrimitive() && "player".equals(as.getAsString()))) {
			ServerPlayer player = serverPlayer(call.string("player", null));
			source = player.createCommandSourceStack();
			told = player;
		} else if (as.isJsonPrimitive() && "server".equals(as.getAsString())) {
			source = server.createCommandSourceStack();
			told = server;
		} else if (as.isJsonObject() && Json.string(as.getAsJsonObject(), "player") != null) {
			ServerPlayer player = serverPlayer(Json.string(as.getAsJsonObject(), "player"));
			source = player.createCommandSourceStack();
			told = player;
		} else {
			throw ProbeException.badRequest("as", "as is \"player\", {\"player\": name} or \"server\", not " + as);
		}
		int[] result = {0};
		Heard heard = new Heard(told);
		String typed = text.startsWith("/") ? text : "/" + text;
		HEARING.set(heard);
		try {
			server.getCommands().performPrefixedCommand(VersionCommon.withResult(source, result), typed);
		} finally {
			HEARING.remove();
		}
		return Json.object("result", result[0], "lines", heard.lines, "errors", heard.errors);
	}

	/**
	 * A system message to a player or the server (the hook command.heard): a line of the command running for that
	 * source on this thread, if one is; the action bar's (an overlay) is none.
	 */
	static void heard(Object to, Component message, boolean overlay) {
		Heard hearing = HEARING.get();
		if (hearing == null || hearing.source != to || overlay) {
			return;
		}
		String plain = message.getString();
		hearing.lines.add(plain);
		if (RED.equals(message.getStyle().getColor())) {
			hearing.errors.add(plain);
		}
	}

	/**
	 * After the command, settle_ticks client ticks, so what it changed has reached the client (as 1.7.10's does); a
	 * dedicated server has no client of its own to wait for: its players' clients are theirs.
	 */
	private static JsonElement settled(Call call, JsonElement value) throws ProbeException, InterruptedException {
		if (call.probe.dedicated()) {
			return value;
		}
		return waitClient(call, call.number("settle_ticks", 3, 0, 1200), value);
	}

	// ---------------------------------------------------------------- players by name

	/** A player in players.list (PROTOCOL.md 9.4), as 1.7.10's: name, uuid, entity id, dimension, where it stands. */
	static JsonObject summary(ServerPlayer player) {
		return Json.object(
			"name", player.getName().getString(),
			"uuid", player.getUUID().toString(),
			"entity", player.getId(),
			"dimension", VersionCommon.id(VersionCommon.level(player).dimension()),
			"pos", java.util.Arrays.asList(player.getX(), player.getY(), player.getZ()));
	}

	/** player.kick: the player named is sent off, as /kick does, with that reason; it must be named. */
	private static JsonElement kick(Call call) throws ProbeException {
		String name = call.string("player", null);
		if (name == null) {
			throw ProbeException.badRequest("player", "player.kick names the player to kick");
		}
		serverPlayer(name).connection.disconnect(Component.literal(call.string("reason", "kicked by unitTAS")));
		return new JsonObject();
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
		ResourceKey<Level> key = dimension.isJsonPrimitive()
			? VersionCommon.key(Registries.DIMENSION, dimension.getAsString()) : null;
		ServerLevel level = key == null ? null : server.getLevel(key);
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
		ServerLevel to = call.has("dimension") ? level(ModernServer.get(), call.args.get("dimension"))
			: VersionCommon.level(player);
		call.note = null;
		if (to != VersionCommon.level(player)) {
			if (call.inBatch) {
				throw ProbeException.badRequest("dimension", "a teleport to another dimension waits for the client: it can't be in a batch");
			}
			Vec3 at = pos == null ? player.position() : new Vec3(pos[0], pos[1], pos[2]);
			VersionCommon.teleport(player, to, at.x, at.y, at.z, yaw, pitch);
			call.note = VersionCommon.id(to.dimension());
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
			return ModernValues.item(slot(player, slot), registries);
		}
		Inventory inventory = player.getInventory();
		JsonArray main = new JsonArray();
		for (ItemStack stack : VersionCommon.mainItems(inventory)) {
			main.add(ModernValues.item(stack, registries));
		}
		return Json.object(
			"selected", VersionCommon.selectedSlot(inventory),
			"main", main,
			"armor", Json.object(
				"feet", ModernValues.item(player.getItemBySlot(EquipmentSlot.FEET), registries),
				"legs", ModernValues.item(player.getItemBySlot(EquipmentSlot.LEGS), registries),
				"chest", ModernValues.item(player.getItemBySlot(EquipmentSlot.CHEST), registries),
				"head", ModernValues.item(player.getItemBySlot(EquipmentSlot.HEAD), registries)),
			"offhand", ModernValues.item(player.getItemBySlot(EquipmentSlot.OFFHAND), registries),
			"cursor", ModernValues.item(player.containerMenu.getCarried(), registries));
	}

	/** The stack in a named slot (PROTOCOL.md 8.5): main.N, armor.feet ... head, offhand, held, cursor. */
	static ItemStack slot(Player player, String name) throws ProbeException {
		Inventory inventory = player.getInventory();
		if (name.equals("held")) {
			return VersionCommon.selectedItem(inventory);
		}
		if (name.equals("cursor")) {
			return player.containerMenu.getCarried();
		}
		if (name.equals("offhand")) {
			return player.getItemBySlot(EquipmentSlot.OFFHAND);
		}
		int main = mainIndex(inventory, name);
		if (main >= 0) {
			return VersionCommon.mainItems(inventory).get(main);
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
			return index >= 0 && index < VersionCommon.mainItems(inventory).size() ? index : -1;
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
			changes.add(new Object[]{entry.getKey(), ModernValues.stack(entry.getValue(), player.level().registryAccess())});
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
			inventory.setItem(VersionCommon.selectedSlot(inventory), stack);
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
			slots.add(Json.object("index", slot.index, "item", ModernValues.item(slot.getItem(), registries)));
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
			"class", Members.className(open.getClass()),
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
		JsonObject value = ModernValues.block(level.getBlockState(pos));
		if (call.flag("tile", false)) {
			BlockEntity tile = level.getBlockEntity(pos);
			if (tile == null) {
				value.add("tile", com.google.gson.JsonNull.INSTANCE);
			} else {
				value.addProperty("tile", VersionCommon.tileData(tile, level.registryAccess()).toString());
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
			throw ProbeException.badRequest("block", VersionName.port() + "'s blocks have no meta: a colour is in the id"
				+ " (minecraft:red_wool), the rest is the state's properties");
		}
		if (!VersionCommon.known(BuiltInRegistries.BLOCK, id)) {
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
			state = VersionCommon.parseBlock(text.toString());
		} catch (CommandSyntaxException e) {
			throw ProbeException.badRequest("block", "the game doesn't read " + text + ": " + e.getMessage());
		}
		CompoundTag tileData = call.has("tile") ? ModernValues.compound(call.string("tile", null), "tile") : null;
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
			VersionCommon.loadTile(tile, tileData, level.registryAccess());
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
		ServerLevel level = VersionCommon.level(serverPlayer(call.string("player", null)));
		Optional<EntityType<?>> kind = VersionCommon.byId(BuiltInRegistries.ENTITY_TYPE, type);
		if (kind.isEmpty()) {
			throw new ProbeException("NotFound", "this game has no entity " + type, Json.object("what", type));
		}
		if (!level.isLoaded(BlockPos.containing(at[0], at[1], at[2]))) {
			throw new ProbeException("NotReady", "no chunk is loaded at " + at[0] + " " + at[1] + " " + at[2]
				+ ": the " + type + " would have nowhere to be", Json.object("what", type));
		}
		Entity entity = VersionCommon.create(kind.get(), level);
		if (entity == null) {
			throw ProbeException.badRequest("type", type + " can't be made by a command");
		}
		JsonObject look = call.object("look");
		float yaw = look != null && look.has("yaw") ? look.get("yaw").getAsFloat() : 0.0F;
		float pitch = look != null && look.has("pitch") ? look.get("pitch").getAsFloat() : 0.0F;
		if (call.has("nbt")) {
			// the given data over the entity's own, as /summon's does
			CompoundTag given = ModernValues.compound(call.string("nbt", null), "nbt");
			CompoundTag data = VersionCommon.save(entity, level.registryAccess()).merge(given);
			VersionCommon.load(entity, data, level.registryAccess());
		}
		VersionCommon.place(entity, at[0], at[1], at[2], yaw, pitch);
		if (call.flag("initialize", false) && entity instanceof Mob mob) {
			VersionCommon.finalizeSpawn(mob, level);
		}
		if (!level.addFreshEntity(entity)) {
			throw new ProbeException("NotReady", "the world refused the " + type + " at " + at[0] + " " + at[1] + " "
				+ at[2], null);
		}
		return ModernValues.entity(entity);
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
				// by its Mojang name, the running one where the game runs under others (1.21.1's, 1.20.1's)
				kind = Class.forName(Members.runningClass(className), false, Entity.class.getClassLoader());
			} catch (ClassNotFoundException e) {
				throw new ProbeException("NotFound", "no class " + className, Json.object("what", className));
			}
		}
		boolean players = call.flag("players", false);
		double[] from = at != null ? at : new double[]{player.getX(), player.getY(), player.getZ()};
		Iterable<Entity> all = level instanceof ServerLevel server ? server.getAllEntities() : client().entities(level);
		List<Entity> found = new ArrayList<>();
		for (Entity entity : all) {
			if (entity.isRemoved() || (!players && entity instanceof Player)) {
				continue;
			}
			if (!types.isEmpty() && !types.contains(ModernValues.type(entity))) {
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
			summaries.add(ModernValues.entity(entity));
		}
		return summaries;
	}

	private static double distance(Entity entity, double[] to) {
		double dx = entity.getX() - to[0];
		double dy = entity.getY() - to[1];
		double dz = entity.getZ() - to[2];
		return Math.sqrt(dx * dx + dy * dy + dz * dz);
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

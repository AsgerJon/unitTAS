package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonObject;
import com.mojang.brigadier.StringReader;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import io.github.asgerjon.unittas.probe.link.Json;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.BiConsumer;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.arguments.blocks.BlockStateParser;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Registry;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.TagParser;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.TextComponent;
import net.minecraft.network.protocol.game.ClientboundSetCarriedItemPacket;
import net.minecraft.resources.ResourceKey;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundEvent;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.MobSpawnType;
import net.minecraft.world.entity.player.Abilities;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.food.FoodData;
import net.minecraft.world.inventory.ClickType;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.biome.Biome;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.DoorBlock;
import net.minecraft.world.level.block.TrapDoorBlock;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.Property;
import net.minecraft.world.level.material.Material;

/**
 * What 1.16.1 does its own way that names no client class (SPEC.md 19.7 steps 10b and 11): the part of Version that a
 * dedicated server's probe runs too, each version having one with these same methods, compiled with the shared
 * code against that version's classes. The client's part stays in Version.
 */
final class VersionCommon {

	private VersionCommon() {
	}

	// ---------------------------------------------------------------- the game

	/** The running world's folder's name; null when none is open. */
	static String worldFolder(MinecraftServer server) {
		return V1_16_1ServerWorlds.folder(server);
	}

	// ---------------------------------------------------------------- ids

	/** A key's id as text (minecraft:overworld). */
	static String id(ResourceKey<?> key) {
		return key.location().toString();
	}

	/** The registry's entry by its id; empty for an id it hasn't, or text that is no id. */
	static <T> Optional<T> byId(Registry<T> registry, String id) {
		ResourceLocation key = ResourceLocation.tryParse(id);
		return key == null ? Optional.empty() : registry.getOptional(key);
	}

	/** Whether the registry has the id (a defaulted one, the blocks', answers its default for any other). */
	static boolean known(Registry<?> registry, String id) {
		ResourceLocation key = ResourceLocation.tryParse(id);
		return key != null && registry.containsKey(key);
	}

	/** A key in the registry by its id; null for text that is no id (1.16.1's ResourceKey.create takes no wildcard). */
	static <T> ResourceKey<T> key(ResourceKey<Registry<T>> registry, String id) {
		ResourceLocation key = ResourceLocation.tryParse(id);
		return key == null ? null : ResourceKey.create(registry, key);
	}

	// ---------------------------------------------------------------- sounds

	/** A sound by its id, as a UI sound plays it; null for text that is no id. */
	static SoundEvent soundEvent(String id) {
		ResourceLocation key = ResourceLocation.tryParse(id);
		return key == null ? null : new SoundEvent(key);
	}

	// ---------------------------------------------------------------- the inventory

	/** The main slots: the hotbar's nine, then the rest. */
	static List<ItemStack> mainItems(Inventory inventory) {
		return inventory.items;
	}

	static int selectedSlot(Inventory inventory) {
		return inventory.selected;
	}

	static void selectSlot(Inventory inventory, int slot) {
		inventory.selected = slot;
	}

	static ItemStack selectedItem(Inventory inventory) {
		return inventory.getSelected();
	}

	// ---------------------------------------------------------------- items' data, chat, reach, results

	/** An item's own data as the protocol has it: its NBT as SNBT ("nbt"), when it has any (components are 1.20.5's). */
	static void itemData(ItemStack stack, Object registries, JsonObject item) {
		CompoundTag tag = stack.getTag();
		if (tag != null && !tag.isEmpty()) {
			item.addProperty("nbt", tag.toString());
		}
	}

	/**
	 * The protocol's item's data put on its stack: its NBT (SNBT), as /give reads it; BadRequest for components, which
	 * 1.16.1's items haven't (data components from 1.20.5), and for SNBT that isn't a compound.
	 */
	static void applyItemData(ItemStack stack, JsonObject given, String id, Object registries)
		throws ProbeException {
		if (given.has("components")) {
			throw ProbeException.badRequest("item", VersionName.port() + "'s items have NBT, not components (1.20.5's)");
		}
		String nbt = Json.string(given, "nbt");
		if (nbt != null) {
			stack.setTag(ModernValues.compound(nbt, "nbt"));
		}
	}

	/** The source, its command's result kept in result[0] as the command ends. */
	static CommandSourceStack withResult(CommandSourceStack source, int[] result) {
		return source.withCallback((context, success, value) -> result[0] = value);
	}

	/** A block entity's data, without its id and place, as /data reads it (1.16.1 saves them too: taken off). */
	static CompoundTag tileData(BlockEntity tile, Object registries) {
		CompoundTag data = tile.save(new CompoundTag());
		for (String metadata : new String[] {"id", "x", "y", "z"}) {
			data.remove(metadata);
		}
		return data;
	}

	/** A mob effect's id (minecraft:speed). */
	static String effectId(MobEffectInstance effect) {
		return Registry.MOB_EFFECT.getKey(effect.getEffect()).toString();
	}


	// ---------------------------------------------------------------- the world, players and entities

	/** The lowest block a level has: 1.16.1's worlds start at y 0. */
	static int minY(Level level) {
		return 0;
	}

	static ServerLevel level(ServerPlayer player) {
		return player.getLevel();
	}

	/** A player to another place, in that level, looking that way, nothing else changed. */
	static void teleport(ServerPlayer player, ServerLevel to, double x, double y, double z, float yaw, float pitch) {
		player.teleportTo(to, x, y, z, yaw, pitch);
	}

	/** No bed or anchor to respawn at. */
	static void clearRespawn(ServerPlayer player) {
		player.setRespawnPosition(Level.OVERWORLD, null, false, false);
	}

	/** The held slot told to the player's client. */
	static void sendHeldSlot(ServerPlayer player, int slot) {
		player.connection.send(new ClientboundSetCarriedItemPacket(slot));
	}

	/** An entity's data, without its id, as /data reads it. */
	static CompoundTag save(Entity entity, Object registries) {
		return entity.saveWithoutId(new CompoundTag());
	}

	static void load(Entity entity, CompoundTag data, Object registries) {
		entity.load(data);
	}

	/**
	 * A block entity's data loaded into it, as /data merge does. 1.16.1's load reads the block entity's place from the
	 * data too (x, y, z), so its own place goes in first: data without it would move it to 0, 0, 0, where its block
	 * isn't, and a chest so moved never opens.
	 */
	static void loadTile(BlockEntity tile, CompoundTag data, Object registries) {
		CompoundTag placed = data.copy();
		BlockPos at = tile.getBlockPos();
		placed.putInt("x", at.getX());
		placed.putInt("y", at.getY());
		placed.putInt("z", at.getZ());
		tile.load(tile.getBlockState(), placed);
	}

	/** An entity made as a command makes one; null for a kind a command can't make. */
	static Entity create(EntityType<?> kind, ServerLevel level) {
		return kind.create(level);
	}

	/** A mob given what it would have spawned with, as /summon does. */
	static void finalizeSpawn(Mob mob, ServerLevel level) {
		mob.finalizeSpawn(level, level.getCurrentDifficultyAt(mob.blockPosition()), MobSpawnType.COMMAND, null, null);
	}

	/** An entity put at a place, looking that way, before it is in a world. */
	static void place(Entity entity, double x, double y, double z, float yaw, float pitch) {
		entity.moveTo(x, y, z, yaw, pitch);
	}

	/** A block's state from text, as commands read it (minecraft:oak_stairs[facing=east]). */
	static BlockState parseBlock(String text) throws CommandSyntaxException {
		return new BlockStateParser(new StringReader(text), false).parse(false).getState();
	}

	/** A compound from SNBT, as the game's own commands read it. */
	static CompoundTag parseCompound(String text) throws CommandSyntaxException {
		return TagParser.parseTag(text);
	}

	/** Each of a state's properties, by its name and its value's name. */
	static void properties(BlockState state, BiConsumer<String, String> each) {
		for (Map.Entry<Property<?>, Comparable<?>> value : state.getValues().entrySet()) {
			each.accept(value.getKey().getName(), valueName(value.getKey(), value.getValue()));
		}
	}

	@SuppressWarnings("unchecked")
	private static <T extends Comparable<T>> String valueName(Property<T> property, Comparable<?> value) {
		return property.getName((T) value);
	}

	// ---------------------------------------------------------------- containers

	/** container.click's modes, in 1.7.10's order (pickup, quick_move, swap, clone, throw, quick_craft, pickup_all). */
	static Object[] clickModes() {
		return ClickType.values();
	}

	/** The class of a click's mode, for the screen's own slotClicked. */
	static Class<?> clickModeClass() {
		return ClickType.class;
	}

	/** The version's worlds, their server half alone (a dedicated server's, for the core's WorldOps.bindServer). */
	static GameWorlds serverWorlds() {
		return new V1_16_1ServerWorlds();
	}

	// ---- what 1.16.1 does another way (SPEC.md 19.7 step 11b): the shared code asks each version

	/** The game's blocks by id. */
	static Registry<Block> blocks() {
		return Registry.BLOCK;
	}

	/** The game's items by id. */
	static Registry<Item> items() {
		return Registry.ITEM;
	}

	/** The game's kinds of entity by id. */
	static Registry<EntityType<?>> entityTypes() {
		return Registry.ENTITY_TYPE;
	}

	/** The biomes' registry, by its key. */
	static ResourceKey<Registry<Biome>> biomeRegistry() {
		return Registry.BIOME_REGISTRY;
	}

	/** The dimensions' registry, by its key. */
	static ResourceKey<Registry<Level>> dimensionRegistry() {
		return Registry.DIMENSION_REGISTRY;
	}

	/** The world an entity is in (1.16.1: a field). */
	static Level levelOf(Entity entity) {
		return entity.level;
	}

	/** A player's inventory (a field). */
	static Inventory inventory(Player player) {
		return player.inventory;
	}

	/** A player's abilities (flying, may fly; a field). */
	static Abilities abilities(Player player) {
		return player.abilities;
	}

	/** Whether an entity stands on the ground. */
	static boolean onGround(Entity entity) {
		return entity.isOnGround();
	}

	/** An entity's yaw (a field). */
	static float yRot(Entity entity) {
		return entity.yRot;
	}

	/** An entity's pitch (a field). */
	static float xRot(Entity entity) {
		return entity.xRot;
	}

	/** An entity's yaw and pitch, set. */
	static void setRot(Entity entity, float yaw, float pitch) {
		entity.yRot = yaw;
		entity.xRot = pitch;
	}

	/** Whether an entity has left its world (a field). */
	static boolean removed(Entity entity) {
		return entity.removed;
	}

	/** An entity taken out of its world, with no death (1.16.1's remove()). */
	static void discard(Entity entity) {
		entity.remove();
	}

	/** An entity's fall so far forgotten. */
	static void resetFall(Entity entity) {
		entity.fallDistance = 0;
	}

	/**
	 * Sets a player's food saturation, through its field: 1.16.1's FoodData.setSaturation is the client's only (the
	 * dedicated server's jar hasn't it).
	 */
	static void setSaturation(Player player, float saturation) {
		Members.set(Members.field(FoodData.class, "saturationLevel"), player.getFoodData(), saturation);
	}

	/** The stack a player's cursor carries in an open screen (1.16.1 keeps it in the inventory). */
	static ItemStack carried(Player player) {
		return player.inventory.getCarried();
	}

	/** The stack a player's cursor carries, set. */
	static void setCarried(Player player, ItemStack stack) {
		player.inventory.setCarried(stack);
	}

	/** A player's whole inventory sent to its client again, the carried stack with it. */
	static void sendInventory(ServerPlayer player) {
		player.refreshContainer(player.inventoryMenu);
	}

	/** What a world's item and data calls take: 1.16.1's take none (NBT alone), so none. */
	static Object registries(Level level) {
		return null;
	}

	/** What a server's item and data calls take: 1.16.1's take none, so none. */
	static Object registries(MinecraftServer server) {
		return null;
	}

	/** The block a point is in (BlockPos floors each coordinate). */
	static BlockPos containing(double x, double y, double z) {
		return new BlockPos(x, y, z);
	}

	/** A text as it is. */
	static Component literal(String text) {
		return new TextComponent(text);
	}

	/** A command run as its source typed it (its slash first, which performCommand passes over). */
	static void perform(MinecraftServer server, CommandSourceStack source, String typed) {
		server.getCommands().performCommand(source, typed);
	}

	/** Whether a player opens the door by hand: 1.16.1's door passes on a hand when its material is metal. */
	static boolean opensByHand(DoorBlock door) {
		return door.defaultBlockState().getMaterial() != Material.METAL;
	}

	/** Whether a player opens the trapdoor by hand: as a door, by its material. */
	static boolean opensByHand(TrapDoorBlock block) {
		return block.defaultBlockState().getMaterial() != Material.METAL;
	}

	/** Whether a block's state is a liquid's. */
	static boolean liquid(BlockState state) {
		return state.getMaterial().isLiquid();
	}

	/**
	 * Whether a system message hooked as command.heard went to the action bar: 1.16.1's hooked sendMessage(Component,
	 * UUID) is the chat's (its action bar's is another method), so never.
	 */
	static boolean overlay(Object second) {
		return false;
	}
}

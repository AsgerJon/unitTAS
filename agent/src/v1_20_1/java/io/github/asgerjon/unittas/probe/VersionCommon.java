package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonObject;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.arguments.blocks.BlockStateParser;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.Registry;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.TagParser;
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
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.inventory.ClickType;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.TrapDoorBlock;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockSetType;
import net.minecraft.world.level.block.state.properties.Property;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.BiConsumer;

/**
 * What 1.20.1 does its own way that names no client class (SPEC.md 19.7 step 10b): the part of Version that a
 * dedicated server's probe runs too, each version having one with these same methods, compiled with the shared
 * code against that version's classes. The client's part stays in Version.
 */
final class VersionCommon {

	private VersionCommon() {
	}

	// ---------------------------------------------------------------- the game

	/** The running world's folder's name; null when none is open. */
	static String worldFolder(MinecraftServer server) {
		return V1_20_1ServerWorlds.folder(server);
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

	/** A key in the registry by its id; null for text that is no id. */
	static <T> ResourceKey<T> key(ResourceKey<? extends Registry<T>> registry, String id) {
		ResourceLocation key = ResourceLocation.tryParse(id);
		return key == null ? null : ResourceKey.create(registry, key);
	}

	// ---------------------------------------------------------------- sounds

	/** A sound by its id, as a UI sound plays it; null for text that is no id. */
	static SoundEvent soundEvent(String id) {
		ResourceLocation key = ResourceLocation.tryParse(id);
		return key == null ? null : SoundEvent.createVariableRangeEvent(key);
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
	static void itemData(ItemStack stack, HolderLookup.Provider registries, JsonObject item) {
		CompoundTag tag = stack.getTag();
		if (tag != null && !tag.isEmpty()) {
			item.addProperty("nbt", tag.toString());
		}
	}

	/**
	 * The protocol's item's data put on its stack: its NBT (SNBT), as /give reads it; BadRequest for components, which
	 * 1.20.1's items haven't (data components from 1.20.5), and for SNBT that isn't a compound.
	 */
	static void applyItemData(ItemStack stack, JsonObject given, String id, HolderLookup.Provider registries)
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

	/** A block entity's data, without its id and place, as /data reads it. */
	static CompoundTag tileData(BlockEntity tile, HolderLookup.Provider registries) {
		return tile.saveWithoutMetadata();
	}

	/** A mob effect's id (minecraft:speed). */
	static String effectId(MobEffectInstance effect) {
		return BuiltInRegistries.MOB_EFFECT.getKey(effect.getEffect()).toString();
	}

	/** A trapdoor's kind, whose hand-opening it says (a private field: 1.20.1 has no getter for it). */
	static BlockSetType trapdoorType(TrapDoorBlock block) {
		return Members.get(Trapdoors.TYPE, block);
	}

	/** Found at the first trapdoor asked about, once the probe has its names. */
	private static final class Trapdoors {

		static final java.lang.reflect.Field TYPE = Members.field(TrapDoorBlock.class, "type");
	}

	// ---------------------------------------------------------------- the world, players and entities

	/** The lowest block a level has. */
	static int minY(Level level) {
		return level.getMinBuildHeight();
	}

	static ServerLevel level(ServerPlayer player) {
		return player.serverLevel();
	}

	/** A player to another place, in that level, looking that way, nothing else changed. */
	static void teleport(ServerPlayer player, ServerLevel to, double x, double y, double z, float yaw, float pitch) {
		player.teleportTo(to, x, y, z, yaw, pitch);
	}

	/** No bed or anchor to respawn at. */
	static void clearRespawn(ServerPlayer player) {
		player.setRespawnPosition(Level.OVERWORLD, null, 0.0F, false, false);
	}

	/** The held slot told to the player's client. */
	static void sendHeldSlot(ServerPlayer player, int slot) {
		player.connection.send(new ClientboundSetCarriedItemPacket(slot));
	}

	/** An entity's data, without its id, as /data reads it. */
	static CompoundTag save(Entity entity, HolderLookup.Provider registries) {
		return entity.saveWithoutId(new CompoundTag());
	}

	static void load(Entity entity, CompoundTag data, HolderLookup.Provider registries) {
		entity.load(data);
	}

	static void loadTile(BlockEntity tile, CompoundTag data, HolderLookup.Provider registries) {
		tile.load(data);
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
		return BlockStateParser.parseForBlock(BuiltInRegistries.BLOCK.asLookup(), text, false).blockState();
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
		return new V1_20_1ServerWorlds();
	}
}

package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonObject;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import com.mojang.serialization.DataResult;
import io.github.asgerjon.unittas.probe.link.Json;
import java.util.List;
import java.util.Optional;
import java.util.function.BiConsumer;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.arguments.blocks.BlockStateParser;
import net.minecraft.core.BlockPos;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.Registry;
import net.minecraft.core.component.DataComponentPatch;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.NbtOps;
import net.minecraft.nbt.Tag;
import net.minecraft.nbt.TagParser;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.game.ClientboundSetHeldSlotPacket;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundEvent;
import net.minecraft.util.ProblemReporter;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntitySpawnReason;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Abilities;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.biome.Biome;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.DoorBlock;
import net.minecraft.world.level.block.TrapDoorBlock;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockSetType;
import net.minecraft.world.level.portal.TeleportTransition;
import net.minecraft.world.level.storage.TagValueInput;
import net.minecraft.world.level.storage.TagValueOutput;
import net.minecraft.world.phys.Vec3;

/**
 * What 26.3 does its own way that names no client class (SPEC.md 19.7 step 10b): the part of Version that a
 * dedicated server's probe runs too, each version having one with these same methods, compiled with the shared
 * code against that version's classes. The client's part stays in Version.
 */
final class VersionCommon {

	private VersionCommon() {
	}

	// ---------------------------------------------------------------- the game

	/** The running world's folder's name; null when none is open. */
	static String worldFolder(MinecraftServer server) {
		return V26ServerWorlds.folder(server);
	}

	// ---------------------------------------------------------------- ids

	/** A key's id as text (minecraft:overworld). */
	static String id(ResourceKey<?> key) {
		return key.identifier().toString();
	}

	/** The registry's entry by its id; empty for an id it hasn't, or text that is no id. */
	static <T> Optional<T> byId(Registry<T> registry, String id) {
		Identifier key = Identifier.tryParse(id);
		return key == null ? Optional.empty() : registry.getOptional(key);
	}

	/** Whether the registry has the id (a defaulted one, the blocks', answers its default for any other). */
	static boolean known(Registry<?> registry, String id) {
		Identifier key = Identifier.tryParse(id);
		return key != null && registry.containsKey(key);
	}

	/** A key in the registry by its id; null for text that is no id. */
	static <T> ResourceKey<T> key(ResourceKey<? extends Registry<T>> registry, String id) {
		Identifier key = Identifier.tryParse(id);
		return key == null ? null : ResourceKey.create(registry, key);
	}

	// ---------------------------------------------------------------- sounds

	/** A sound by its id, as a UI sound plays it; null for text that is no id. */
	static SoundEvent soundEvent(String id) {
		Identifier key = Identifier.tryParse(id);
		return key == null ? null : SoundEvent.createVariableRangeEvent(key);
	}

	// ---------------------------------------------------------------- the inventory

	/** The main slots: the hotbar's nine, then the rest. */
	static List<ItemStack> mainItems(Inventory inventory) {
		return inventory.getNonEquipmentItems();
	}

	static int selectedSlot(Inventory inventory) {
		return inventory.getSelectedSlot();
	}

	static void selectSlot(Inventory inventory, int slot) {
		inventory.setSelectedSlot(slot);
	}

	static ItemStack selectedItem(Inventory inventory) {
		return inventory.getSelectedItem();
	}

	// ---------------------------------------------------------------- items' data, chat, reach, results

	/** An item's own data as the protocol has it: its component patch as SNBT ("components"), when it has any. */
	static void itemData(ItemStack stack, Object lookup, JsonObject item) {
		HolderLookup.Provider registries = (HolderLookup.Provider) lookup;
		DataComponentPatch patch = stack.getComponentsPatch();
		if (!patch.isEmpty()) {
			Tag written = DataComponentPatch.CODEC.encodeStart(registries.createSerializationContext(NbtOps.INSTANCE), patch)
				.getOrThrow();
			item.addProperty("components", written.toString());
		}
	}

	/**
	 * The protocol's item's data put on its stack: its components (SNBT of a component patch); BadRequest for nbt, which
	 * 26.3's items haven't (data components from 1.20.5), and for components that aren't the item's.
	 */
	static void applyItemData(ItemStack stack, JsonObject given, String id, Object lookup)
		throws ProbeException {
		HolderLookup.Provider registries = (HolderLookup.Provider) lookup;
		if (given.has("nbt")) {
			throw ProbeException.badRequest("item", VersionName.port() + "'s items have components, not NBT");
		}
		String components = Json.string(given, "components");
		if (components == null) {
			return;
		}
		DataResult<DataComponentPatch> read = DataComponentPatch.CODEC.parse(
			registries.createSerializationContext(NbtOps.INSTANCE), ModernValues.compound(components, "item"));
		Optional<DataComponentPatch> patch = read.result();
		if (patch.isEmpty()) {
			throw ProbeException.badRequest("item", "the components aren't " + id + "'s: "
				+ read.error().map(DataResult.Error::message).orElse(components));
		}
		stack.applyComponents(patch.get());
	}

	/** The source, its command's result kept in result[0] as the command ends. */
	static CommandSourceStack withResult(CommandSourceStack source, int[] result) {
		return source.withCallback((success, value) -> result[0] = value);
	}

	/** A block entity's data, without its id and place, as /data reads it. */
	static CompoundTag tileData(BlockEntity tile, Object lookup) {
		HolderLookup.Provider registries = (HolderLookup.Provider) lookup;
		return tile.saveWithoutMetadata(registries);
	}

	/** A mob effect's id (minecraft:speed). */
	static String effectId(MobEffectInstance effect) {
		return effect.getEffect().unwrapKey().map(VersionCommon::id).orElse("");
	}

	/** Whether a player opens the trapdoor by hand (an iron one needs power): its kind says (its getter protected). */
	static boolean opensByHand(TrapDoorBlock block) {
		return Members.<BlockSetType>call(Trapdoors.TYPE, block).canOpenByHand();
	}

	/** Found at the first trapdoor asked about, once the probe has its names. */
	private static final class Trapdoors {

		static final java.lang.reflect.Method TYPE = Members.method(TrapDoorBlock.class, "getType");
	}

	// ---------------------------------------------------------------- the world, players and entities

	/** The lowest block a level has. */
	static int minY(Level level) {
		return level.getMinY();
	}

	static ServerLevel level(ServerPlayer player) {
		return player.level();
	}

	/** A player to another place, in that level, looking that way, nothing else changed. */
	static void teleport(ServerPlayer player, ServerLevel to, double x, double y, double z, float yaw, float pitch) {
		player.teleport(new TeleportTransition(to, new Vec3(x, y, z), Vec3.ZERO, yaw, pitch,
			TeleportTransition.DO_NOTHING));
	}

	/** No bed or anchor to respawn at. */
	static void clearRespawn(ServerPlayer player) {
		player.setRespawnPosition(null, false);
	}

	/** The held slot told to the player's client. */
	static void sendHeldSlot(ServerPlayer player, int slot) {
		player.connection.send(new ClientboundSetHeldSlotPacket(slot));
	}

	/** An entity's data, without its id, as /data reads it. */
	static CompoundTag save(Entity entity, Object lookup) {
		HolderLookup.Provider registries = (HolderLookup.Provider) lookup;
		TagValueOutput data = TagValueOutput.createWithContext(ProblemReporter.DISCARDING, registries);
		entity.saveWithoutId(data);
		return data.buildResult();
	}

	static void load(Entity entity, CompoundTag data, Object lookup) {
		HolderLookup.Provider registries = (HolderLookup.Provider) lookup;
		entity.load(TagValueInput.create(ProblemReporter.DISCARDING, registries, data));
	}

	static void loadTile(BlockEntity tile, CompoundTag data, Object lookup) {
		HolderLookup.Provider registries = (HolderLookup.Provider) lookup;
		tile.loadWithComponents(TagValueInput.create(ProblemReporter.DISCARDING, registries, data));
	}

	/** An entity made as a command makes one; null for a kind a command can't make. */
	static Entity create(EntityType<?> kind, ServerLevel level) {
		return kind.create(level, EntitySpawnReason.COMMAND);
	}

	/** A mob given what it would have spawned with, as /summon does. */
	static void finalizeSpawn(Mob mob, ServerLevel level) {
		mob.finalizeSpawn(level, level.getCurrentDifficultyAt(mob.blockPosition()), EntitySpawnReason.COMMAND, null);
	}

	/** An entity put at a place, looking that way, before it is in a world. */
	static void place(Entity entity, double x, double y, double z, float yaw, float pitch) {
		entity.snapTo(x, y, z, yaw, pitch);
	}

	/** A block's state from text, as commands read it (minecraft:oak_stairs[facing=east]). */
	static BlockState parseBlock(String text) throws CommandSyntaxException {
		return BlockStateParser.parseForBlock(BuiltInRegistries.BLOCK, text, false).blockState();
	}

	/** A compound from SNBT, as the game's own commands read it. */
	static CompoundTag parseCompound(String text) throws CommandSyntaxException {
		return TagParser.parseCompoundFully(text);
	}

	/** Each of a state's properties, by its name and its value's name. */
	static void properties(BlockState state, BiConsumer<String, String> each) {
		state.getValues().forEach(value -> each.accept(value.property().getName(), value.valueName()));
	}

	// ---------------------------------------------------------------- containers

	/** container.click's modes, in 1.7.10's order (pickup, quick_move, swap, clone, throw, quick_craft, pickup_all). */
	static Object[] clickModes() {
		return ContainerInput.values();
	}

	/** The class of a click's mode, for the screen's own slotClicked. */
	static Class<?> clickModeClass() {
		return ContainerInput.class;
	}

	/** The version's worlds, their server half alone (a dedicated server's, for the core's WorldOps.bindServer). */
	static GameWorlds serverWorlds() {
		return new V26ServerWorlds();
	}

	// ---- what 1.16.1 does another way (SPEC.md 19.7 step 11b): the shared code asks each version

	/** The game's blocks by id. */
	static Registry<Block> blocks() {
		return BuiltInRegistries.BLOCK;
	}

	/** The game's items by id. */
	static Registry<Item> items() {
		return BuiltInRegistries.ITEM;
	}

	/** The game's kinds of entity by id. */
	static Registry<EntityType<?>> entityTypes() {
		return BuiltInRegistries.ENTITY_TYPE;
	}

	/** The biomes' registry, by its key. */
	static ResourceKey<Registry<Biome>> biomeRegistry() {
		return Registries.BIOME;
	}

	/** The dimensions' registry, by its key. */
	static ResourceKey<Registry<Level>> dimensionRegistry() {
		return Registries.DIMENSION;
	}

	/** The world an entity is in. */
	static Level levelOf(Entity entity) {
		return entity.level();
	}

	/** A player's inventory. */
	static Inventory inventory(Player player) {
		return player.getInventory();
	}

	/** A player's abilities (flying, may fly). */
	static Abilities abilities(Player player) {
		return player.getAbilities();
	}

	/** Whether an entity stands on the ground. */
	static boolean onGround(Entity entity) {
		return entity.onGround();
	}

	/** An entity's yaw. */
	static float yRot(Entity entity) {
		return entity.getYRot();
	}

	/** An entity's pitch. */
	static float xRot(Entity entity) {
		return entity.getXRot();
	}

	/** An entity's yaw and pitch, set. */
	static void setRot(Entity entity, float yaw, float pitch) {
		entity.setYRot(yaw);
		entity.setXRot(pitch);
	}

	/** Whether an entity has left its world. */
	static boolean removed(Entity entity) {
		return entity.isRemoved();
	}

	/** An entity taken out of its world, as /kill's kind of removal is not (no death). */
	static void discard(Entity entity) {
		entity.discard();
	}

	/** An entity's fall so far forgotten. */
	static void resetFall(Entity entity) {
		entity.resetFallDistance();
	}

	/** Sets a player's food saturation. */
	static void setSaturation(Player player, float saturation) {
		player.getFoodData().setSaturation(saturation);
	}

	/** The stack a player's cursor carries in an open screen. */
	static ItemStack carried(Player player) {
		return player.containerMenu.getCarried();
	}

	/** The stack a player's cursor carries, set. */
	static void setCarried(Player player, ItemStack stack) {
		player.containerMenu.setCarried(stack);
	}

	/** A player's whole inventory sent to its client again. */
	static void sendInventory(ServerPlayer player) {
		player.inventoryMenu.sendAllDataToRemote();
	}

	/** What a world's item and data calls take (its registries). */
	static Object registries(Level level) {
		return level.registryAccess();
	}

	/** What a server's item and data calls take (its registries). */
	static Object registries(MinecraftServer server) {
		return server.registryAccess();
	}

	/** The block a point is in. */
	static BlockPos containing(double x, double y, double z) {
		return BlockPos.containing(x, y, z);
	}

	/** A text as it is. */
	static Component literal(String text) {
		return Component.literal(text);
	}

	/** A command run as its source typed it (its slash first). */
	static void perform(MinecraftServer server, CommandSourceStack source, String typed) {
		server.getCommands().performPrefixedCommand(source, typed);
	}

	/** Whether a player opens the door by hand (an iron one needs power). */
	static boolean opensByHand(DoorBlock door) {
		return door.type().canOpenByHand();
	}

	/** Whether a block's state is a liquid's. */
	static boolean liquid(BlockState state) {
		return state.liquid();
	}

	/**
	 * Whether a system message hooked as command.heard went to the action bar: its second argument, the overlay flag.
	 */
	static boolean overlay(Object second) {
		return second != null && (Boolean) second;
	}
}

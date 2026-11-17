package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import com.mojang.serialization.DataResult;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.component.DataComponentPatch;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.NbtOps;
import net.minecraft.nbt.Tag;
import net.minecraft.nbt.TagParser;
import net.minecraft.resources.Identifier;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.state.BlockState;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

/**
 * The game's things as the protocol's values in 26.3 (PROTOCOL.md 5; SPEC.md 12, D4), as 1.7.10's Values has them,
 * with 26.3's own: an item by its id and count, its data as components (SNBT of the stack's component patch; no meta,
 * no NBT); a block by its flattened id and its state's properties (no meta); an entity's type by its id
 * (minecraft:zombie). Read them on the thread of the side they belong to.
 */
final class V26Values {

	private V26Values() {
	}

	// ---------------------------------------------------------------- items

	/** An item: its id and count, and its components when it has any of its own; null for an empty slot. */
	static JsonElement item(ItemStack stack, HolderLookup.Provider registries) {
		if (stack == null || stack.isEmpty()) {
			return JsonNull.INSTANCE;
		}
		JsonObject item = Json.object(
			"id", BuiltInRegistries.ITEM.getKey(stack.getItem()).toString(),
			"count", stack.getCount());
		DataComponentPatch patch = stack.getComponentsPatch();
		if (!patch.isEmpty()) {
			Tag written = DataComponentPatch.CODEC.encodeStart(registries.createSerializationContext(NbtOps.INSTANCE), patch)
				.getOrThrow();
			item.addProperty("components", written.toString());
		}
		return item;
	}

	/**
	 * An item stack from the protocol's item, or ItemStack.EMPTY for null: NotFound for an id the game hasn't;
	 * BadRequest for meta or nbt, which 26.3's items haven't (the colour is in the id, damage and names are
	 * components), and for components that aren't the game's.
	 */
	static ItemStack stack(JsonElement value, HolderLookup.Provider registries) throws ProbeException {
		if (value == null || value.isJsonNull()) {
			return ItemStack.EMPTY;
		}
		if (!value.isJsonObject() || Json.string(value.getAsJsonObject(), "id") == null) {
			throw ProbeException.badRequest("item", "an item is {\"id\": ..., \"count\": ..., \"components\": ...} or null");
		}
		JsonObject given = value.getAsJsonObject();
		String id = Json.string(given, "id");
		if (given.has("meta")) {
			throw ProbeException.badRequest("item", "26.3's items have no meta: a colour is in the id"
				+ " (minecraft:red_wool), damage is a component");
		}
		if (given.has("nbt")) {
			throw ProbeException.badRequest("item", "26.3's items have components, not NBT");
		}
		Identifier key = Identifier.tryParse(id);
		Optional<Item> item = key == null ? Optional.empty() : BuiltInRegistries.ITEM.getOptional(key);
		if (item.isEmpty()) {
			throw new ProbeException("NotFound", "this game has no item " + id, Json.object("what", id));
		}
		int count = given.has("count") ? given.get("count").getAsInt() : 1;
		ItemStack stack = new ItemStack(item.get(), count);
		String components = Json.string(given, "components");
		if (components != null) {
			DataResult<DataComponentPatch> read = DataComponentPatch.CODEC.parse(
				registries.createSerializationContext(NbtOps.INSTANCE), compound(components, "item"));
			Optional<DataComponentPatch> patch = read.result();
			if (patch.isEmpty()) {
				throw ProbeException.badRequest("item", "the components aren't " + id + "'s: "
					+ read.error().map(DataResult.Error::message).orElse(components));
			}
			stack.applyComponents(patch.get());
		}
		return stack;
	}

	/** A compound from SNBT, as the game's own commands read it; a BadRequest naming the field for text that isn't one. */
	static CompoundTag compound(String text, String field) throws ProbeException {
		try {
			return TagParser.parseCompoundFully(text);
		} catch (CommandSyntaxException e) {
			throw ProbeException.badRequest(field, "not SNBT the game reads: " + e.getMessage());
		}
	}

	// ---------------------------------------------------------------- blocks

	/** A block: its id, and its state's properties when it has any (each by its name and its value's name). */
	static JsonObject block(BlockState state) {
		JsonObject block = Json.object("id", BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString());
		JsonObject properties = new JsonObject();
		state.getValues().forEach(each -> properties.addProperty(each.property().getName(), each.valueName()));
		if (properties.size() > 0) {
			block.add("state", properties);
		}
		return block;
	}

	// ---------------------------------------------------------------- entities and players

	static List<Double> pos(Entity entity) {
		return Arrays.asList(entity.getX(), entity.getY(), entity.getZ());
	}

	static JsonObject look(Entity entity) {
		return Json.object("yaw", (double) entity.getYRot(), "pitch", (double) entity.getXRot());
	}

	static List<Double> motion(Entity entity) {
		return Arrays.asList(entity.getDeltaMovement().x, entity.getDeltaMovement().y, entity.getDeltaMovement().z);
	}

	/** An entity's type as 26.3 names it: its id (minecraft:zombie; minecraft:player for a player). */
	static String type(Entity entity) {
		return EntityType.getKey(entity.getType()).toString();
	}

	static String dimension(Entity entity) {
		return entity.level().dimension().identifier().toString();
	}

	private static JsonElement riding(Entity entity) {
		return entity.getVehicle() == null ? JsonNull.INSTANCE : Json.object("entity", entity.getVehicle().getId());
	}

	/** An entity's summary (5.5). */
	static JsonObject entity(Entity entity) {
		JsonObject summary = Json.object(
			"entity", entity.getId(),
			"type", type(entity),
			"class", entity.getClass().getName(),
			"uuid", entity.getUUID().toString(),
			"pos", pos(entity),
			"look", look(entity),
			"motion", motion(entity),
			"dimension", dimension(entity),
			"alive", !entity.isRemoved(),
			"on_ground", entity.onGround(),
			"name", entity.getName().getString(),
			"custom_name", entity.hasCustomName() ? entity.getCustomName().getString() : null,
			"riding", riding(entity),
			"fire_ticks", Math.max(0, entity.getRemainingFireTicks()));
		if (entity instanceof LivingEntity living) {
			summary.addProperty("health", (double) living.getHealth());
			summary.addProperty("max_health", (double) living.getMaxHealth());
		}
		return summary;
	}

	/** A player (8.4's player.get): the server's player, or the client's own view of itself. */
	static JsonObject player(Player player) {
		String mode = player instanceof ServerPlayer server ? server.gameMode.getGameModeForPlayer().getName()
			: Minecraft.getInstance().gameMode == null ? "" : Minecraft.getInstance().gameMode.getPlayerMode().getName();
		List<Object> effects = new ArrayList<>();
		for (MobEffectInstance effect : player.getActiveEffects()) {
			effects.add(Json.object(
				"effect", effect.getEffect().unwrapKey().map(key -> key.identifier().toString()).orElse(""),
				// 26.3's effects have no number of their own: their id is the name
				"id", -1,
				"amplifier", effect.getAmplifier(),
				"duration", effect.getDuration(),
				"ambient", effect.isAmbient()));
		}
		return Json.object(
			"entity", player.getId(),
			"name", player.getName().getString(),
			"uuid", player.getUUID().toString(),
			"pos", pos(player),
			"look", look(player),
			"motion", motion(player),
			"dimension", dimension(player),
			"game_mode", mode,
			"health", (double) player.getHealth(),
			"max_health", (double) player.getMaxHealth(),
			"food", player.getFoodData().getFoodLevel(),
			"saturation", (double) player.getFoodData().getSaturationLevel(),
			"xp", Json.object("level", player.experienceLevel, "progress", (double) player.experienceProgress,
				"total", player.totalExperience),
			"on_ground", player.onGround(),
			"flying", player.getAbilities().flying,
			"may_fly", player.getAbilities().mayfly,
			"sneaking", player.isShiftKeyDown(),
			"sprinting", player.isSprinting(),
			"sleeping", player.isSleeping(),
			"riding", riding(player),
			"fire_ticks", Math.max(0, player.getRemainingFireTicks()),
			"air", player.getAirSupply(),
			"fall_distance", player.fallDistance,
			"arrows", player.getArrowCount(),
			"effects", effects);
	}
}

package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.entity.Entity;
import net.minecraft.entity.EntityList;
import net.minecraft.entity.EntityLiving;
import net.minecraft.entity.EntityLivingBase;
import net.minecraft.entity.player.EntityPlayer;
import net.minecraft.entity.player.EntityPlayerMP;
import net.minecraft.item.Item;
import net.minecraft.item.ItemStack;
import net.minecraft.potion.Potion;
import net.minecraft.potion.PotionEffect;

import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * The game's things as the protocol's values (PROTOCOL.md 5): items, entities and players, as the version has them
 * (1.7.10's registry names, its meta, its EntityList names). Read them on the thread of the side they belong to.
 */
final class Values {

	/** Entity.fire (private): MCP's name, then Searge's. */
	private static final Field FIRE = field(Entity.class, "fire", "field_70151_c");

	private Values() {
	}

	private static Field field(Class<?> owner, String... names) {
		for (String name : names) {
			try {
				Field found = owner.getDeclaredField(name);
				found.setAccessible(true);
				return found;
			} catch (NoSuchFieldException | RuntimeException e) {
				// the other name, in the other kind of game
			}
		}
		return null;
	}

	/** An item: its registry name, count and meta, and its NBT as SNBT when it has a tag; null for an empty slot (5.3). */
	static JsonElement item(ItemStack stack) {
		if (stack == null || stack.getItem() == null) {
			return JsonNull.INSTANCE;
		}
		JsonObject item = Json.object(
			"id", String.valueOf(Item.itemRegistry.getNameForObject(stack.getItem())),
			"count", stack.stackSize,
			// getMetadata: the stack's damage value (MCP stable_12's name for it)
			"meta", stack.getMetadata());
		if (stack.hasTagCompound()) {
			item.addProperty("nbt", Snbt.write(stack.getTagCompound()));
		}
		return item;
	}

	/** Where an entity stands: its feet (a client player's posY is at its eyes in 1.7.10: yOffset says how far). */
	static List<Double> pos(Entity entity) {
		return Arrays.asList(entity.posX, entity.posY - entity.yOffset, entity.posZ);
	}

	static JsonObject look(Entity entity) {
		return Json.object("yaw", (double) entity.rotationYaw, "pitch", (double) entity.rotationPitch);
	}

	/** An entity's type as the version names it: 1.7.10's EntityList name ("Zombie"), "Player" for a player. */
	static String type(Entity entity) {
		if (entity instanceof EntityPlayer) {
			return "Player";
		}
		String name = EntityList.getEntityString(entity);
		return name != null ? name : entity.getClass().getSimpleName();
	}

	/**
	 * How many more ticks the entity burns. Entity.fire itself goes below zero when it isn't burning (a player's sits at
	 * -20, its fireResistance): that is a cooldown of the game's, not fire.
	 */
	static int fireTicks(Entity entity) {
		try {
			return FIRE == null ? (entity.isBurning() ? 1 : 0) : Math.max(0, FIRE.getInt(entity));
		} catch (IllegalAccessException e) {
			return entity.isBurning() ? 1 : 0;
		}
	}

	/** An entity's summary (5.5). */
	static JsonObject entity(Entity entity) {
		JsonObject summary = Json.object(
			"entity", entity.getEntityId(),
			"type", type(entity),
			"class", entity.getClass().getName(),
			"uuid", entity.getUniqueID().toString(),
			"pos", pos(entity),
			"look", look(entity),
			"motion", Arrays.asList(entity.motionX, entity.motionY, entity.motionZ),
			"dimension", ServerWorld.dimension(entity.dimension),
			"alive", !entity.isDead,
			"on_ground", entity.onGround,
			"name", entity.getCommandSenderName(),
			"custom_name", entity instanceof EntityLiving && ((EntityLiving) entity).hasCustomNameTag()
				? ((EntityLiving) entity).getCustomNameTag() : null,
			"riding", entity.ridingEntity == null ? null : Json.object("entity", entity.ridingEntity.getEntityId()),
			"fire_ticks", fireTicks(entity));
		if (entity instanceof EntityLivingBase) {
			summary.addProperty("health", (double) ((EntityLivingBase) entity).getHealth());
			summary.addProperty("max_health", (double) ((EntityLivingBase) entity).getMaxHealth());
		}
		return summary;
	}

	/** A player (8.4's player.get): the server's player, or the client's own view of itself. */
	static JsonObject player(EntityPlayer player) {
		String mode;
		if (player instanceof EntityPlayerMP) {
			mode = ((EntityPlayerMP) player).theItemInWorldManager.getGameType().getName();
		} else {
			// the client knows its game mode by its abilities
			mode = player.capabilities.isCreativeMode ? "creative" : player.capabilities.allowEdit ? "survival" : "adventure";
		}
		List<Object> effects = new ArrayList<>();
		for (Object active : player.getActivePotionEffects()) {
			PotionEffect effect = (PotionEffect) active;
			Potion potion = Potion.potionTypes[effect.getPotionID()];
			effects.add(Json.object(
				"effect", potion == null ? null : potion.getName(),
				"id", effect.getPotionID(),
				"amplifier", effect.getAmplifier(),
				"duration", effect.getDuration(),
				"ambient", effect.getIsAmbient()));
		}
		return Json.object(
			"entity", player.getEntityId(),
			"name", player.getCommandSenderName(),
			"uuid", player.getUniqueID().toString(),
			"pos", pos(player),
			"look", look(player),
			"motion", Arrays.asList(player.motionX, player.motionY, player.motionZ),
			"dimension", ServerWorld.dimension(player.dimension),
			"game_mode", mode,
			"health", (double) player.getHealth(),
			"max_health", (double) player.getMaxHealth(),
			"food", player.getFoodStats().getFoodLevel(),
			"saturation", (double) player.getFoodStats().getSaturationLevel(),
			"xp", Json.object("level", player.experienceLevel, "progress", (double) player.experience,
				"total", player.experienceTotal),
			"on_ground", player.onGround,
			"flying", player.capabilities.isFlying,
			"may_fly", player.capabilities.allowFlying,
			"sneaking", player.isSneaking(),
			"sprinting", player.isSprinting(),
			"sleeping", player.isPlayerSleeping(),
			"riding", player.ridingEntity == null ? null : Json.object("entity", player.ridingEntity.getEntityId()),
			"fire_ticks", fireTicks(player),
			"air", player.getAir(),
			"fall_distance", (double) player.fallDistance,
			"arrows", player.getArrowCountInEntity(),
			"effects", effects);
	}

	// ---------------------------------------------------------------- an item from the protocol (ThingOps and Reflect, both sides)

	static ItemStack stack(JsonElement value) throws ProbeException {
		if (value == null || value.isJsonNull()) {
			return null;
		}
		if (!value.isJsonObject() || Json.string(value.getAsJsonObject(), "id") == null) {
			throw ProbeException.badRequest("item", "an item is {\"id\": ..., \"count\": ..., \"meta\": ...} or null");
		}
		JsonObject item = value.getAsJsonObject();
		String id = Json.string(item, "id");
		if (!Item.itemRegistry.containsKey(id)) {
			throw new ProbeException("NotFound", "this game has no item " + id, Json.object("what", id));
		}
		if (item.has("components")) {
			throw new ProbeException("Unsupported", "1.7.10's items have NBT, not components", null);
		}
		int count = item.has("count") ? item.get("count").getAsInt() : 1;
		int meta = item.has("meta") ? item.get("meta").getAsInt() : 0;
		ItemStack stack = new ItemStack((Item) Item.itemRegistry.getObject(id), count, meta);
		String nbt = Json.string(item, "nbt");
		if (nbt != null) {
			stack.setTagCompound(compound(nbt, "nbt"));
		}
		return stack;
	}

	/** A compound from SNBT; a BadRequest naming the field for text that isn't one. */
	static net.minecraft.nbt.NBTTagCompound compound(String text, String field) throws ProbeException {
		try {
			return Snbt.readCompound(text);
		} catch (IllegalArgumentException e) {
			throw ProbeException.badRequest(field, e.getMessage());
		}
	}
}

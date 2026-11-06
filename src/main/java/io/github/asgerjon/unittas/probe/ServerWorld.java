package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.entity.player.EntityPlayerMP;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.EnumDifficulty;
import net.minecraft.world.GameRules;
import net.minecraft.world.WorldServer;
import net.minecraft.world.WorldType;
import net.minecraft.world.storage.WorldInfo;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * A world's settings and state, read and set on the server thread: the integrated server's or a dedicated server's
 * alike (SPEC.md 11.3, step 2). No client class here, nor in anything it calls: on a dedicated server there are none,
 * and a class that so much as names one may fail to load there. {@link Worlds} hands its server-side helpers here.
 */
public final class ServerWorld {

	private ServerWorld() {
	}

	/** A dimension's protocol name (PROTOCOL.md 5.2): vanilla's three by their modern ids, a mod's as dim:n. */
	public static String dimension(int number) {
		switch (number) {
			case 0:
				return "minecraft:overworld";
			case -1:
				return "minecraft:the_nether";
			case 1:
				return "minecraft:the_end";
			default:
				return "dim:" + number;
		}
	}

	/** The world type's protocol name: default, flat, large_biomes, amplified, or the type's own name. */
	public static String typeName(WorldType type) {
		if (type == WorldType.LARGE_BIOMES) {
			return "large_biomes";
		}
		return type == null ? null : type.getWorldTypeName();
	}

	/** world.get's value: the overworld's settings and state, every dimension's rules being the overworld's. */
	public static JsonObject describe() {
		MinecraftServer server = MinecraftServer.getServer();
		WorldServer overworld = server.worldServerForDimension(0);
		WorldInfo info = overworld.getWorldInfo();
		GameRules rules = overworld.getGameRules();
		JsonObject ruleValues = new JsonObject();
		for (String rule : rules.getRules()) {
			ruleValues.addProperty(rule, rules.getGameRuleStringValue(rule));
		}
		List<String> dimensions = new ArrayList<>();
		for (WorldServer world : server.worldServers) {
			dimensions.add(dimension(world.provider.dimensionId));
		}
		List<Integer> spawn = new ArrayList<>();
		spawn.add(info.getSpawnX());
		spawn.add(info.getSpawnY());
		spawn.add(info.getSpawnZ());
		return Json.object(
			"folder", server.getFolderName(),
			"name", info.getWorldName(),
			"seed", info.getSeed(),
			"type", typeName(info.getTerrainType()),
			"generator", info.getGeneratorOptions(),
			"game_mode", info.getGameType().getName(),
			"hardcore", info.isHardcoreModeEnabled(),
			"cheats", info.areCommandsAllowed(),
			"difficulty", overworld.difficultySetting.name().toLowerCase(Locale.ROOT),
			"time", info.getWorldTotalTime(),
			"day_time", info.getWorldTime(),
			"raining", info.isRaining(),
			"thundering", info.isThundering(),
			"rules", ruleValues,
			"spawn", spawn,
			"dimensions", dimensions);
	}

	/** The rules the overworld lacks, of those named; none means all can be set. */
	public static List<String> unknownRules(Iterable<String> names) {
		GameRules rules = MinecraftServer.getServer().worldServerForDimension(0).getGameRules();
		List<String> unknown = new ArrayList<>();
		for (String name : names) {
			if (!rules.hasRule(name)) {
				unknown.add(name);
			}
		}
		return unknown;
	}

	/**
	 * The steady world a test world is given, by both runners and on both kinds of server: no daylight cycle, mob
	 * spawning, fire tick or mob griefing; the time noon (6000); clear weather. Each reset then holds the weather clear
	 * and sets Easy (Reset.world).
	 */
	public static void prepare() {
		Map<String, String> rules = new java.util.LinkedHashMap<>();
		rules.put("doDaylightCycle", "false");
		rules.put("doMobSpawning", "false");
		rules.put("doFireTick", "false");
		rules.put("mobGriefing", "false");
		setRules(rules);
		setTime(6000, null);
		setWeather(false, false, false);
	}

	/** Sets the game rules in every dimension (1.7.10 keeps them per world). */
	public static void setRules(Map<String, String> values) {
		for (WorldServer world : MinecraftServer.getServer().worldServers) {
			GameRules rules = world.getGameRules();
			for (Map.Entry<String, String> rule : values.entrySet()) {
				rules.setOrCreateGameRule(rule.getKey(), rule.getValue());
			}
		}
	}

	/** The day's time in every dimension, or in the one numbered (null: every one). */
	public static void setTime(long time, Integer dimension) {
		for (WorldServer world : MinecraftServer.getServer().worldServers) {
			if (dimension == null || world.provider.dimensionId == dimension) {
				world.setWorldTime(time);
			}
		}
	}

	/**
	 * The weather in every dimension. Held: its timers pushed out of reach and its strengths set at once, so it doesn't
	 * turn by itself mid-run (1.7.10 has no rule for that) and the sky is as asked from the next frame.
	 */
	public static void setWeather(boolean raining, boolean thundering, boolean hold) {
		for (WorldServer world : MinecraftServer.getServer().worldServers) {
			WorldInfo info = world.getWorldInfo();
			info.setRaining(raining);
			info.setThundering(thundering);
			if (hold) {
				info.setRainTime(1000000);
				info.setThunderTime(1000000);
				world.rainingStrength = world.prevRainingStrength = raining ? 1.0F : 0.0F;
				world.thunderingStrength = world.prevThunderingStrength = thundering ? 1.0F : 0.0F;
			}
		}
	}

	/** The difficulty of every dimension, and the spawns it allows (a client's own option is the client's to set). */
	public static void setDifficulty(EnumDifficulty difficulty) {
		for (WorldServer world : MinecraftServer.getServer().worldServers) {
			world.difficultySetting = difficulty;
			world.setAllowedSpawnTypes(difficulty != EnumDifficulty.PEACEFUL, true);
		}
	}

	/** The first player on the server, or null (read it on the server thread, or as a guess). */
	public static EntityPlayerMP firstPlayerOrNull() {
		MinecraftServer server = MinecraftServer.getServer();
		if (server == null || server.getConfigurationManager() == null || server.getConfigurationManager().playerEntityList.isEmpty()) {
			return null;
		}
		return (EntityPlayerMP) server.getConfigurationManager().playerEntityList.get(0);
	}
}

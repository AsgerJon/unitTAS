package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiDownloadTerrain;
import net.minecraft.client.gui.GuiMainMenu;
import net.minecraft.entity.player.EntityPlayerMP;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.EnumDifficulty;
import net.minecraft.world.GameRules;
import net.minecraft.world.WorldServer;
import net.minecraft.world.WorldSettings;
import net.minecraft.world.WorldType;
import net.minecraft.world.storage.ISaveFormat;
import net.minecraft.world.storage.WorldInfo;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Worlds in 1.7.10 (PROTOCOL.md 8.3): made, opened and left as the game's own screens do, and their settings read and
 * set. Each method says the thread it runs on. The probe's world operations and the Java runner both use these, so
 * there is one way to make a world.
 */
public final class Worlds {

	/** The test world's folder and name, unless asked otherwise. */
	public static final String FOLDER = "unittas";
	public static final String NAME = "unitTAS";
	/** Bedrock, two dirt, grass: the surface is y 3, a player stands at y 4. The empty last field: no structures. */
	public static final String FLAT_LAYERS = "2;7,2x3,2;1;";
	public static final long SEED = 20261029L;

	private Worlds() {
	}

	// ---------------------------------------------------------------- the client thread

	/**
	 * Makes and opens a world, as the Create New World screen does. It returns once the integrated server runs (the
	 * client thread waits for it there, as the game's own loading screen does); the player joins at the ticks after.
	 */
	public static void create(Minecraft mc, String folder, String name, long seed, WorldType type, String generator,
		WorldSettings.GameType mode, boolean cheats, boolean structures) {
		ISaveFormat saves = mc.getSaveLoader();
		saves.flushCache();
		// map features: structures that other generators add (a mod's, the Nether's) are made; flat layers name none
		WorldSettings settings = new WorldSettings(seed, mode, structures, false, type);
		if (cheats) {
			settings.enableCommands();
		}
		// the generator's options (the flat layers): MCP stable_12 names this setter setWorldName
		settings.setWorldName(generator);
		mc.launchIntegratedServer(folder, name, settings);
	}

	/** Opens a save, as the world list's Play does; IllegalStateException when there is none by that name. */
	public static void open(Minecraft mc, String folder) {
		ISaveFormat saves = mc.getSaveLoader();
		saves.flushCache();
		WorldInfo info = saves.getWorldInfo(folder);
		if (info == null) {
			throw new IllegalStateException("no save called " + folder + " in " + new File(mc.mcDataDir, "saves"));
		}
		mc.launchIntegratedServer(folder, info.getWorldName(), null);
	}

	/**
	 * Saves and leaves the world, as the pause menu's Save and Quit does. Forge's client waits here until the integrated
	 * server has stopped, and the server saves everything and flushes its file writes as it stops.
	 */
	public static void close(Minecraft mc) {
		if (mc.theWorld != null) {
			mc.theWorld.sendQuittingDisconnectingPacket();
		}
		mc.loadWorld(null);
		mc.displayGuiScreen(new GuiMainMenu());
	}

	/** The player is in the world on both sides, past the terrain screen. */
	public static boolean inWorld(Minecraft mc) {
		return mc.thePlayer != null && mc.theWorld != null && serverPlayerOrNull() != null
			&& !(mc.currentScreen instanceof GuiDownloadTerrain);
	}

	/** The first player on the integrated server's side, or null (read it on the server thread, or as a guess). */
	public static EntityPlayerMP serverPlayerOrNull() {
		MinecraftServer server = MinecraftServer.getServer();
		if (server == null || server.getConfigurationManager() == null || server.getConfigurationManager().playerEntityList.isEmpty()) {
			return null;
		}
		return (EntityPlayerMP) server.getConfigurationManager().playerEntityList.get(0);
	}

	// ---------------------------------------------------------------- the server thread

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

	/** The world type a protocol name names, or null. */
	public static WorldType type(String name) {
		switch (name) {
			case "default":
				return WorldType.DEFAULT;
			case "flat":
				return WorldType.FLAT;
			case "large_biomes":
				return WorldType.LARGE_BIOMES;
			case "amplified":
				return WorldType.AMPLIFIED;
			default:
				return null;
		}
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

	/** The difficulty of every dimension, and the spawns it allows (the client's own option is set on its thread). */
	public static void setDifficulty(EnumDifficulty difficulty) {
		for (WorldServer world : MinecraftServer.getServer().worldServers) {
			world.difficultySetting = difficulty;
			world.setAllowedSpawnTypes(difficulty != EnumDifficulty.PEACEFUL, true);
		}
	}
}

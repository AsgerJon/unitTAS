package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiDownloadTerrain;
import net.minecraft.client.gui.GuiMainMenu;
import net.minecraft.entity.player.EntityPlayerMP;
import net.minecraft.world.EnumDifficulty;
import net.minecraft.world.WorldSettings;
import net.minecraft.world.WorldType;
import net.minecraft.world.storage.ISaveFormat;
import net.minecraft.world.storage.WorldInfo;

import java.io.File;
import java.util.List;
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
		return ServerWorld.firstPlayerOrNull();
	}

	// ---------------------------------------------------------------- the server thread: ServerWorld's, which a dedicated server uses too

	/** A dimension's protocol name (PROTOCOL.md 5.2): vanilla's three by their modern ids, a mod's as dim:n. */
	public static String dimension(int number) {
		return ServerWorld.dimension(number);
	}

	/** The world type's protocol name: default, flat, large_biomes, amplified, or the type's own name. */
	public static String typeName(WorldType type) {
		return ServerWorld.typeName(type);
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
		return ServerWorld.describe();
	}

	/** The rules the overworld lacks, of those named; none means all can be set. */
	public static List<String> unknownRules(Iterable<String> names) {
		return ServerWorld.unknownRules(names);
	}

	/**
	 * The steady world a test world is given, on the server thread, by both runners (TasRunner.prepareWorld, and the
	 * probe's world.prepare for the orchestrator's): no daylight cycle, mob spawning, fire tick or mob griefing; the
	 * time noon (6000); clear weather. Each reset then holds the weather clear and sets Easy (Reset.world).
	 */
	public static void prepare() {
		ServerWorld.prepare();
	}

	/** Sets the game rules in every dimension (1.7.10 keeps them per world). */
	public static void setRules(Map<String, String> values) {
		ServerWorld.setRules(values);
	}

	/** The day's time in every dimension, or in the one numbered (null: every one). */
	public static void setTime(long time, Integer dimension) {
		ServerWorld.setTime(time, dimension);
	}

	/**
	 * The weather in every dimension. Held: its timers pushed out of reach and its strengths set at once, so it doesn't
	 * turn by itself mid-run (1.7.10 has no rule for that) and the sky is as asked from the next frame.
	 */
	public static void setWeather(boolean raining, boolean thundering, boolean hold) {
		ServerWorld.setWeather(raining, thundering, hold);
	}

	/** The difficulty of every dimension, and the spawns it allows (the client's own option is set on its thread). */
	public static void setDifficulty(EnumDifficulty difficulty) {
		ServerWorld.setDifficulty(difficulty);
	}
}

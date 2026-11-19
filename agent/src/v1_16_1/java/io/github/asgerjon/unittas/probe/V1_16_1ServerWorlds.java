package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Registry;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.Difficulty;
import net.minecraft.world.level.GameRules;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.biome.BiomeSource;
import net.minecraft.world.level.biome.OverworldBiomeSource;
import net.minecraft.world.level.chunk.ChunkGenerator;
import net.minecraft.world.level.levelgen.FlatLevelSource;
import net.minecraft.world.level.levelgen.NoiseBasedChunkGenerator;
import net.minecraft.world.level.levelgen.NoiseGeneratorSettings;
import net.minecraft.world.level.levelgen.flat.FlatLevelGeneratorSettings;
import net.minecraft.world.level.storage.LevelResource;
import net.minecraft.world.level.storage.WorldData;

import java.lang.reflect.Method;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * The world operations' server half in 1.16.1 (GameWorlds' server thread, for the core's WorldOps; SPEC.md 19.7
 * steps 10b and 11c): the world described, its rules, time and weather set, the steady world, as a client's integrated
 * server has them (V1_16_1Worlds extends it) and a dedicated server's probe too (VersionCommon.serverWorlds): no
 * client class. Its client thread's methods are refused: a dedicated server has no client.
 */
class V1_16_1ServerWorlds implements GameWorlds {

	/**
	 * The test world's layers, as 1.16.1's Customize box writes them: bedrock, two dirt, grass, on plains. A flat world
	 * starts at the bottom of the world (y 0 before 1.18), so the surface is y 3 and a player stands at y 4, as in
	 * 1.7.10.
	 */
	static final String TEST_LAYERS = "minecraft:bedrock,2*minecraft:dirt,minecraft:grass_block;minecraft:plains";

	/** A held weather's timers, in ticks: out of reach of a run (about 14 hours of game time). */
	private static final int HELD = 1000000;
	/** 1.16.1's /weather's duration when it is given none, in ticks (five minutes). */
	private static final int WEATHER_TICKS = 6000;

	@Override
	public String testLayers() {
		return TEST_LAYERS;
	}

	/** A flat world's layers as the Customize box writes them (ModernFlat). */
	@Override
	public String flatLayers(java.util.List<FlatLayer> layers, String biome) throws ProbeException {
		return ModernFlat.text(layers, biome);
	}

	/**
	 * 1.16.1's generator options are a flat world's layers only, as its Customize box writes them: layers of
	 * [height*]block from the bottom up, then ;biome. The game reads text it can't as the classic flat world; the
	 * probe refuses it, before anything is made.
	 */
	@Override
	public void checkGenerator(String type, String generator) throws ProbeException {
		if (generator.isEmpty()) {
			return;
		}
		if (!"flat".equals(type)) {
			throw ProbeException.badRequest("generator", "a " + type + " world takes no generator options in 1.16.1: they"
				+ " are a flat world's layers");
		}
		String[] parts = generator.split(";", -1);
		if (parts.length > 2) {
			throw ProbeException.badRequest("generator", "a flat world's layers are layers;biome, not " + generator);
		}
		for (String layer : parts[0].split(",", -1)) {
			String[] heightAndBlock = layer.split("\\*", 2);
			if (heightAndBlock.length == 2) {
				try {
					Integer.parseInt(heightAndBlock[0]);
				} catch (NumberFormatException e) {
					throw ProbeException.badRequest("generator", "a layer's height is a number, not " + heightAndBlock[0]
						+ " (in " + layer + ")");
				}
			}
			String block = heightAndBlock[heightAndBlock.length - 1];
			if (!VersionCommon.known(VersionCommon.blocks(), block)) {
				throw ProbeException.badRequest("generator", "1.16.1 has no block " + block + " (in " + layer + ")");
			}
		}
		if (parts.length == 2 && VersionCommon.key(VersionCommon.biomeRegistry(), parts[1]) == null) {
			throw ProbeException.badRequest("generator", "a biome is a name like minecraft:plains, not " + parts[1]);
		}
	}

	// ---------------------------------------------------------------- the client thread

	/** A dedicated server has no client: it makes, opens and closes no world, and has no client's options. */
	private static IllegalStateException noClient(String what) {
		return new IllegalStateException(what + " is a client's: a dedicated server has none");
	}

	@Override
	public void create(String folder, String name, long seed, String type, String generator, String gameMode,
		boolean cheats, boolean structures) throws Exception {
		throw noClient("create");
	}

	@Override
	public void open(String folder) throws Exception {
		throw noClient("open");
	}

	@Override
	public void close() throws Exception {
		throw noClient("close");
	}

	@Override
	public void picture(java.io.File file) throws Exception {
		throw noClient("picture");
	}

	@Override
	public void traceStart() {
		throw noClient("traceStart");
	}

	@Override
	public void traceStop() {
		throw noClient("traceStop");
	}

	@Override
	public void clientDifficulty(String difficulty) {
		throw noClient("clientDifficulty");
	}

	// ---------------------------------------------------------------- the server thread

	/** The running server: a client's integrated one, or the dedicated server the probe is in (ModernServer). */
	private static MinecraftServer server() {
		MinecraftServer server = ModernServer.orNull();
		if (server == null) {
			throw new IllegalStateException("no server is running: no world is open");
		}
		return server;
	}

	@Override
	public JsonObject describe() {
		MinecraftServer server = server();
		ServerLevel overworld = server.overworld();
		WorldData data = server.getWorldData();
		GameRules rules = server.getGameRules();
		JsonObject ruleValues = new JsonObject();
		for (Map.Entry<String, GameRules.Key<?>> rule : rulesByName().entrySet()) {
			ruleValues.addProperty(rule.getKey(), rules.getRule(rule.getValue()).serialize());
		}
		List<String> dimensions = server.levelKeys().stream().map(VersionCommon::id).collect(Collectors.toList());
		BlockPos spawn = overworld.getSharedSpawnPos();
		ChunkGenerator generator = overworld.getChunkSource().getGenerator();
		long seed = data.worldGenSettings().seed();
		return Json.object(
			"folder", folder(server),
			"name", data.getLevelName(),
			"seed", seed,
			"type", typeName(generator, seed),
			"generator", generatorText(generator),
			"game_mode", data.getGameType().getName(),
			"hardcore", data.isHardcore(),
			"cheats", data.getAllowCommands(),
			"difficulty", data.getDifficulty().getKey(),
			"time", overworld.getGameTime(),
			"day_time", overworld.getDayTime(),
			// the weather as /weather sets it (the level data's), not the rain's fading strength (Level.isRaining)
			"raining", overworld.getLevelData().isRaining(),
			"thundering", overworld.getLevelData().isThundering(),
			"rules", ruleValues,
			"spawn", Arrays.asList(spawn.getX(), spawn.getY(), spawn.getZ()),
			"dimensions", dimensions);
	}

	/** The save's folder: the last part of its path. */
	static String folder(MinecraftServer server) {
		Path root = server.getWorldPath(LevelResource.ROOT).toAbsolutePath().normalize();
		return root.getFileName().toString();
	}

	/** Found at the first large-biomes world described, once the probe has its names. */
	private static final class Biomes {

		static final java.lang.reflect.Field LARGE = Members.field(OverworldBiomeSource.class, "largeBiomes");
	}

	/**
	 * The world type's protocol name: default, flat, large_biomes, amplified, or the generator's own. 1.16.1 keeps no
	 * preset's name: its noise generator says whether it is the overworld's or the amplified one for the world's seed,
	 * and large biomes are its biome source's.
	 */
	private static String typeName(ChunkGenerator generator, long seed) {
		if (generator instanceof FlatLevelSource) {
			return "flat";
		}
		if (generator instanceof NoiseBasedChunkGenerator) {
			NoiseBasedChunkGenerator noise = (NoiseBasedChunkGenerator) generator;
			if (noise.stable(seed, NoiseGeneratorSettings.Preset.AMPLIFIED)) {
				return "amplified";
			}
			if (noise.stable(seed, NoiseGeneratorSettings.Preset.OVERWORLD)) {
				BiomeSource biomes = generator.getBiomeSource();
				return biomes instanceof OverworldBiomeSource && Members.<Boolean>get(Biomes.LARGE, biomes)
					? "large_biomes" : "default";
			}
			return "noise";
		}
		return Members.className(generator.getClass());
	}

	/** A flat world's layers as the Customize box writes them; "" for any other world. */
	private static String generatorText(ChunkGenerator generator) {
		if (!(generator instanceof FlatLevelSource)) {
			return "";
		}
		FlatLevelSource flat = (FlatLevelSource) generator;
		FlatLevelGeneratorSettings settings = flat.settings();
		String layers = settings.getLayersInfo().stream().map(Object::toString).collect(Collectors.joining(","));
		return layers + ";" + Registry.BIOME.getKey(settings.getBiome());
	}

	/** Every rule by its name (doDaylightCycle), as /gamerule names it. */
	private static Map<String, GameRules.Key<?>> rulesByName() {
		Map<String, GameRules.Key<?>> named = new LinkedHashMap<>();
		GameRules.visitGameRuleTypes(new GameRules.GameRuleTypeVisitor() {
			@Override
			public <T extends GameRules.Value<T>> void visit(GameRules.Key<T> key, GameRules.Type<T> type) {
				named.put(key.getId(), key);
			}
		});
		return named;
	}

	@Override
	public List<String> unknownRules(Iterable<String> names) {
		Map<String, GameRules.Key<?>> known = rulesByName();
		List<String> unknown = new ArrayList<>();
		for (String name : names) {
			if (!known.containsKey(name)) {
				unknown.add(name);
			}
		}
		return unknown;
	}

	/** As /gamerule sets them, a boolean rule to true or false, a number's to a number. A refused one sets none. */
	@Override
	public void setRules(Map<String, String> values) throws ProbeException {
		MinecraftServer server = server();
		Map<String, GameRules.Key<?>> named = rulesByName();
		List<Runnable> sets = new ArrayList<>();
		for (Map.Entry<String, String> rule : values.entrySet()) {
			sets.add(setter(server, named.get(rule.getKey()), rule.getKey(), rule.getValue()));
		}
		sets.forEach(Runnable::run);
	}

	private static Runnable setter(MinecraftServer server, GameRules.Key<?> key, String name, String text)
		throws ProbeException {
		GameRules.Value<?> value = server.getGameRules().getRule(key);
		if (value instanceof GameRules.BooleanValue) {
			GameRules.BooleanValue bool = (GameRules.BooleanValue) value;
			if (!text.equals("true") && !text.equals("false")) {
				throw ProbeException.badRequest("rules", name + " can't be " + text + " (it is true or false)");
			}
			return () -> bool.set(Boolean.parseBoolean(text), server);
		}
		if (value instanceof GameRules.IntegerValue) {
			GameRules.IntegerValue number = (GameRules.IntegerValue) value;
			int parsed;
			try {
				parsed = Integer.parseInt(text);
			} catch (NumberFormatException e) {
				throw ProbeException.badRequest("rules", name + " can't be " + text + " (it is a number)");
			}
			// 1.16.1's number rule has no set, and its dedicated server's jar has neither tryDeserialize nor setFrom
			// (the client's only): its value read from text, then the server told, as /gamerule's does
			Method deserialize = Members.method(GameRules.IntegerValue.class, "deserialize", String.class);
			Method changed = Members.method(GameRules.Value.class, "onChanged", MinecraftServer.class);
			return () -> {
				Members.call(deserialize, number, Integer.toString(parsed));
				Members.call(changed, number, server);
			};
		}
		throw ProbeException.badRequest("rules", name + " is a rule of a kind the probe doesn't set: "
			+ Members.className(value.getClass()));
	}

	@Override
	public boolean knowsDimension(JsonElement dimension) {
		return level(server(), dimension) != null;
	}

	/** The level a protocol name names, or null. */
	private static ServerLevel level(MinecraftServer server, JsonElement dimension) {
		ResourceKey<Level> key = dimension.isJsonPrimitive()
			? VersionCommon.key(VersionCommon.dimensionRegistry(), dimension.getAsString()) : null;
		return key == null ? null : server.getLevel(key);
	}

	/**
	 * As /time set: the day's time of every level, which the other dimensions take from the overworld's; or the named
	 * dimension's own (one following the overworld's keeps following it).
	 */
	@Override
	public void setTime(long time, JsonElement dimension) {
		MinecraftServer server = server();
		if (dimension.isJsonNull()) {
			for (ServerLevel level : server.getAllLevels()) {
				level.setDayTime(time);
			}
			return;
		}
		level(server, dimension).setDayTime(time);
	}

	/**
	 * As /weather sets it (the overworld's, which the other dimensions follow). Held: its timers out of reach and its
	 * strengths set at once, so it doesn't turn by itself mid-run and the sky is as asked from the next frame. Not
	 * held: 1.16.1's /weather's own duration, 6000 ticks, whichever the weather.
	 */
	@Override
	public void setWeather(boolean raining, boolean thundering, boolean hold) {
		MinecraftServer server = server();
		ServerLevel overworld = server.overworld();
		int duration = hold ? HELD : WEATHER_TICKS;
		int clear = raining ? 0 : duration;
		int rain = raining ? duration : 0;
		overworld.setWeatherParameters(clear, rain, raining, thundering);
		if (hold) {
			for (Level level : server.getAllLevels()) {
				setStrengths(level, raining ? 1.0F : 0.0F, thundering ? 1.0F : 0.0F);
			}
		}
	}

	/**
	 * A level's rain and thunder strengths, set at once as the client's Level.setRainLevel and setThunderLevel set them
	 * (each the strength and its last tick's). 1.16.1's dedicated server's jar hasn't those two, so through the fields
	 * both sides have.
	 */
	private static void setStrengths(Level level, float rain, float thunder) {
		Members.set(Members.field(Level.class, "oRainLevel"), level, rain);
		Members.set(Members.field(Level.class, "rainLevel"), level, rain);
		Members.set(Members.field(Level.class, "oThunderLevel"), level, thunder);
		Members.set(Members.field(Level.class, "thunderLevel"), level, thunder);
	}

	/** As /difficulty sets it. */
	@Override
	public void setDifficulty(String difficulty) {
		server().setDifficulty(Difficulty.byName(difficulty), true);
	}

	/**
	 * The steady world, by 1.16.1's rules: no daylight cycle, no mob spawning, no fire spread, no mob griefing; noon;
	 * clear weather. Each reset then holds the weather clear and sets Easy.
	 */
	@Override
	public void prepare() {
		MinecraftServer server = server();
		GameRules rules = server.getGameRules();
		rules.getRule(GameRules.RULE_DAYLIGHT).set(false, server);
		rules.getRule(GameRules.RULE_DOMOBSPAWNING).set(false, server);
		rules.getRule(GameRules.RULE_DOFIRETICK).set(false, server);
		rules.getRule(GameRules.RULE_MOBGRIEFING).set(false, server);
		setTime(6000, com.google.gson.JsonNull.INSTANCE);
		setWeather(false, false, false);
	}
}

package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.GenericMessageScreen;
import net.minecraft.client.gui.screens.PresetFlatWorldScreen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.HolderGetter;
import net.minecraft.core.HolderSet;
import net.minecraft.core.RegistryAccess;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.Difficulty;
import net.minecraft.world.level.GameRules;
import net.minecraft.world.level.GameType;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.LevelSettings;
import net.minecraft.world.level.WorldDataConfiguration;
import net.minecraft.world.level.biome.Biome;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.chunk.ChunkGenerator;
import net.minecraft.world.level.levelgen.FlatLevelSource;
import net.minecraft.world.level.levelgen.NoiseBasedChunkGenerator;
import net.minecraft.world.level.levelgen.NoiseGeneratorSettings;
import net.minecraft.world.level.levelgen.WorldDimensions;
import net.minecraft.world.level.levelgen.WorldOptions;
import net.minecraft.world.level.levelgen.flat.FlatLevelGeneratorSettings;
import net.minecraft.world.level.levelgen.placement.PlacedFeature;
import net.minecraft.world.level.levelgen.presets.WorldPreset;
import net.minecraft.world.level.levelgen.presets.WorldPresets;
import net.minecraft.world.level.levelgen.structure.StructureSet;
import net.minecraft.world.level.storage.LevelResource;
import net.minecraft.world.level.storage.WorldData;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Collectors;

/**
 * The world operations' game calls in 1.21.1 (GameWorlds, for the core's WorldOps; SPEC.md 19.7 step 6c), as 26.3's
 * (V26Worlds) each as the game's own screen or command does it: made as createFreshLevel makes it, opened as the
 * world list's Play, left as the pause menu's Save and Quit; the rules, the time, the weather and the difficulty as
 * /gamerule, /time set, /weather and /difficulty set them. Where 1.21.1 differs from 26.3: its rules are named in
 * camel case (doDaylightCycle) and are booleans or numbers; its time and weather are the overworld's (a level's own
 * data, the other dimensions following it), not clocks; fire's spread is a rule of its own (doFireTick).
 */
final class V1_21_1Worlds implements GameWorlds {

	/**
	 * The test world's layers, as 1.21.1's Customize box writes them: bedrock, two dirt, grass, on plains. A flat world
	 * starts at the bottom of the world (y -64), so the surface is y -61 and a player stands at y -60, as in 26.3.
	 */
	static final String TEST_LAYERS = "minecraft:bedrock,2*minecraft:dirt,minecraft:grass_block;minecraft:plains";
	/** A held weather's timers, in ticks: out of reach of a run (about 14 hours of game time). */
	private static final int HELD = 1000000;

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
	 * 1.21.1's generator options are a flat world's layers only, as its Customize box writes them: layers of
	 * [height*]block from the bottom up, then ;biome. The game reads text it can't as the classic flat world; the
	 * probe refuses it, before anything is made.
	 */
	@Override
	public void checkGenerator(String type, String generator) throws ProbeException {
		if (generator.isEmpty()) {
			return;
		}
		if (!"flat".equals(type)) {
			throw ProbeException.badRequest("generator", "a " + type + " world takes no generator options in 1.21.1: they"
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
			if (!Version.known(BuiltInRegistries.BLOCK, block)) {
				throw ProbeException.badRequest("generator", "1.21.1 has no block " + block + " (in " + layer + ")");
			}
		}
		if (parts.length == 2 && Version.key(Registries.BIOME, parts[1]) == null) {
			throw ProbeException.badRequest("generator", "a biome is a name like minecraft:plains, not " + parts[1]);
		}
	}

	// ---------------------------------------------------------------- the client thread

	/**
	 * Makes and opens a world as createFreshLevel does (the Create New World screen's settings: Normal, not hardcore,
	 * the default rules and data packs). It returns once the integrated server is ready; a failure the game catches
	 * (it goes back to the screen it came from) is a failure here, said.
	 */
	@Override
	public void create(String folder, String name, long seed, String type, String generator, String gameMode,
		boolean cheats, boolean structures) throws Exception {
		Minecraft mc = Minecraft.getInstance();
		LevelSettings settings = new LevelSettings(name, GameType.byName(gameMode), false, Difficulty.NORMAL, cheats,
			new GameRules(), WorldDataConfiguration.DEFAULT);
		WorldOptions options = new WorldOptions(seed, structures, false);
		AtomicReference<ProbeException> refused = new AtomicReference<>();
		mc.createWorldOpenFlows().createFreshLevel(folder, settings, options,
			registries -> dimensions(registries, type, generator, refused), Version.screen());
		if (refused.get() != null) {
			throw refused.get();
		}
		if (mc.getSingleplayerServer() == null) {
			throw new IllegalStateException("the game didn't make " + folder + " (its log says why)");
		}
	}

	/** The world's dimensions, from its type's preset; a flat world with layers of its own gets those. */
	private static WorldDimensions dimensions(RegistryAccess registries, String type, String generator,
		AtomicReference<ProbeException> refused) {
		WorldDimensions dimensions = registries.lookupOrThrow(Registries.WORLD_PRESET).getOrThrow(preset(type)).value()
			.createWorldDimensions();
		if (!"flat".equals(type) || generator.isEmpty()) {
			return dimensions;
		}
		HolderGetter<Block> blocks = registries.lookupOrThrow(Registries.BLOCK);
		HolderGetter<Biome> biomes = registries.lookupOrThrow(Registries.BIOME);
		HolderGetter<StructureSet> structureSets = registries.lookupOrThrow(Registries.STRUCTURE_SET);
		HolderGetter<PlacedFeature> placedFeatures = registries.lookupOrThrow(Registries.PLACED_FEATURE);
		// no structures: the layers name none, as 1.7.10's test layers don't
		Optional<HolderSet<StructureSet>> none = Optional.of(HolderSet.direct(new ArrayList<Holder<StructureSet>>()));
		FlatLevelGeneratorSettings base = new FlatLevelGeneratorSettings(none,
			FlatLevelGeneratorSettings.getDefaultBiome(biomes), FlatLevelGeneratorSettings.createLakesList(placedFeatures));
		FlatLevelGeneratorSettings made = PresetFlatWorldScreen.fromString(blocks, biomes, structureSets, placedFeatures,
			generator, base);
		String[] parts = generator.split(";", -1);
		String problem = null;
		if (made.structureOverrides() != none) {
			// fromString gave the classic flat world: it couldn't read the layers (checkGenerator reads them first)
			problem = "1.21.1 can't read the layers " + parts[0];
		} else if (parts.length == 2 && !made.getBiome().is(Version.key(Registries.BIOME, parts[1]))) {
			problem = "1.21.1 has no biome " + parts[1];
		}
		if (problem != null) {
			refused.set(ProbeException.badRequest("generator", problem));
			// createFreshLevel catches it and goes back to the screen it came from; create says why
			throw new IllegalArgumentException(problem);
		}
		return dimensions.replaceOverworldGenerator(registries, new FlatLevelSource(made));
	}

	private static ResourceKey<WorldPreset> preset(String type) {
		switch (type) {
			case "default":
				return WorldPresets.NORMAL;
			case "flat":
				return WorldPresets.FLAT;
			case "large_biomes":
				return WorldPresets.LARGE_BIOMES;
			case "amplified":
				return WorldPresets.AMPLIFIED;
			default:
				throw new IllegalArgumentException("1.21.1 has no world type " + type);
		}
	}

	/** Opens a save as the world list's Play does; a screen the game asks first on (a backup, say) stays up. */
	@Override
	public void open(String folder) {
		Minecraft.getInstance().createWorldOpenFlows().openWorld(folder, () -> { });
	}

	/**
	 * Saves and leaves, as the pause menu's Save and Quit: the level disconnected, then the game, which waits here
	 * until the integrated server stopped, behind the "Saving world" screen; then the title screen, as the pause
	 * menu opens it after.
	 */
	@Override
	public void close() {
		Minecraft mc = Minecraft.getInstance();
		if (mc.level != null) {
			mc.level.disconnect();
			mc.disconnect(new GenericMessageScreen(Component.translatable("menu.savingLevel")));
			mc.setScreen(new TitleScreen());
		}
	}

	@Override
	public void picture(java.io.File file) throws Exception {
		throw new UnsupportedOperationException("1.21.1's pictures come with a later step");
	}

	/** 1.21.1 keeps no trace of a world loading for the probe (debug.trace is empty). */
	@Override
	public void traceStart() {
		ModernTrace.start();
	}

	@Override
	public void traceStop() {
		ModernTrace.stop();
	}

	/** 1.21.1's client has no difficulty option of its own: it shows the server's. */
	@Override
	public void clientDifficulty(String difficulty) {
	}

	// ---------------------------------------------------------------- the server thread

	private static MinecraftServer server() {
		MinecraftServer server = Minecraft.getInstance().getSingleplayerServer();
		if (server == null) {
			throw new IllegalStateException("no integrated server");
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
		List<String> dimensions = server.levelKeys().stream().map(Version::id).collect(Collectors.toList());
		BlockPos spawn = overworld.getSharedSpawnPos();
		ChunkGenerator generator = overworld.getChunkSource().getGenerator();
		return Json.object(
			"folder", folder(server),
			"name", data.getLevelName(),
			"seed", data.worldGenOptions().seed(),
			"type", typeName(generator),
			"generator", generatorText(generator),
			"game_mode", data.getGameType().getName(),
			"hardcore", data.isHardcore(),
			"cheats", data.isAllowCommands(),
			"difficulty", data.getDifficulty().getSerializedName(),
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

	/** The world type's protocol name: default, flat, large_biomes, amplified, or the generator's own. */
	private static String typeName(ChunkGenerator generator) {
		if (generator instanceof FlatLevelSource) {
			return "flat";
		}
		if (generator instanceof NoiseBasedChunkGenerator noise) {
			Holder<NoiseGeneratorSettings> settings = noise.generatorSettings();
			if (settings.is(NoiseGeneratorSettings.OVERWORLD)) {
				return "default";
			}
			if (settings.is(NoiseGeneratorSettings.LARGE_BIOMES)) {
				return "large_biomes";
			}
			if (settings.is(NoiseGeneratorSettings.AMPLIFIED)) {
				return "amplified";
			}
			return settings.unwrapKey().map(Version::id).orElse("noise");
		}
		return Members.className(generator.getClass());
	}

	/** A flat world's layers as the Customize box writes them; "" for any other world. */
	private static String generatorText(ChunkGenerator generator) {
		if (!(generator instanceof FlatLevelSource flat)) {
			return "";
		}
		FlatLevelGeneratorSettings settings = flat.settings();
		String layers = settings.getLayersInfo().stream().map(Object::toString).collect(Collectors.joining(","));
		return layers + ";" + settings.getBiome().unwrapKey().map(Version::id).orElse("");
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
		if (value instanceof GameRules.BooleanValue bool) {
			if (!text.equals("true") && !text.equals("false")) {
				throw ProbeException.badRequest("rules", name + " can't be " + text + " (it is true or false)");
			}
			return () -> bool.set(Boolean.parseBoolean(text), server);
		}
		if (value instanceof GameRules.IntegerValue number) {
			int parsed;
			try {
				parsed = Integer.parseInt(text);
			} catch (NumberFormatException e) {
				throw ProbeException.badRequest("rules", name + " can't be " + text + " (it is a number)");
			}
			return () -> number.set(parsed, server);
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
		ResourceKey<Level> key = dimension.isJsonPrimitive() ? Version.key(Registries.DIMENSION, dimension.getAsString())
			: null;
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
	 * held: its durations drawn as /weather draws them.
	 */
	@Override
	public void setWeather(boolean raining, boolean thundering, boolean hold) {
		MinecraftServer server = server();
		ServerLevel overworld = server.overworld();
		int clear = raining ? 0 : hold ? HELD : ServerLevel.RAIN_DELAY.sample(overworld.getRandom());
		int rain = !raining ? 0 : hold ? HELD
			: (thundering ? ServerLevel.THUNDER_DURATION : ServerLevel.RAIN_DURATION).sample(overworld.getRandom());
		overworld.setWeatherParameters(clear, rain, raining, thundering);
		if (hold) {
			for (Level level : server.getAllLevels()) {
				level.setRainLevel(raining ? 1.0F : 0.0F);
				level.setThunderLevel(thundering ? 1.0F : 0.0F);
			}
		}
	}

	/** As /difficulty sets it. */
	@Override
	public void setDifficulty(String difficulty) {
		server().setDifficulty(Difficulty.byName(difficulty), true);
	}

	/**
	 * The steady world, by 1.21.1's rules: no daylight cycle, no mob spawning, no fire spread, no mob griefing; noon;
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

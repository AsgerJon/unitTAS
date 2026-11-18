package io.github.asgerjon.unittas.probe;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.PresetFlatWorldScreen;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.core.Holder;
import net.minecraft.core.HolderGetter;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.HolderSet;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.Difficulty;
import net.minecraft.world.level.GameType;
import net.minecraft.world.level.LevelSettings;
import net.minecraft.world.level.WorldDataConfiguration;
import net.minecraft.world.level.biome.Biome;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.levelgen.FlatLevelSource;
import net.minecraft.world.level.levelgen.WorldDimensions;
import net.minecraft.world.level.levelgen.WorldOptions;
import net.minecraft.world.level.levelgen.flat.FlatLevelGeneratorSettings;
import net.minecraft.world.level.levelgen.placement.PlacedFeature;
import net.minecraft.world.level.levelgen.presets.WorldPreset;
import net.minecraft.world.level.levelgen.presets.WorldPresets;
import net.minecraft.world.level.levelgen.structure.StructureSet;

import java.util.ArrayList;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

/**
 * The world operations' game calls in 26.3 (GameWorlds, for the core's WorldOps; SPEC.md 12.3, step 4), each as the
 * game's own screen or command does it: a world made as createFreshLevel makes it (the Create New World screen's
 * settings), opened as the world list's Play opens it, left as the pause menu's Save and Quit leaves it; the rules,
 * the time, the weather and the difficulty as /gamerule, /time set, /weather and /difficulty set them. It keeps
 * nothing, so a new one is the same as any. Only a client makes one (ModernPort.worlds): it names client classes;
 * its server half is V26ServerWorlds'.
 */
final class V26Worlds extends V26ServerWorlds {

	// ---------------------------------------------------------------- the client thread

	/**
	 * Makes and opens a world as createFreshLevel does (the Create New World screen's settings: Normal, not hardcore,
	 * the default data packs). It returns once the integrated server is ready: the client thread waits for it there,
	 * as the game's own loading screen does. The game catches a failure of its own and goes back to the screen it came
	 * from; that is a failure here, said.
	 */
	@Override
	public void create(String folder, String name, long seed, String type, String generator, String gameMode,
		boolean cheats, boolean structures) throws Exception {
		Minecraft mc = Minecraft.getInstance();
		LevelSettings settings = new LevelSettings(name, GameType.byName(gameMode),
			new LevelSettings.DifficultySettings(Difficulty.NORMAL, false, false), cheats, WorldDataConfiguration.DEFAULT);
		WorldOptions options = new WorldOptions(seed, structures, false);
		AtomicReference<ProbeException> refused = new AtomicReference<>();
		mc.createWorldOpenFlows().createFreshLevel(folder, settings, options,
			registries -> dimensions(registries, type, generator, refused), mc.gui.screen());
		if (refused.get() != null) {
			throw refused.get();
		}
		if (mc.getSingleplayerServer() == null) {
			throw new IllegalStateException("the game didn't make " + folder + " (its log says why)");
		}
	}

	/** The world's dimensions, from its type's preset; a flat world with layers of its own gets those. */
	private static WorldDimensions dimensions(HolderLookup.Provider registries, String type, String generator,
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
			problem = "26.3 can't read the layers " + parts[0];
		} else if (parts.length == 2 && !made.getBiome().is(ResourceKey.create(Registries.BIOME, Identifier.parse(parts[1])))) {
			problem = "26.3 has no biome " + parts[1];
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
				throw new IllegalArgumentException("26.3 has no world type " + type);
		}
	}

	/** Opens a save as the world list's Play does; a screen the game asks first on (a backup, say) stays up. */
	@Override
	public void open(String folder) {
		Minecraft.getInstance().createWorldOpenFlows().openWorld(folder, () -> { });
	}

	/** Saves and leaves, as the pause menu's Save and Quit: the game waits here until the integrated server stopped. */
	@Override
	public void close() {
		Minecraft mc = Minecraft.getInstance();
		if (mc.level != null) {
			mc.disconnectFromWorld(ClientLevel.DEFAULT_QUIT_MESSAGE);
		}
	}

	@Override
	public void picture(java.io.File file) throws Exception {
		throw new UnsupportedOperationException("26.3's pictures come with a later step");
	}

	/** 26.3 keeps no trace of a world loading for the probe (debug.trace is empty). */
	@Override
	public void traceStart() {
		ModernTrace.start();
	}

	@Override
	public void traceStop() {
		ModernTrace.stop();
	}

	/** 26.3's client has no difficulty option of its own: it shows the server's. */
	@Override
	public void clientDifficulty(String difficulty) {
	}
}

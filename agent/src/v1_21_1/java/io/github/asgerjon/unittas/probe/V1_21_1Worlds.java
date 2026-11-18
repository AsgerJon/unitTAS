package io.github.asgerjon.unittas.probe;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.GenericMessageScreen;
import net.minecraft.client.gui.screens.PresetFlatWorldScreen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.core.Holder;
import net.minecraft.core.HolderGetter;
import net.minecraft.core.HolderSet;
import net.minecraft.core.RegistryAccess;
import net.minecraft.core.registries.Registries;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.Difficulty;
import net.minecraft.world.level.GameRules;
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
 * The world operations' game calls in 1.21.1 (GameWorlds, for the core's WorldOps; SPEC.md 19.7 step 6c), as 26.3's
 * (V26Worlds) each as the game's own screen or command does it: made as createFreshLevel makes it, opened as the
 * world list's Play, left as the pause menu's Save and Quit; the rules, the time, the weather and the difficulty as
 * /gamerule, /time set, /weather and /difficulty set them. Where 1.21.1 differs from 26.3: its rules are named in
 * camel case (doDaylightCycle) and are booleans or numbers; its time and weather are the overworld's (a level's own
 * data, the other dimensions following it), not clocks; fire's spread is a rule of its own (doFireTick).
 */
final class V1_21_1Worlds extends V1_21_1ServerWorlds {

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
		} else if (parts.length == 2 && !made.getBiome().is(VersionCommon.key(Registries.BIOME, parts[1]))) {
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
}

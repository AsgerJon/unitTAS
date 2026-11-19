package io.github.asgerjon.unittas.probe;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.GenericDirtMessageScreen;
import net.minecraft.client.gui.screens.PresetFlatWorldScreen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.client.gui.screens.worldselection.WorldPreset;
import net.minecraft.core.Registry;
import net.minecraft.core.RegistryAccess;
import net.minecraft.network.chat.TranslatableComponent;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.Difficulty;
import net.minecraft.world.level.DataPackConfig;
import net.minecraft.world.level.GameRules;
import net.minecraft.world.level.GameType;
import net.minecraft.world.level.LevelSettings;
import net.minecraft.world.level.levelgen.FlatLevelSource;
import net.minecraft.world.level.levelgen.StructureSettings;
import net.minecraft.world.level.levelgen.WorldGenSettings;
import net.minecraft.world.level.levelgen.flat.FlatLevelGeneratorSettings;

import java.util.Collections;
import java.util.Optional;

/**
 * The world operations' game calls in 1.16.1 (GameWorlds, for the core's WorldOps; SPEC.md 19.7 step 11c), as 1.20.1's
 * (V1_20_1Worlds) each as the game's own screen or command does it: made as the Create New World screen makes it
 * (Minecraft.createLevel, its world type a WorldPreset, a flat world's layers as its Customize screen reads them),
 * opened as the world list's Play (loadLevel), left as the pause menu's Save and Quit; the rules, the time, the weather
 * and the difficulty as /gamerule, /time set, /weather and /difficulty set them. 1.16.1's rules are named in camel
 * case and are booleans or numbers; its time and weather are the overworld's; fire's spread is a rule of its own.
 */
final class V1_16_1Worlds extends V1_16_1ServerWorlds {

	/** The world types the Create New World screen offers by name that 1.16.1 keeps private: found once, by name. */
	private static final class Presets {

		static final java.lang.reflect.Field FLAT = Members.field(WorldPreset.class, "FLAT");
		static final java.lang.reflect.Field LARGE_BIOMES = Members.field(WorldPreset.class, "LARGE_BIOMES");
	}

	// ---------------------------------------------------------------- the client thread

	/**
	 * Makes and opens a world as the Create New World screen does (Normal, not hardcore, the default rules and data
	 * packs, the built-in registries; no bonus chest). It returns once the integrated server is ready (1.16.1's
	 * createLevel waits for it); layers or a biome 1.16.1 can't read are BadRequest, said before anything is made.
	 */
	@Override
	public void create(String folder, String name, long seed, String type, String generator, String gameMode,
		boolean cheats, boolean structures) throws Exception {
		Minecraft mc = Minecraft.getInstance();
		LevelSettings settings = new LevelSettings(name, GameType.byName(gameMode), false, Difficulty.NORMAL, cheats,
			new GameRules(), DataPackConfig.DEFAULT);
		RegistryAccess.RegistryHolder registries = RegistryAccess.builtin();
		WorldGenSettings made = preset(type).create(registries, seed, structures, false);
		if ("flat".equals(type) && !generator.isEmpty()) {
			made = made.withDimensions(
				WorldGenSettings.withOverworld(made.dimensions(), new FlatLevelSource(flat(generator))));
		}
		mc.createLevel(folder, settings, registries, made);
		if (mc.getSingleplayerServer() == null) {
			throw new IllegalStateException("the game didn't make " + folder + " (its log says why)");
		}
	}

	/**
	 * A flat world's settings from its layers, as the Customize screen reads them (PresetFlatWorldScreen.fromString),
	 * on a base with no structures (the layers name none, as 1.7.10's test layers don't). BadRequest where 1.16.1
	 * can't read the layers (fromString gives its classic flat world then: another base than the one given) or hasn't
	 * the biome.
	 */
	private static FlatLevelGeneratorSettings flat(String generator) throws ProbeException {
		StructureSettings none = new StructureSettings(Optional.empty(), Collections.emptyMap());
		FlatLevelGeneratorSettings made = PresetFlatWorldScreen.fromString(generator,
			new FlatLevelGeneratorSettings(none));
		String[] parts = generator.split(";", -1);
		if (made.structureSettings() != none) {
			throw ProbeException.badRequest("generator", "1.16.1 can't read the layers " + parts[0]);
		}
		if (parts.length == 2 && !Registry.BIOME.getKey(made.getBiome()).equals(ResourceLocation.tryParse(parts[1]))) {
			throw ProbeException.badRequest("generator", "1.16.1 has no biome " + parts[1]);
		}
		return made;
	}

	/** The Create New World screen's world type by its name. */
	private static WorldPreset preset(String type) {
		switch (type) {
			case "default":
				return WorldPreset.NORMAL;
			case "flat":
				return Members.get(Presets.FLAT, null);
			case "large_biomes":
				return Members.get(Presets.LARGE_BIOMES, null);
			case "amplified":
				return WorldPreset.AMPLIFIED;
			default:
				throw new IllegalArgumentException("1.16.1 has no world type " + type);
		}
	}

	/**
	 * Opens a save as the world list's Play does (1.16.1's Minecraft.loadLevel); a screen the game asks first on (a
	 * backup, say) stays up.
	 */
	@Override
	public void open(String folder) {
		Minecraft.getInstance().loadLevel(folder);
	}

	/**
	 * Saves and leaves, as 1.16.1's pause menu's Save and Quit: the level disconnected, then cleared (clearLevel, which
	 * waits here until the integrated server stopped, behind the "Saving world" screen); then the title screen, as the
	 * pause menu opens it after.
	 */
	@Override
	public void close() {
		Minecraft mc = Minecraft.getInstance();
		if (mc.level != null) {
			mc.level.disconnect();
			mc.clearLevel(new GenericDirtMessageScreen(new TranslatableComponent("menu.savingLevel")));
			mc.setScreen(new TitleScreen());
		}
	}

	@Override
	public void picture(java.io.File file) throws Exception {
		throw new UnsupportedOperationException("1.16.1's pictures come with a later step");
	}

	/** 1.16.1 keeps no trace of a world loading for the probe (debug.trace is empty). */
	@Override
	public void traceStart() {
		ModernTrace.start();
	}

	@Override
	public void traceStop() {
		ModernTrace.stop();
	}

	/** 1.16.1's client has no difficulty option of its own: it shows the server's. */
	@Override
	public void clientDifficulty(String difficulty) {
	}
}

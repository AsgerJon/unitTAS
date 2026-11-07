package io.github.asgerjon.unittas.probe;

import net.fabricmc.loader.api.FabricLoader;
import net.fabricmc.loader.api.ModContainer;

import java.util.Collections;
import java.util.List;

/**
 * The 26.3 Fabric port (SPEC.md 12, D5): what this version and loader give the probe's version-free core. Its facts
 * come from Fabric Loader's own mod containers (Minecraft's, the loader's, the probe's), not from constants, so the
 * hello says what really runs. Its game operations come with phase 4's steps 3 to 7; until then a game operation is
 * Unsupported.
 */
public final class FabricPort implements Port {

	@Override
	public String name() {
		return "26.3-fabric";
	}

	@Override
	public String minecraft() {
		return version("minecraft");
	}

	@Override
	public String loaderName() {
		return "fabric";
	}

	@Override
	public String loaderVersion() {
		return version("fabricloader");
	}

	@Override
	public String names() {
		// 26.x is unobfuscated: the game names its members as Mojang does
		return "mojang";
	}

	@Override
	public boolean development() {
		return FabricLoader.getInstance().isDevelopmentEnvironment();
	}

	@Override
	public String probeVersion() {
		return version("unittas");
	}

	@Override
	public void beforeWake() {
	}

	@Override
	public void woken(Probe probe) {
	}

	@Override
	public List<String> trace() {
		return Collections.emptyList();
	}

	@Override
	public void declare(Probe probe) {
	}

	/** A mod's version as Fabric Loader has it, or "" for one it hasn't. */
	private static String version(String mod) {
		return FabricLoader.getInstance().getModContainer(mod).map(ModContainer::getMetadata)
			.map(metadata -> metadata.getVersion().getFriendlyString()).orElse("");
	}
}

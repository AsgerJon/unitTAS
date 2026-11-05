package io.github.asgerjon.unittas.core;

import cpw.mods.fml.relauncher.IFMLLoadingPlugin;
import io.github.asgerjon.unittas.probe.Probe;
import net.minecraft.launchwrapper.Launch;

import java.io.File;
import java.util.Map;

/**
 * Hands unitTAS's mixins (mixins.unittas.json) to Mixin. Mixin itself is started by the game's Mixin loader
 * (UniMixins' MixinTweaker), never here. The jar's manifest names this class (FMLCorePlugin) and says the jar holds a
 * mod as well (FMLCorePluginContainsFMLMod: true).
 *
 * When matters. From a jar in mods/ (a real game), FML makes the coremods before UniMixins' tweaker has started Mixin,
 * so the constructor is too early: touched then, Mixin's classes would land in the wrong class loader and the game stops
 * (in UniMixins' own coremod). {@link #injectData} is late enough everywhere: LaunchWrapper makes every tweaker of a
 * round (the MixinTweaker among them, which starts Mixin as it is made) before it calls any of them, and FML hands a
 * coremod its data from such a call. In a development run the tweaker is on the command line, earlier still. Even so,
 * the one Mixin call is in another class, {@link UnitTasMixins}, loaded only when it is made.
 */
@IFMLLoadingPlugin.Name("unitTAS")
@IFMLLoadingPlugin.MCVersion("1.7.10")
@IFMLLoadingPlugin.TransformerExclusions("io.github.asgerjon.unittas.core")
public final class UnitTasLoadingPlugin implements IFMLLoadingPlugin {

	static final String CONFIG = "mixins.unittas.json";
	/** Mixin's key on LaunchWrapper's blackboard (GlobalProperties.Keys.INIT): set once Mixin has started. */
	private static final String MIXIN_STARTED = "mixin.initialised";

	@Override
	public String[] getASMTransformerClass() {
		return new String[0];
	}

	@Override
	public String getModContainerClass() {
		return null;
	}

	@Override
	public String getSetupClass() {
		return null;
	}

	@Override
	public void injectData(Map<String, Object> data) {
		if (Launch.blackboard == null || Launch.blackboard.get(MIXIN_STARTED) == null) {
			throw new IllegalStateException("unitTAS's mixins can't be loaded: Mixin hasn't started. Is a Mixin loader"
				+ " (UniMixins) in the game?");
		}
		UnitTasMixins.addConfig();
		// the probe, if an orchestrator left its start file (PROTOCOL.md 2.1): before any mod loads, so it hears them load
		Object gameDir = data.get("mcLocation");
		Probe.early(gameDir instanceof File ? (File) gameDir : null, Boolean.TRUE.equals(data.get("runtimeDeobfuscationEnabled")));
	}

	@Override
	public String getAccessTransformerClass() {
		return null;
	}
}

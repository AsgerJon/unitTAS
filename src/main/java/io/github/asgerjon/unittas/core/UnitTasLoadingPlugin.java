package io.github.asgerjon.unittas.core;

import cpw.mods.fml.relauncher.IFMLLoadingPlugin;
import org.spongepowered.asm.mixin.Mixins;

import java.util.Map;

/**
 * Hands unitTAS's mixins (mixins.unittas.json) to Mixin as the game starts. Mixin itself is started by the game's
 * Mixin loader (UniMixins: its MixinTweaker, which runs before any coremod, on the class loader Mixin needs), never
 * here: started from a coremod, Mixin's classes end up in two class loaders and the game stops with a LinkageError.
 * The jar's manifest names this class (FMLCorePlugin) and says the jar holds a mod as well
 * (FMLCorePluginContainsFMLMod: true); a development run names it in -Dfml.coreMods.load.
 */
@IFMLLoadingPlugin.Name("unitTAS")
@IFMLLoadingPlugin.MCVersion("1.7.10")
@IFMLLoadingPlugin.TransformerExclusions("io.github.asgerjon.unittas.core")
public final class UnitTasLoadingPlugin implements IFMLLoadingPlugin {

	public UnitTasLoadingPlugin() {
		Mixins.addConfiguration("mixins.unittas.json");
	}

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
	}

	@Override
	public String getAccessTransformerClass() {
		return null;
	}
}

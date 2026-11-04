package io.github.asgerjon.unittas.core;

import org.spongepowered.asm.mixin.Mixins;

/**
 * The one class of the coremod's that touches Mixin, loaded only once Mixin has started (see
 * {@link UnitTasLoadingPlugin}): a Mixin class loaded any earlier lands in the wrong class loader.
 */
final class UnitTasMixins {

	private UnitTasMixins() {
	}

	/** Adds mixins.unittas.json (added twice, it's the one config: Mixin keeps them by name). */
	static void addConfig() {
		Mixins.addConfiguration(UnitTasLoadingPlugin.CONFIG);
	}
}

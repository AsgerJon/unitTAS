package io.github.asgerjon.unittas.mixins.fabric;

import net.minecraft.client.SectionUpdateTracker;
import net.minecraft.client.renderer.extract.LevelExtractor;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

/** The sections 26.3 knows changed and has yet to build again (view.block waits for a block's own). */
@Mixin(LevelExtractor.class)
public interface LevelExtractorAccess {

	@Accessor("sectionUpdateTracker")
	SectionUpdateTracker unittas$sectionUpdateTracker();
}

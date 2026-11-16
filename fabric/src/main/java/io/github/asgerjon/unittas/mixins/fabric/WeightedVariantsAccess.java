package io.github.asgerjon.unittas.mixins.fabric;

import net.minecraft.client.renderer.block.dispatch.BlockStateModel;
import net.minecraft.client.renderer.block.dispatch.WeightedVariants;
import net.minecraft.util.random.WeightedList;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

/** The models a block state is drawn with at random (stone, plain or mirrored), each a look block.faces gives. */
@Mixin(WeightedVariants.class)
public interface WeightedVariantsAccess {

	@Accessor("list")
	WeightedList<BlockStateModel> unittas$list();
}

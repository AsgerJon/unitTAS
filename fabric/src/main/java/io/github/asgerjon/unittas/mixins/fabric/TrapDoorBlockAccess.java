package io.github.asgerjon.unittas.mixins.fabric;

import net.minecraft.world.level.block.TrapDoorBlock;
import net.minecraft.world.level.block.state.properties.BlockSetType;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

/** A trapdoor's kind (protected in 26.3), which says whether a hand opens it, for player.perceive. */
@Mixin(TrapDoorBlock.class)
public interface TrapDoorBlockAccess {

	@Invoker("getType")
	BlockSetType unittas$type();
}

package io.github.asgerjon.unittas.mixins.fabric;

import net.minecraft.client.Minecraft;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

/** The game's own pick of what the crosshair meets (Minecraft.pick, private in 26.3), made afresh for player.perceive. */
@Mixin(Minecraft.class)
public interface MinecraftAccess {

	@Invoker("pick")
	void unittas$pick(float partialTicks);
}

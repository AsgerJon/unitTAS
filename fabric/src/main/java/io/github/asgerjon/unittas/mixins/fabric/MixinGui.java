package io.github.asgerjon.unittas.mixins.fabric;

import io.github.asgerjon.unittas.probe.FabricHooks;
import net.minecraft.client.gui.Gui;
import net.minecraft.client.gui.screens.Screen;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** The client's screen changes: in 26.3 the screen is Gui's (Gui.setScreen), not Minecraft's. */
@Mixin(Gui.class)
public abstract class MixinGui {

	@Shadow
	public abstract Screen screen();

	@Inject(method = "setScreen", at = @At("HEAD"))
	private void unittas$screen(Screen to, CallbackInfo info) {
		FabricHooks.screen(screen(), to);
	}
}

package io.github.asgerjon.unittas.mixins.fabric;

import io.github.asgerjon.unittas.probe.FabricClient;
import net.minecraft.client.Minecraft;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** The end of Minecraft's constructor: the probe dials from here, as the 1.7.10 probe's MixinMinecraft does. */
@Mixin(Minecraft.class)
public abstract class MixinMinecraft {

	@Inject(method = "<init>", at = @At("RETURN"))
	private void unittas$launched(CallbackInfo info) {
		FabricClient.launched((Minecraft) (Object) this);
	}
}

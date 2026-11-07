package io.github.asgerjon.unittas.mixins.fabric;

import io.github.asgerjon.unittas.probe.FabricClient;
import io.github.asgerjon.unittas.probe.FabricHooks;
import net.minecraft.client.Minecraft;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * The end of Minecraft's constructor: the probe dials from here, as the 1.7.10 probe's MixinMinecraft does. The
 * client's tick, its start and its end, for the probe's hooks (FabricHooks). And the window's title: unitTAS while the
 * probe is awake (PROTOCOL.md 2.5), whenever the game makes its title (updateTitle sets what createTitle gives).
 */
@Mixin(Minecraft.class)
public abstract class MixinMinecraft {

	@Inject(method = "<init>", at = @At("RETURN"))
	private void unittas$launched(CallbackInfo info) {
		FabricClient.launched((Minecraft) (Object) this);
	}

	@Inject(method = "tick", at = @At("HEAD"))
	private void unittas$tickStart(CallbackInfo info) {
		FabricHooks.clientTickStart();
	}

	@Inject(method = "tick", at = @At("TAIL"))
	private void unittas$tickEnd(CallbackInfo info) {
		FabricHooks.clientTickEnd((Minecraft) (Object) this);
	}

	@Inject(method = "createTitle", at = @At("HEAD"), cancellable = true)
	private void unittas$title(CallbackInfoReturnable<String> info) {
		String title = FabricHooks.title();
		if (title != null) {
			info.setReturnValue(title);
		}
	}
}

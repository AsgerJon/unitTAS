package io.github.asgerjon.unittas.mixins.server;

import io.github.asgerjon.unittas.probe.Probe;
import net.minecraft.server.dedicated.DedicatedServer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * An orchestrator's probe in a dedicated server dials once the server is made (SPEC.md 11.3, step 2): as with the
 * client's Minecraft, LaunchWrapper is done adding class transformers by then, so no class of the probe's thread is
 * loaded while that list still changes. Applied on a dedicated server only (the config's "server" list).
 */
@Mixin(DedicatedServer.class)
public abstract class MixinDedicatedServer {

	@Inject(method = "<init>", at = @At("RETURN"))
	private void unittas$launched(CallbackInfo info) {
		Probe.launched(null);
	}
}

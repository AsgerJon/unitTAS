package io.github.asgerjon.unittas.mixins.server;

import io.github.asgerjon.unittas.probe.Opening;
import net.minecraft.network.NetworkSystem;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

import java.util.List;

/**
 * debug.drop_login on a dedicated server (the join guard's tests, SPEC.md 11.3 step 3): a connection dropped as soon
 * as the server's network tick lists it, as 1.7.10's race drops one whose channel isn't set yet, silently. The client
 * then waits at its connecting screen for an answer that never comes. Nothing else changes: without debug.drop_login
 * this does nothing at all.
 */
@Mixin(NetworkSystem.class)
public abstract class MixinNetworkSystemDrop {

	@Shadow
	@Final
	private List networkManagers;

	@Inject(method = "networkTick", at = @At("HEAD"), require = 0)
	private void unittas$dropLogin(CallbackInfo ci) {
		if (Opening.DROP_LOGINS.get() > 0) {
			synchronized (networkManagers) {
				if (!networkManagers.isEmpty() && Opening.dropNextLogin()) {
					networkManagers.remove(0);
				}
			}
		}
	}
}

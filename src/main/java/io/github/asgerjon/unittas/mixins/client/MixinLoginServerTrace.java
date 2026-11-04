package io.github.asgerjon.unittas.mixins.client;

import io.github.asgerjon.unittas.TasTrace;
import net.minecraft.network.login.client.C00PacketLoginStart;
import net.minecraft.server.network.NetHandlerLoginServer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** unitTAS's loading trace (TasTrace): the server's login. */
@Mixin(NetHandlerLoginServer.class)
public abstract class MixinLoginServerTrace {
	@Inject(method = "processLoginStart", at = @At("HEAD"), require = 0)
	private void unittas$loginStart(C00PacketLoginStart packet, CallbackInfo ci) {
		if (TasTrace.recording()) {
			TasTrace.note("server login start");
		}
	}

	@Inject(method = "func_147326_c", at = @At("HEAD"), require = 0)
	private void unittas$accept(CallbackInfo ci) {
		if (TasTrace.recording()) {
			TasTrace.note("server accepts the login (the FML handshake starts here)");
		}
	}
}

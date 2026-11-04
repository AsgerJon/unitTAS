package io.github.asgerjon.unittas.mixins.client;

import io.github.asgerjon.unittas.TasTrace;
import net.minecraft.client.network.NetHandlerLoginClient;
import net.minecraft.network.login.server.S02PacketLoginSuccess;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** unitTAS's loading trace (TasTrace): the client's login. */
@Mixin(NetHandlerLoginClient.class)
public abstract class MixinLoginClientTrace {
	@Inject(method = "handleLoginSuccess", at = @At("HEAD"), require = 0)
	private void unittas$loginSuccess(S02PacketLoginSuccess packet, CallbackInfo ci) {
		if (TasTrace.recording()) {
			TasTrace.note("client login success");
		}
	}
}

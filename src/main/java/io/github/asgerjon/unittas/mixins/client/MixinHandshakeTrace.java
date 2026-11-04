package io.github.asgerjon.unittas.mixins.client;

import io.github.asgerjon.unittas.TasTrace;
import net.minecraft.network.handshake.client.C00Handshake;
import net.minecraft.client.network.NetHandlerHandshakeMemory;
import net.minecraft.server.network.NetHandlerHandshakeTCP;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** unitTAS's loading trace (TasTrace): the server's handshake (a local connection's is NetHandlerHandshakeMemory). */
@Mixin({NetHandlerHandshakeTCP.class, NetHandlerHandshakeMemory.class})
public abstract class MixinHandshakeTrace {
	@Inject(method = "processHandshake", at = @At("HEAD"), require = 0)
	private void unittas$handshake(C00Handshake packet, CallbackInfo ci) {
		if (TasTrace.recording()) {
			TasTrace.note("server handshake: to " + packet.getRequestedState());
		}
	}
}

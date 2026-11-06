package io.github.asgerjon.unittas.mixins.client;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import com.llamalad7.mixinextras.sugar.Local;
import io.github.asgerjon.unittas.ITracedConnection;
import io.github.asgerjon.unittas.TasTrace;
import io.github.asgerjon.unittas.probe.Opening;
import net.minecraft.network.NetworkManager;
import net.minecraft.network.NetworkSystem;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

import java.net.SocketAddress;
import java.util.Iterator;
import java.util.List;

/**
 * unitTAS's loading trace (TasTrace): the server's local endpoint, the connections its tick lists (each by name the
 * first time, with its channel's state), and any it drops, with why.
 */
@Mixin(NetworkSystem.class)
public abstract class MixinNetworkSystemTrace {

	@Shadow
	@Final
	private List networkManagers;

	@Unique
	private int unittas$listed = -1;

	@Inject(method = "addLocalEndpoint", at = @At("RETURN"), require = 0)
	private void unittas$endpoint(CallbackInfoReturnable<SocketAddress> cir) {
		if (TasTrace.recording()) {
			TasTrace.note("the server's local endpoint is bound: " + cir.getReturnValue());
		}
	}

	@Inject(method = "networkTick", at = @At("HEAD"), require = 0)
	private void unittas$tick(CallbackInfo ci) {
		// debug.drop_login (the opening guard's tests): a connection dropped as soon as it is listed, as 1.7.10's login
		// race drops one whose channel isn't set yet, silently; the client then waits at its login for ever
		if (Opening.DROP_LOGINS.get() > 0) {
			synchronized (networkManagers) {
				if (!networkManagers.isEmpty() && Opening.dropNextLogin()) {
					Object dropped = networkManagers.remove(0);
					TasTrace.note("debug.drop_login DROPS connection " + ITracedConnection.describe(dropped));
				}
			}
		}
		if (TasTrace.recording()) {
			TasTrace.noteOnce("server tick", "the server's network tick runs");
			int listed = networkManagers.size();
			if (listed != unittas$listed) {
				unittas$listed = listed;
				TasTrace.note("the server's tick lists " + listed + " connection" + (listed == 1 ? "" : "s"));
			}
			synchronized (networkManagers) {
				for (Object manager : networkManagers) {
					TasTrace.noteOnce("seen " + System.identityHashCode(manager), "the server's tick sees connection " + ITracedConnection.describe(manager));
				}
			}
		}
	}

	@WrapOperation(method = "networkTick", at = @At(value = "INVOKE", target = "Ljava/util/Iterator;remove()V"), require = 0)
	private void unittas$drop(Iterator<?> iterator, Operation<Void> original, @Local NetworkManager manager) {
		if (TasTrace.recording()) {
			TasTrace.note("the server's tick DROPS connection " + ITracedConnection.describe(manager) + " (exit message: " + manager.getExitMessage() + ")");
		}
		original.call(iterator);
	}
}

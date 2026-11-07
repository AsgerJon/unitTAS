package io.github.asgerjon.unittas.mixins.fabric;

import io.github.asgerjon.unittas.probe.FabricHooks;
import net.minecraft.server.MinecraftServer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

import java.util.function.BooleanSupplier;

/** The integrated server's tick, its start and its end, for the probe's hooks (FabricHooks). */
@Mixin(MinecraftServer.class)
public abstract class MixinMinecraftServer {

	@Inject(method = "tickServer", at = @At("HEAD"))
	private void unittas$tickStart(BooleanSupplier hasTimeLeft, CallbackInfo info) {
		FabricHooks.serverTickStart();
	}

	@Inject(method = "tickServer", at = @At("TAIL"))
	private void unittas$tickEnd(BooleanSupplier hasTimeLeft, CallbackInfo info) {
		FabricHooks.serverTickEnd();
	}
}

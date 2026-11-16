package io.github.asgerjon.unittas.mixins.fabric;

import io.github.asgerjon.unittas.probe.FabricHooks;
import net.minecraft.client.Minecraft;
import net.minecraft.client.MouseHandler;
import net.minecraft.client.input.MouseButtonInfo;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

import java.util.List;

/**
 * While the probe is awake (PROTOCOL.md 2.5): the game never grabs the mouse pointer, the real mouse's buttons, moves,
 * scrolls and drops are dropped before the game reads them, and the mouse counts as grabbed while a world is open and no
 * screen is (the game counts as focused then, as holding the attack key to mine needs).
 */
@Mixin(MouseHandler.class)
public abstract class MixinMouseHandler {

	@Inject(method = "grabMouse", at = @At("HEAD"), cancellable = true)
	private void unittas$leavePointerFree(CallbackInfo info) {
		if (FabricHooks.awake()) {
			info.cancel();
		}
	}

	@Inject(method = "onButton", at = @At("HEAD"), cancellable = true)
	private void unittas$noRealClicks(long window, MouseButtonInfo button, int action, CallbackInfo info) {
		if (FabricHooks.awake()) {
			info.cancel();
		}
	}

	@Inject(method = "onMove", at = @At("HEAD"), cancellable = true)
	private void unittas$noRealLooking(long window, double x, double y, double dx, double dy, CallbackInfo info) {
		if (FabricHooks.awake()) {
			info.cancel();
		}
	}

	@Inject(method = "onScroll", at = @At("HEAD"), cancellable = true)
	private void unittas$noRealScrolling(long window, double x, double y, CallbackInfo info) {
		if (FabricHooks.awake()) {
			info.cancel();
		}
	}

	@Inject(method = "onDrop", at = @At("HEAD"), cancellable = true)
	private void unittas$noRealDrops(long window, List<String> files, CallbackInfo info) {
		if (FabricHooks.awake()) {
			info.cancel();
		}
	}

	@Inject(method = "isMouseGrabbed", at = @At("HEAD"), cancellable = true)
	private void unittas$focusedInWorld(CallbackInfoReturnable<Boolean> info) {
		Minecraft mc = Minecraft.getInstance();
		if (FabricHooks.awake() && mc.level != null && mc.gui.screen() == null) {
			info.setReturnValue(true);
		}
	}
}

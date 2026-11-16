package io.github.asgerjon.unittas.mixins.fabric;

import io.github.asgerjon.unittas.probe.FabricHooks;
import net.minecraft.client.KeyboardHandler;
import net.minecraft.client.input.CharacterEvent;
import net.minecraft.client.input.KeyEvent;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * While the probe is awake (PROTOCOL.md 2.5): the real keyboard's keys, characters and text are dropped before the game
 * reads them. The tests' own keys go to the key bindings and the screens directly (FabricInput), not through here.
 */
@Mixin(KeyboardHandler.class)
public abstract class MixinKeyboardHandler {

	@Inject(method = "keyPress", at = @At("HEAD"), cancellable = true)
	private void unittas$noRealKeys(long window, int action, KeyEvent event, CallbackInfo info) {
		if (FabricHooks.awake()) {
			info.cancel();
		}
	}

	@Inject(method = "charTyped", at = @At("HEAD"), cancellable = true)
	private void unittas$noRealTyping(long window, CharacterEvent event, CallbackInfo info) {
		if (FabricHooks.awake()) {
			info.cancel();
		}
	}

	@Inject(method = "textInput", at = @At("HEAD"), cancellable = true)
	private void unittas$noRealText(long window, String text, CallbackInfo info) {
		if (FabricHooks.awake()) {
			info.cancel();
		}
	}
}

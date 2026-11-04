package io.github.asgerjon.unittas.mixins.client;

import io.github.asgerjon.unittas.UnitTasMode;
import net.minecraft.client.audio.ISound;
import net.minecraft.client.audio.SoundEventAccessorComposite;
import net.minecraft.client.audio.SoundHandler;
import net.minecraft.util.ResourceLocation;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * During a unitTAS run, every sound the client is asked to play, by name, for tests to check; one the game doesn't
 * have (no sound event by that name, which plays nothing without a word) goes to the unknown list instead. Here rather
 * than at Forge's PlaySoundEvent17, which isn't fired with the master volume at zero (a muted test window still hears).
 */
@Mixin(SoundHandler.class)
public abstract class MixinSoundHandler {

	@Shadow
	public abstract SoundEventAccessorComposite getSound(ResourceLocation location);

	@Inject(method = "playSound", at = @At("HEAD"))
	private void unittas$heard(ISound sound, CallbackInfo ci) {
		if (UnitTasMode.running && sound != null) {
			ResourceLocation location = sound.getSoundLocation();
			if (location.toString().equals("minecraft:none") || location.getResourcePath().isEmpty()) {
				// 1.7.10's golems name the sounds they don't have "none" (EntityGolem), and a wild ocelot's ambient
				// sound is "" (EntityOcelot.getLivingSound): no sound, on purpose
				return;
			}
			if (getSound(location) != null) {
				UnitTasMode.SOUNDS_HEARD.add(location.toString());
			} else {
				UnitTasMode.SOUNDS_UNKNOWN.add(location.toString());
				UnitTasMode.SOUNDS_UNKNOWN_FROM.add(location + " from " + unittas$caller());
			}
		}
	}

	/** The first few calls outside the sound system and this mixin, to say who asked for a sound. */
	@Unique
	private static String unittas$caller() {
		StringBuilder calls = new StringBuilder();
		int shown = 0;
		for (StackTraceElement frame : Thread.currentThread().getStackTrace()) {
			String owner = frame.getClassName();
			if (owner.startsWith("java.") || owner.startsWith("net.minecraft.client.audio.") || owner.contains("MixinSoundHandler")) {
				continue;
			}
			calls.append(shown == 0 ? "" : " < ").append(owner.substring(owner.lastIndexOf('.') + 1)).append('.').append(frame.getMethodName())
				.append(':').append(frame.getLineNumber());
			if (++shown == 5) {
				break;
			}
		}
		return calls.toString();
	}
}

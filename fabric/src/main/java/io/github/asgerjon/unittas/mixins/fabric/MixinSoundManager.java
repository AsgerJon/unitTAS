package io.github.asgerjon.unittas.mixins.fabric;

import io.github.asgerjon.unittas.probe.FabricSounds;
import net.minecraft.client.resources.sounds.SoundInstance;
import net.minecraft.client.sounds.SoundEngine;
import net.minecraft.client.sounds.SoundManager;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * Every sound the client is asked to play, before the engine has it: here rather than in the engine, which plays
 * nothing (and says nothing) at a volume of zero, so a muted test window still hears.
 */
@Mixin(SoundManager.class)
public abstract class MixinSoundManager {

	@Inject(method = "play", at = @At("HEAD"))
	private void unittas$heard(SoundInstance sound, CallbackInfoReturnable<SoundEngine.PlayResult> info) {
		FabricSounds.heard((SoundManager) (Object) this, sound);
	}
}

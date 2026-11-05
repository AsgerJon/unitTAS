package io.github.asgerjon.unittas.mixins.client;

import io.github.asgerjon.unittas.UnitTasMode;
import io.github.asgerjon.unittas.probe.Probe;
import net.minecraft.client.Minecraft;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.ModifyArg;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

import java.io.File;

/**
 * A unitTAS run's window has its own title, set before the window opens so that window rules can match it. And an
 * orchestrator's probe dials once Minecraft is made: LaunchWrapper is done adding class transformers by then.
 */
@Mixin(Minecraft.class)
public abstract class MixinMinecraft {

	@Shadow
	@Final
	public File mcDataDir;

	@Inject(method = "<init>", at = @At("RETURN"))
	private void unittas$launched(CallbackInfo info) {
		Probe.launched(null);
	}

	@ModifyArg(method = "startGame", at = @At(value = "INVOKE", target = "Lorg/lwjgl/opengl/Display;setTitle(Ljava/lang/String;)V", remap = false))
	private String unittas$unitTasTitle(String title) {
		return UnitTasMode.requested(mcDataDir) || Probe.active() ? UnitTasMode.WINDOW_TITLE : title;
	}
}

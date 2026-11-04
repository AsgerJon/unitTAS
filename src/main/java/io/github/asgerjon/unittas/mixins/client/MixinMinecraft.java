package io.github.asgerjon.unittas.mixins.client;

import io.github.asgerjon.unittas.UnitTasMode;
import net.minecraft.client.Minecraft;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyArg;

import java.io.File;

/** A unitTAS run's window has its own title, set before the window opens so that window rules can match it. */
@Mixin(Minecraft.class)
public abstract class MixinMinecraft {

	@Shadow
	@Final
	public File mcDataDir;

	@ModifyArg(method = "startGame", at = @At(value = "INVOKE", target = "Lorg/lwjgl/opengl/Display;setTitle(Ljava/lang/String;)V", remap = false))
	private String unittas$unitTasTitle(String title) {
		return UnitTasMode.requested(mcDataDir) ? UnitTasMode.WINDOW_TITLE : title;
	}
}

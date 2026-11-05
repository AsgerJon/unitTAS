package io.github.asgerjon.unittas.mixins.client;

import io.github.asgerjon.unittas.UnitTasMode;
import io.github.asgerjon.unittas.probe.Probe;
import net.minecraft.client.Minecraft;
import net.minecraft.crash.CrashReport;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.ModifyArg;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

import java.io.File;

/**
 * A unitTAS run's window has its own title, set before the window opens so that window rules can match it. An
 * orchestrator's probe dials once Minecraft is made: LaunchWrapper is done adding class transformers by then. And a
 * crash is told to the orchestrator before the game exits.
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

	/**
	 * The game is crashing: its crash report is printed and saved, and FML's handleExit is about to end the JVM. The
	 * probe says so first (Probe.crashed), with the report's file (null if it couldn't be saved) and what it says.
	 */
	@Inject(method = "displayCrashReport", at = @At(value = "INVOKE", target = "Lcpw/mods/fml/common/FMLCommonHandler;handleExit(I)V", remap = false))
	private void unittas$crashed(CrashReport report, CallbackInfo info) {
		Probe.crashed(report.getFile(), report.getDescription(), report.getCrashCause());
	}

	@ModifyArg(method = "startGame", at = @At(value = "INVOKE", target = "Lorg/lwjgl/opengl/Display;setTitle(Ljava/lang/String;)V", remap = false))
	private String unittas$unitTasTitle(String title) {
		return UnitTasMode.requested(mcDataDir) || Probe.active() ? UnitTasMode.WINDOW_TITLE : title;
	}
}

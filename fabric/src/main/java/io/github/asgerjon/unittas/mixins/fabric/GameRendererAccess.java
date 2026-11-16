package io.github.asgerjon.unittas.mixins.fabric;

import com.mojang.blaze3d.vertex.PoseStack;
import net.minecraft.client.renderer.GameRenderer;
import net.minecraft.client.renderer.state.level.CameraRenderState;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

/**
 * The tilt a hurt player's view takes and the view's bobbing (GameRenderer's private bobHurt and bobView), which 26.3
 * puts on the level's projection as it draws a frame: view.block's camera is the frame's own, with them.
 */
@Mixin(GameRenderer.class)
public interface GameRendererAccess {

	@Invoker("bobHurt")
	void unittas$bobHurt(CameraRenderState camera, PoseStack pose);

	@Invoker("bobView")
	void unittas$bobView(CameraRenderState camera, PoseStack pose);
}

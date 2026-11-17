package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.mojang.blaze3d.pipeline.RenderTarget;
import com.mojang.blaze3d.platform.NativeImage;
import com.mojang.blaze3d.vertex.PoseStack;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.client.Screenshot;
import net.minecraft.client.SectionUpdateTracker;
import net.minecraft.client.renderer.chunk.SectionRenderDispatcher;
import net.minecraft.client.renderer.state.GameRenderState;
import net.minecraft.client.renderer.state.level.CameraRenderState;
import net.minecraft.client.renderer.state.level.PlayerRenderState;
import net.minecraft.client.server.IntegratedServer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.SectionPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;
import org.joml.Matrix4f;

import java.io.File;
import java.io.IOException;
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.Collections;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * view.block in 26.3 (PROTOCOL.md 8.10; SPEC.md 15.6 step 6, 19.7 step 3c), as 1.7.10's View: the frame the game drew for
 * the player, the HUD hidden and the view's bobbing stopped, and the pixels of it the block covers by the game's own
 * ray (ViewMask, shared). The camera is the frame's own, as 26.3 kept it to draw it: its render state's position,
 * view rotation and projection, with the hurt tilt (and the bobbing, if on) the game puts on the projection. 26.3
 * builds a changed chunk section again on other threads, so the frame is taken once the block's own section is built
 * from the block as it is (as the server has it, in singleplayer), and then drawn: never a frame of the block before.
 * 26.3 draws no toast while the HUD is hidden: nothing covers the world.
 */
final class V26View {

	/** The settings a view is taken with, before it was: the HUD's (hidden for the view) and the view's bobbing. */
	private static final long HID_HUD = 1;
	private static final long STOPPED_BOBBING = 2;
	/** The client ticks the block's section may take to be built anew and drawn. */
	private static final int REBUILT_TICKS = 200;
	/** The client ticks the picture may take to come back. */
	private static final int PICTURE_TICKS = 40;
	/** A section's last build, and whether it is done (26.3's own, private: read for the wait above). */
	private static final Field LAST_BUILD = Members.field(SectionRenderDispatcher.RenderSection.class, "lastCompileTask");
	private static final Field DONE = Members.field(SectionRenderDispatcher.RenderSection.SectionTask.class, "isCompleted");
	private static final Field CANCELLED = Members.field(SectionRenderDispatcher.RenderSection.SectionTask.class, "isCancelled");
	/** The sections 26.3 knows changed and has yet to build again (LevelExtractor's, private). */
	private static final Field TRACKER = Members.field(net.minecraft.client.renderer.extract.LevelExtractor.class,
		"sectionUpdateTracker");
	/** The hurt tilt and the bobbing renderLevel puts on the projection (GameRenderer's, private). */
	private static final java.lang.reflect.Method BOB_HURT = Members.method(net.minecraft.client.renderer.GameRenderer.class,
		"bobHurt", CameraRenderState.class, PoseStack.class);
	private static final java.lang.reflect.Method BOB_VIEW = Members.method(net.minecraft.client.renderer.GameRenderer.class,
		"bobView", CameraRenderState.class, PoseStack.class);

	private V26View() {
	}

	static void bind(Probe probe) {
		probe.op("view.block").does(V26View::hide).settles(V26View::take);
	}

	/** The HUD hidden and the view's bobbing stopped, for the frames to come; what was set already is left. */
	private static JsonElement hide(Call call) throws ProbeException {
		Minecraft mc = Minecraft.getInstance();
		if (mc.player == null || mc.level == null) {
			throw new ProbeException("NotReady", "view.block needs a world", null);
		}
		ModernThings.blockPos(call);
		String file = call.string("file", null);
		if (file == null || !new File(file).isAbsolute()) {
			throw ProbeException.badRequest("file", "view.block needs the file to write the frame to, an absolute path");
		}
		long changed = 0;
		if (!mc.gui.hud.isHidden()) {
			mc.gui.hud.toggle();
			changed |= HID_HUD;
		}
		if (mc.options.bobView().get()) {
			mc.options.bobView().set(false);
			changed |= STOPPED_BOBBING;
		}
		call.mark = changed;
		return new JsonObject();
	}

	/**
	 * Once the block's section is built from the block as it is, the settle ticks' frames, then the frame, its camera
	 * and the block's pixels; the settings put back.
	 */
	private static JsonElement take(Call call, JsonElement value) throws ProbeException, InterruptedException {
		long changed = call.mark;
		try {
			BlockPos pos = ModernThings.blockPos(call);
			File file = new File(call.string("file", null));
			rebuilt(call, pos, value);
			ModernThings.waitClient(call, call.number("settle_ticks", 2, 1, 1200), value);
			CompletableFuture<int[]> written = new CompletableFuture<>();
			JsonObject answer = on(call, Side.CLIENT, () -> view(Minecraft.getInstance(), pos, file, written));
			for (int tick = 0; tick < PICTURE_TICKS && !written.isDone(); tick++) {
				ModernThings.waitClient(call, 1, value);
			}
			if (!written.isDone()) {
				throw new ProbeException("ProbeError", "the frame didn't come back in " + PICTURE_TICKS + " client ticks", null);
			}
			try {
				written.join();
			} catch (CompletionException e) {
				throw new ProbeException("ProbeError", "the frame couldn't be written: " + e.getCause(), null);
			}
			return answer;
		} finally {
			Sides.get().post(Side.CLIENT, () -> {
				Minecraft mc = Minecraft.getInstance();
				if ((changed & HID_HUD) != 0 && mc.gui.hud.isHidden()) {
					mc.gui.hud.toggle();
				}
				if ((changed & STOPPED_BOBBING) != 0) {
					mc.options.bobView().set(true);
				}
				return null;
			});
		}
	}

	/** A step on the side's thread; what it throws besides the probe's own is the probe's failure. */
	private static <T> T on(Call call, Side side, java.util.concurrent.Callable<T> step)
		throws ProbeException, InterruptedException {
		try {
			return Sides.get().run(side, step, Sides.STALL_SECONDS, null);
		} catch (Sides.Stalled stalled) {
			throw Ops.stalled(call.probe, stalled);
		} catch (ProbeException | InterruptedException | RuntimeException e) {
			throw e;
		} catch (Exception e) {
			throw new ProbeException("ProbeError", "the view failed: " + e, null);
		}
	}

	/**
	 * Waits, by client ticks, until the client has the block as its server does (in singleplayer), and the block's
	 * section, where the frame draws it, is built from it: not marked changed, and its last build done.
	 */
	private static void rebuilt(Call call, BlockPos pos, JsonElement value) throws ProbeException, InterruptedException {
		for (int tick = 0; tick <= REBUILT_TICKS; tick++) {
			BlockState served = served(call, pos);
			if (on(call, Side.CLIENT, () -> rebuilt(Minecraft.getInstance(), pos, served))) {
				return;
			}
			ModernThings.waitClient(call, 1, value);
		}
		throw new ProbeException("ProbeError", "the block at " + pos.toShortString() + " wasn't drawn anew in "
			+ REBUILT_TICKS + " client ticks: its chunk section wasn't built again from it", null);
	}

	/** The block as the integrated server has it, read on its thread; null without one (a client of a server). */
	private static BlockState served(Call call, BlockPos pos) throws ProbeException, InterruptedException {
		IntegratedServer server = Minecraft.getInstance().getSingleplayerServer();
		if (server == null) {
			return null;
		}
		return on(call, Side.SERVER, () -> {
			Minecraft mc = Minecraft.getInstance();
			ServerLevel level = mc.level == null ? null : server.getLevel(mc.level.dimension());
			return level == null ? null : level.getBlockState(pos);
		});
	}

	private static boolean rebuilt(Minecraft mc, BlockPos pos, BlockState served) throws ReflectiveOperationException {
		if (mc.level == null) {
			throw new IllegalStateException("the world closed while view.block waited");
		}
		if (served != null && !served.equals(mc.level.getBlockState(pos))) {
			return false;
		}
		long node = SectionPos.asLong(pos);
		SectionRenderDispatcher.RenderSection section = null;
		for (SectionRenderDispatcher.RenderSection each : mc.levelRenderer.visibleSections()) {
			if (each.getSectionNode() == node) {
				section = each;
				break;
			}
		}
		if (section == null) {
			// not drawn this frame (out of the view, or hidden behind others): no look of it to wait for
			return true;
		}
		SectionUpdateTracker tracker = Members.get(TRACKER, mc.levelExtractor);
		SectionUpdateTracker.SectionDirtyState dirty = tracker.getDirtyState(node);
		if (dirty != null && dirty.isDirty()) {
			return false;
		}
		Object build = LAST_BUILD.get(section);
		return build == null || ((AtomicBoolean) DONE.get(build)).get() || ((AtomicBoolean) CANCELLED.get(build)).get();
	}

	/** The last frame drawn: its camera, the block's pixels on it, and the frame itself asked for, to 'written'. */
	private static JsonObject view(Minecraft mc, BlockPos pos, File file, CompletableFuture<int[]> written)
		throws ProbeException {
		if (mc.level == null) {
			throw new ProbeException("NotReady", "the world closed while view.block waited", null);
		}
		GameRenderState state = mc.gameRenderer.gameRenderState();
		CameraRenderState camera = state.levelRenderState.cameraRenderState;
		PlayerRenderState player = state.levelRenderState.playerRenderState;
		if (camera == null || !camera.initialized) {
			throw new ProbeException("NotReady", "no frame of the world has been drawn yet", null);
		}
		float effect = state.optionsRenderState.screenEffectScale;
		if (Math.max(player.portalEffectIntensity, player.nauseaEffectIntensity) * effect * effect > 0) {
			throw new ProbeException("Unsupported", "the frame is warped (nausea, or a portal's effect): its camera"
				+ " can't place the block's pixels", null);
		}
		// the level's projection as renderLevel makes it: the camera's, times the hurt tilt and the bobbing
		PoseStack bob = new PoseStack();
		Members.call(BOB_HURT, mc.gameRenderer, camera, bob);
		if (state.optionsRenderState.bobView) {
			Members.call(BOB_VIEW, mc.gameRenderer, camera, bob);
		}
		float[] projection = new float[16];
		new Matrix4f(camera.projectionMatrix).mul(bob.last().pose()).get(projection);
		float[] modelview = new float[16];
		new Matrix4f(camera.viewRotationMatrix).get(modelview);
		RenderTarget target = mc.gameRenderer.mainRenderTarget();
		int width = target.width;
		int height = target.height;
		int[] viewport = {0, 0, width, height};
		double[] eye = {camera.pos.x, camera.pos.y, camera.pos.z};
		double[] toClip = Matrices.multiply(Matrices.of(projection), Matrices.of(modelview));
		JsonObject cameraValue = Json.object(
			"pos", Arrays.asList(eye[0], eye[1], eye[2]),
			"look", ModernValues.look(mc.getCameraEntity()),
			"modelview", ViewMask.floats(modelview),
			"projection", ViewMask.floats(projection),
			"viewport", Arrays.asList(viewport[0], viewport[1], viewport[2], viewport[3]));
		JsonObject value = Json.object("file", file.getAbsolutePath(), "width", width, "height", height,
			"tick", Sides.get().ticks(Side.CLIENT), "camera", cameraValue);
		value.add("covered", new JsonArray());
		ViewMask.into(value, new int[]{pos.getX(), pos.getY(), pos.getZ()}, eye, toClip, viewport, width, height,
			Collections.<int[]>emptyList(), (start, end) -> {
				BlockHitResult hit = mc.level.clip(new ClipContext(new Vec3(start[0], start[1], start[2]),
					new Vec3(end[0], end[1], end[2]), ClipContext.Block.OUTLINE, ClipContext.Fluid.NONE, mc.getCameraEntity()));
				// 26.3's Direction counts the faces as ViewMask does
				return hit.getType() == HitResult.Type.BLOCK && hit.getBlockPos().equals(pos) ? hit.getDirection().ordinal()
					: -1;
			});
		// the same frame, as the game's screenshot copies it: the main render target holds the last frame drawn
		Screenshot.takeScreenshot(target, (NativeImage image) -> {
			try (image) {
				File folder = file.getParentFile();
				if (folder != null) {
					folder.mkdirs();
				}
				image.writeToFile(file);
				written.complete(new int[] {image.getWidth(), image.getHeight()});
			} catch (IOException | RuntimeException e) {
				written.completeExceptionally(e);
			}
		});
		return value;
	}
}

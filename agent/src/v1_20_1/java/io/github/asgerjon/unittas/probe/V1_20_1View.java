package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.mojang.blaze3d.pipeline.RenderTarget;
import com.mojang.blaze3d.platform.NativeImage;
import com.mojang.blaze3d.vertex.PoseStack;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Camera;
import net.minecraft.client.Minecraft;
import net.minecraft.client.Screenshot;
import net.minecraft.client.renderer.LevelRenderer;
import net.minecraft.client.renderer.chunk.ChunkRenderDispatcher;
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
import java.util.List;
import java.util.Set;
import java.util.WeakHashMap;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * view.block in 1.20.1 (PROTOCOL.md 8.10; SPEC.md 19.7 step 6e), as 26.3's (V26View) and 1.7.10's View: the frame the
 * game drew for the player, the HUD hidden and the view's bobbing stopped, and the pixels of it the block covers by
 * the game's own ray (ViewMask, shared). 1.20.1 keeps no render state of a frame's camera, so the probe keeps it:
 * the view.frame hook, on LevelRenderer.renderLevel, is given the camera, the view rotation (on its pose stack) and
 * the projection the frame is drawn with (the hurt tilt and the bobbing on it, as GameRenderer.renderLevel makes it).
 * 1.20.1 builds a changed chunk section (its RenderChunk) again on other threads, and its tasks say only whether they
 * were cancelled: the view.compiled hook, on LevelRenderer.addRecentlyCompiledChunk (which only a build that wasn't
 * cancelled calls), marks a section's last build done. So the frame is taken once the block's own section is built
 * from the block as it is (as the server has it, in singleplayer): never a frame of the block before.
 */
final class V1_20_1View {

	/** The settings a view is taken with, before it was: the HUD's (hidden for the view) and the view's bobbing. */
	private static final long HID_HUD = 1;
	private static final long STOPPED_BOBBING = 2;
	/** The client ticks the block's section may take to be built anew and drawn. */
	private static final int REBUILT_TICKS = 200;
	/** The client ticks the picture may take to come back. */
	private static final int PICTURE_TICKS = 40;

	/** The last frame's camera, as renderLevel gave it to the level's renderer: its place, view rotation and projection. */
	private record Frame(Vec3 eye, float[] modelview, float[] projection) {
	}

	private static volatile Frame last;
	/** The builds of sections that finished (weakly: a section's next build replaces its last). */
	private static final Set<Object> DONE = Collections.synchronizedSet(Collections.newSetFromMap(new WeakHashMap<>()));

	/** 1.20.1's own, private: found at the first view, once the names are known. */
	private static final class Fields {

		static final Field LAST_BUILD = Members.field(ChunkRenderDispatcher.RenderChunk.class, "lastRebuildTask");
		static final Field VISIBLE = Members.field(LevelRenderer.class, "renderChunksInFrustum");
	}

	/** A drawn section's info's section (RenderChunkInfo is package-private: found from an info's own class, once). */
	private static volatile Field infoChunk;

	private static ChunkRenderDispatcher.RenderChunk chunkOf(Object info) {
		Field found = infoChunk;
		if (found == null) {
			found = Members.field(info.getClass(), "chunk");
			infoChunk = found;
		}
		return Members.get(found, info);
	}

	/** A build's cancelled flag (ChunkCompileTask's, a private class: found from a build's own class, once). */
	private static volatile Field cancelled;

	private static boolean cancelled(Object build) {
		Field found = cancelled;
		if (found == null) {
			Class<?> type = build.getClass();
			while (type != null && !Members.mojang(type).endsWith("ChunkRenderDispatcher$RenderChunk$ChunkCompileTask")) {
				type = type.getSuperclass();
			}
			if (type == null) {
				throw new IllegalStateException(Members.className(build.getClass()) + " isn't a section's ChunkCompileTask");
			}
			found = Members.field(type, "isCancelled");
			cancelled = found;
		}
		return ((AtomicBoolean) Members.get(found, build)).get();
	}

	private V1_20_1View() {
	}

	static void bind(Probe probe) {
		probe.op("view.block").does(V1_20_1View::hide).settles(V1_20_1View::take);
	}

	/**
	 * The view.frame hook: LevelRenderer.renderLevel's arguments (the pose stack, the view rotation its last pose; the
	 * partial tick; the frame's end in nanoseconds; whether the block outline is drawn; the camera; the game renderer;
	 * the light texture; the projection), kept.
	 */
	static void frame(Object[] arguments) {
		Camera camera = (Camera) arguments[4];
		float[] modelview = new float[16];
		((PoseStack) arguments[0]).last().pose().get(modelview);
		float[] projection = new float[16];
		((Matrix4f) arguments[7]).get(projection);
		last = new Frame(camera.getPosition(), modelview, projection);
	}

	/** The view.compiled hook: the section's last build is done (a build cancelled never gets here). */
	static void compiled(Object section) {
		Object build = Members.get(Fields.LAST_BUILD, section);
		if (build != null) {
			DONE.add(build);
		}
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
		if (!Version.hudHidden()) {
			Version.toggleHud();
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
				if ((changed & HID_HUD) != 0 && Version.hudHidden()) {
					Version.toggleHud();
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
	 * section, where the frame draws it, is built from it: not marked changed, and its last build done or cancelled.
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

	private static boolean rebuilt(Minecraft mc, BlockPos pos, BlockState served) {
		if (mc.level == null) {
			throw new IllegalStateException("the world closed while view.block waited");
		}
		if (served != null && !served.equals(mc.level.getBlockState(pos))) {
			return false;
		}
		BlockPos origin = SectionPos.of(pos).origin();
		ChunkRenderDispatcher.RenderChunk section = null;
		List<?> visible = Members.get(Fields.VISIBLE, mc.levelRenderer);
		for (Object info : visible) {
			ChunkRenderDispatcher.RenderChunk each = chunkOf(info);
			if (each.getOrigin().equals(origin)) {
				section = each;
				break;
			}
		}
		if (section == null) {
			// not drawn this frame (out of the view, or hidden behind others): no look of it to wait for
			return true;
		}
		if (section.isDirty()) {
			return false;
		}
		Object build = Members.get(Fields.LAST_BUILD, section);
		return build == null || DONE.contains(build) || cancelled(build);
	}

	/** The last frame drawn: its camera, the block's pixels on it, and the frame itself, written to 'written'. */
	private static JsonObject view(Minecraft mc, BlockPos pos, File file, CompletableFuture<int[]> written)
		throws ProbeException {
		if (mc.level == null || mc.player == null) {
			throw new ProbeException("NotReady", "the world closed while view.block waited", null);
		}
		Frame frame = last;
		if (frame == null) {
			throw new ProbeException("NotReady", "no frame of the world has been drawn yet", null);
		}
		float effect = mc.options.screenEffectScale().get().floatValue();
		if (mc.player.spinningEffectIntensity * effect * effect > 0) {
			throw new ProbeException("Unsupported", "the frame is warped (nausea, or a portal's effect): its camera"
				+ " can't place the block's pixels", null);
		}
		RenderTarget target = mc.getMainRenderTarget();
		int width = target.width;
		int height = target.height;
		int[] viewport = {0, 0, width, height};
		double[] eye = {frame.eye().x, frame.eye().y, frame.eye().z};
		double[] toClip = Matrices.multiply(Matrices.of(frame.projection()), Matrices.of(frame.modelview()));
		JsonObject cameraValue = Json.object(
			"pos", Arrays.asList(eye[0], eye[1], eye[2]),
			"look", ModernValues.look(mc.getCameraEntity()),
			"modelview", ViewMask.floats(frame.modelview()),
			"projection", ViewMask.floats(frame.projection()),
			"viewport", Arrays.asList(viewport[0], viewport[1], viewport[2], viewport[3]));
		JsonObject value = Json.object("file", file.getAbsolutePath(), "width", width, "height", height,
			"tick", Sides.get().ticks(Side.CLIENT), "camera", cameraValue);
		value.add("covered", new JsonArray());
		ViewMask.into(value, new int[]{pos.getX(), pos.getY(), pos.getZ()}, eye, toClip, viewport, width, height,
			Collections.<int[]>emptyList(), (start, end) -> {
				BlockHitResult hit = mc.level.clip(new ClipContext(new Vec3(start[0], start[1], start[2]),
					new Vec3(end[0], end[1], end[2]), ClipContext.Block.OUTLINE, ClipContext.Fluid.NONE, mc.getCameraEntity()));
				// 1.20.1's Direction counts the faces as ViewMask does
				return hit.getType() == HitResult.Type.BLOCK && hit.getBlockPos().equals(pos) ? hit.getDirection().ordinal()
					: -1;
			});
		// the same frame, as the game's screenshot copies it: the main render target holds the last frame drawn
		try (NativeImage image = Screenshot.takeScreenshot(target)) {
			File folder = file.getParentFile();
			if (folder != null) {
				folder.mkdirs();
			}
			image.writeToFile(file);
			written.complete(new int[] {image.getWidth(), image.getHeight()});
		} catch (IOException | RuntimeException e) {
			written.completeExceptionally(e);
		}
		return value;
	}
}

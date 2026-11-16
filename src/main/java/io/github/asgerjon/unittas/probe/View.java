package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.ActiveRenderInfo;
import net.minecraft.client.renderer.entity.RenderManager;
import net.minecraft.util.MovingObjectPosition;
import net.minecraft.util.Vec3;
import net.minecraft.world.World;

import java.io.File;
import java.io.IOException;
import java.lang.reflect.Field;
import java.nio.FloatBuffer;
import java.nio.IntBuffer;
import java.util.Arrays;

/**
 * view.block (PROTOCOL.md 8.10, SPEC.md 15.4 and 15.6 step 6): the frame the game drew for the player, the GUI hidden,
 * and the pixels of it that a block covers, by the game's own ray. The frame is the game's own screenshot; the camera
 * is that frame's, as the game kept it (ActiveRenderInfo's matrices, RenderManager's viewer position); for each pixel
 * of the block's box on the frame, the ray from the camera through its middle is cast as the crosshair's is, and the
 * pixel is the block's when that ray meets the block first. Parallax, the player's own way to tell what hides what,
 * comes later (15.4); until then the game's ray says.
 */
final class View {

	/** The settings a view is taken with, before it was: the GUI's (hidden for the view) and the view's bobbing. */
	private static final long HID_GUI = 1;
	private static final long STOPPED_BOBBING = 2;
	/** How far a pixel's ray is cast, in blocks: beyond any reach. */
	private static final double RAY = 64.0;
	/** The face a ray met, by 1.7.10's sideHit (ForgeDirection's order). */
	private static final String[] FACES = {"down", "up", "north", "south", "west", "east"};

	private View() {
	}

	static void bind(Probe probe) {
		probe.op("view.block").does(View::hide).settles(View::take);
	}

	/** The GUI hidden and the view's bobbing stopped, for the frames to come; what was set already is left. */
	private static JsonElement hide(Call call) throws ProbeException {
		Minecraft mc = Minecraft.getMinecraft();
		if (mc.thePlayer == null || mc.theWorld == null) {
			throw new ProbeException("NotReady", "view.block needs a world", null);
		}
		ThingOps.position(call, "pos");
		String file = call.string("file", null);
		if (file == null || !new File(file).isAbsolute()) {
			throw ProbeException.badRequest("file", "view.block needs the file to write the frame to, an absolute path");
		}
		long changed = 0;
		if (!mc.gameSettings.hideGUI) {
			mc.gameSettings.hideGUI = true;
			changed |= HID_GUI;
		}
		if (mc.gameSettings.viewBobbing) {
			mc.gameSettings.viewBobbing = false;
			changed |= STOPPED_BOBBING;
		}
		call.mark = changed;
		return new JsonObject();
	}

	/** After the settle ticks' frames: the frame, its camera and the block's pixels; the settings put back. */
	private static JsonElement take(Call call, JsonElement value) throws ProbeException, InterruptedException {
		long changed = call.mark;
		try {
			try {
				Sides.get().waitTicks(Side.CLIENT, call.number("settle_ticks", 2, 1, 1200), Sides.STALL_SECONDS);
			} catch (Sides.Stalled stalled) {
				throw Ops.stalled(call.probe, stalled);
			}
			int[] pos = ThingOps.position(call, "pos");
			File file = new File(call.string("file", null));
			return Sides.get().run(Side.CLIENT, () -> view(Minecraft.getMinecraft(), pos, file), Sides.STALL_SECONDS,
				null);
		} catch (InterruptedException | RuntimeException | ProbeException e) {
			throw e;
		} catch (IOException e) {
			throw new ProbeException("ProbeError", "the frame couldn't be written: " + e, null);
		} catch (Exception e) {
			throw new ProbeException("ProbeError", "the view failed: " + e, null);
		} finally {
			Sides.get().post(Side.CLIENT, () -> {
				Minecraft mc = Minecraft.getMinecraft();
				if ((changed & HID_GUI) != 0) {
					mc.gameSettings.hideGUI = false;
				}
				if ((changed & STOPPED_BOBBING) != 0) {
					mc.gameSettings.viewBobbing = true;
				}
				return null;
			});
		}
	}

	private static JsonElement view(Minecraft mc, int[] pos, File file) throws Exception {
		Pictures.saveAs(mc, file);
		float[] modelview = matrix("modelview", "field_74594_j");
		float[] projection = matrix("projection", "field_74595_k");
		int[] viewport = viewport();
		double[] eye = {RenderManager.renderPosX, RenderManager.renderPosY, RenderManager.renderPosZ};
		double[] toClip = Matrices.multiply(Matrices.of(projection), Matrices.of(modelview));
		double[] fromClip = Matrices.invert(toClip);
		int width = mc.displayWidth;
		int height = mc.displayHeight;
		JsonObject camera = Json.object(
			"pos", Arrays.asList(eye[0], eye[1], eye[2]),
			"look", Values.look(mc.renderViewEntity),
			"modelview", floats(modelview),
			"projection", floats(projection),
			"viewport", Arrays.asList(viewport[0], viewport[1], viewport[2], viewport[3]));
		JsonObject value = Json.object("file", file.getAbsolutePath(), "width", width, "height", height,
			"tick", Sides.get().ticks(Side.CLIENT), "camera", camera);
		// what the game draws over the world with the GUI hidden: 1.7.10's tutorial toast ("Press 'E' to open your
		// inventory"), whose pixels are no block's
		int[] toast = toast(mc);
		JsonArray covered = new JsonArray();
		if (toast != null) {
			covered.add(Json.object("by", "toast", "rect", Arrays.asList(toast[0], toast[1], toast[2], toast[3])));
		}
		value.add("covered", covered);
		int[] rect = rect(pos, eye, toClip, viewport, width, height);
		if (rect == null) {
			value.add("rect", com.google.gson.JsonNull.INSTANCE);
			value.add("mask", new JsonArray());
			value.add("faces", new JsonObject());
			return value;
		}
		World world = mc.theWorld;
		JsonArray mask = new JsonArray();
		int[] faces = new int[FACES.length];
		for (int y = rect[1]; y < rect[3]; y++) {
			StringBuilder row = new StringBuilder(rect[2] - rect[0]);
			for (int x = rect[0]; x < rect[2]; x++) {
				if (toast != null && x >= toast[0] && x < toast[2] && y >= toast[1] && y < toast[3]) {
					row.append('0');
					continue;
				}
				double[][] ray = ray(x, y, eye, fromClip, viewport, height);
				MovingObjectPosition hit = world.rayTraceBlocks(
					Vec3.createVectorHelper(ray[0][0], ray[0][1], ray[0][2]),
					Vec3.createVectorHelper(ray[1][0], ray[1][1], ray[1][2]), false, false, true);
				boolean mine = hit != null && hit.typeOfHit == MovingObjectPosition.MovingObjectType.BLOCK
					&& hit.blockX == pos[0] && hit.blockY == pos[1] && hit.blockZ == pos[2];
				row.append(mine ? '1' : '0');
				if (mine && hit.sideHit >= 0 && hit.sideHit < FACES.length) {
					faces[hit.sideHit]++;
				}
			}
			mask.add(Json.of(row.toString()));
		}
		JsonObject shown = new JsonObject();
		for (int i = 0; i < FACES.length; i++) {
			if (faces[i] > 0) {
				shown.addProperty(FACES[i], faces[i]);
			}
		}
		value.add("rect", Json.of(Arrays.asList(rect[0], rect[1], rect[2], rect[3])));
		value.add("mask", mask);
		value.add("faces", shown);
		return value;
	}

	/**
	 * The box on the frame the block's corners fall in, [x0, y0, x1, y1) in the frame's pixels from its top left, kept
	 * to the frame; the whole frame when a corner is behind the camera; null when nothing of it is in front.
	 */
	private static int[] rect(int[] pos, double[] eye, double[] toClip, int[] viewport, int width, int height) {
		double left = Double.MAX_VALUE;
		double top = Double.MAX_VALUE;
		double right = -Double.MAX_VALUE;
		double bottom = -Double.MAX_VALUE;
		int behind = 0;
		for (int corner = 0; corner < 8; corner++) {
			double[] clip = Matrices.apply(toClip, new double[]{
				pos[0] + (corner & 1) - eye[0], pos[1] + (corner >> 1 & 1) - eye[1], pos[2] + (corner >> 2 & 1) - eye[2], 1});
			if (clip[3] <= 1e-6) {
				behind++;
				continue;
			}
			double x = viewport[0] + (clip[0] / clip[3] + 1) / 2 * viewport[2];
			double y = height - (viewport[1] + (clip[1] / clip[3] + 1) / 2 * viewport[3]);
			left = Math.min(left, x);
			right = Math.max(right, x);
			top = Math.min(top, y);
			bottom = Math.max(bottom, y);
		}
		if (behind == 8) {
			return null;
		}
		if (behind > 0) {
			return new int[]{0, 0, width, height};
		}
		int x0 = Math.max(0, (int) Math.floor(left));
		int y0 = Math.max(0, (int) Math.floor(top));
		int x1 = Math.min(width, (int) Math.ceil(right));
		int y1 = Math.min(height, (int) Math.ceil(bottom));
		return x0 < x1 && y0 < y1 ? new int[]{x0, y0, x1, y1} : null;
	}

	/** The ray through a pixel's middle: from the near plane, RAY blocks on, in the world's coordinates. */
	private static double[][] ray(int x, int y, double[] eye, double[] fromClip, int[] viewport, int height) {
		double ndcX = 2 * ((x + 0.5) - viewport[0]) / viewport[2] - 1;
		double ndcY = 2 * ((height - (y + 0.5)) - viewport[1]) / viewport[3] - 1;
		double[] near = Matrices.apply(fromClip, new double[]{ndcX, ndcY, -1, 1});
		double[] far = Matrices.apply(fromClip, new double[]{ndcX, ndcY, 1, 1});
		double[] start = new double[3];
		double[] along = new double[3];
		double length = 0;
		for (int i = 0; i < 3; i++) {
			start[i] = near[i] / near[3];
			along[i] = far[i] / far[3] - start[i];
			length += along[i] * along[i];
		}
		length = Math.sqrt(length);
		double[] end = new double[3];
		for (int i = 0; i < 3; i++) {
			end[i] = start[i] + along[i] / length * RAY + eye[i];
			start[i] += eye[i];
		}
		return new double[][]{start, end};
	}

	/**
	 * The frame's pixels 1.7.10's achievement toast takes while it shows, [x0, y0, x1, y1): 160 by 32 of the GUI's
	 * units at the top right, as GuiAchievement draws it (its slide counted as shown); null while none shows.
	 */
	private static int[] toast(Minecraft mc) throws ReflectiveOperationException {
		Object achievement = toastField("theAchievement", "field_146266_k").get(mc.guiAchievement);
		long since = toastField("notificationTime", "field_146263_l").getLong(mc.guiAchievement);
		if (achievement == null || since == 0) {
			return null;
		}
		int scale = new net.minecraft.client.gui.ScaledResolution(mc, mc.displayWidth, mc.displayHeight).getScaleFactor();
		return new int[]{Math.max(0, mc.displayWidth - 160 * scale), 0, mc.displayWidth, Math.min(mc.displayHeight,
			32 * scale)};
	}

	private static Field toastField(String name, String srg) throws NoSuchFieldException {
		Class<?> type = net.minecraft.client.gui.achievement.GuiAchievement.class;
		Field field;
		try {
			field = type.getDeclaredField(name);
		} catch (NoSuchFieldException e) {
			field = type.getDeclaredField(srg);
		}
		field.setAccessible(true);
		return field;
	}

	private static float[] matrix(String name, String srg) throws ReflectiveOperationException {
		FloatBuffer buffer = (FloatBuffer) field(name, srg).get(null);
		float[] values = new float[16];
		for (int i = 0; i < 16; i++) {
			values[i] = buffer.get(i);
		}
		return values;
	}

	private static int[] viewport() throws ReflectiveOperationException {
		IntBuffer buffer = (IntBuffer) field("viewport", "field_74597_i").get(null);
		return new int[]{buffer.get(0), buffer.get(1), buffer.get(2), buffer.get(3)};
	}

	private static Field field(String name, String srg) throws NoSuchFieldException {
		Field field;
		try {
			field = ActiveRenderInfo.class.getDeclaredField(name);
		} catch (NoSuchFieldException e) {
			field = ActiveRenderInfo.class.getDeclaredField(srg);
		}
		field.setAccessible(true);
		return field;
	}

	private static java.util.List<Double> floats(float[] values) {
		java.util.List<Double> out = new java.util.ArrayList<>();
		for (float each : values) {
			out.add((double) each);
		}
		return out;
	}
}

package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;

import java.util.Arrays;
import java.util.List;

/**
 * view.block's pixels (PROTOCOL.md 8.10, SPEC.md 15.6 step 6), the same in every port: from the frame's camera (its
 * eye, and its projection times its modelview, relative to the eye), the box on the frame the block's corners fall in,
 * and for each pixel of it, the ray from the camera through the pixel's middle, cast by the port as its crosshair's is;
 * the pixel is the block's when that ray meets the block first. What the game draws over the world (1.7.10's toast) is
 * no block's.
 */
final class ViewMask {

	/** A face by its number, as both 1.7.10's sideHit and 26.3's Direction count them. */
	static final String[] FACES = {"down", "up", "north", "south", "west", "east"};
	/** How far a pixel's ray is cast, in blocks: beyond any reach. */
	private static final double RAY = 64.0;

	/** A port's ray: the face (FACES' number) it meets the block at first, or -1 when it meets something else first. */
	interface Ray {
		int face(double[] start, double[] end);
	}

	private ViewMask() {
	}

	/**
	 * The block's box on the frame ("rect", null when nothing of it is in front), its mask (a row of '0' and '1' for
	 * each row of the box), and how many of its pixels show each face ("faces"), put into 'value'. A pixel inside one of
	 * 'covered' ([x0, y0, x1, y1) each) is no block's.
	 */
	static void into(JsonObject value, int[] pos, double[] eye, double[] toClip, int[] viewport, int width, int height,
			List<int[]> covered, Ray ray) {
		int[] rect = rect(pos, eye, toClip, viewport, width, height);
		if (rect == null) {
			value.add("rect", JsonNull.INSTANCE);
			value.add("mask", new JsonArray());
			value.add("faces", new JsonObject());
			return;
		}
		double[] fromClip = Matrices.invert(toClip);
		JsonArray mask = new JsonArray();
		int[] faces = new int[FACES.length];
		for (int y = rect[1]; y < rect[3]; y++) {
			StringBuilder row = new StringBuilder(rect[2] - rect[0]);
			for (int x = rect[0]; x < rect[2]; x++) {
				if (inside(covered, x, y)) {
					row.append('0');
					continue;
				}
				double[][] through = ray(x, y, eye, fromClip, viewport, height);
				int face = ray.face(through[0], through[1]);
				row.append(face >= 0 ? '1' : '0');
				if (face >= 0 && face < FACES.length) {
					faces[face]++;
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
	}

	private static boolean inside(List<int[]> covered, int x, int y) {
		for (int[] each : covered) {
			if (x >= each[0] && x < each[2] && y >= each[1] && y < each[3]) {
				return true;
			}
		}
		return false;
	}

	/**
	 * The box on the frame the block's corners fall in, [x0, y0, x1, y1) in the frame's pixels from its top left, kept
	 * to the frame; the whole frame when a corner is behind the camera; null when nothing of it is in front.
	 */
	static int[] rect(int[] pos, double[] eye, double[] toClip, int[] viewport, int width, int height) {
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
	static double[][] ray(int x, int y, double[] eye, double[] fromClip, int[] viewport, int height) {
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

	/** A matrix's 16 numbers as JSON's list. */
	static List<Double> floats(float[] values) {
		java.util.List<Double> out = new java.util.ArrayList<>();
		for (float each : values) {
			out.add((double) each);
		}
		return out;
	}
}

package io.github.asgerjon.unittas.probe;

/**
 * 4 by 4 matrices as OpenGL keeps them: 16 numbers, column by column (row r of column c at c * 4 + r). For view.block's
 * camera: a frame's projection and modelview, a point through them, and back.
 */
final class Matrices {

	private Matrices() {
	}

	static double[] of(float[] values) {
		double[] out = new double[16];
		for (int i = 0; i < 16; i++) {
			out[i] = values[i];
		}
		return out;
	}

	/** a times b. */
	static double[] multiply(double[] a, double[] b) {
		double[] out = new double[16];
		for (int c = 0; c < 4; c++) {
			for (int r = 0; r < 4; r++) {
				double sum = 0;
				for (int k = 0; k < 4; k++) {
					sum += a[k * 4 + r] * b[c * 4 + k];
				}
				out[c * 4 + r] = sum;
			}
		}
		return out;
	}

	/** m times the column v (four numbers). */
	static double[] apply(double[] m, double[] v) {
		double[] out = new double[4];
		for (int r = 0; r < 4; r++) {
			double sum = 0;
			for (int c = 0; c < 4; c++) {
				sum += m[c * 4 + r] * v[c];
			}
			out[r] = sum;
		}
		return out;
	}

	/** m's inverse, by Gauss-Jordan with partial pivoting; IllegalArgumentException for a singular m. */
	static double[] invert(double[] m) {
		double[][] rows = new double[4][8];
		for (int r = 0; r < 4; r++) {
			for (int c = 0; c < 4; c++) {
				rows[r][c] = m[c * 4 + r];
			}
			rows[r][4 + r] = 1;
		}
		for (int col = 0; col < 4; col++) {
			int pivot = col;
			for (int r = col + 1; r < 4; r++) {
				if (Math.abs(rows[r][col]) > Math.abs(rows[pivot][col])) {
					pivot = r;
				}
			}
			if (Math.abs(rows[pivot][col]) < 1e-12) {
				throw new IllegalArgumentException("the camera's matrix has no inverse");
			}
			double[] swap = rows[col];
			rows[col] = rows[pivot];
			rows[pivot] = swap;
			double scale = rows[col][col];
			for (int c = 0; c < 8; c++) {
				rows[col][c] /= scale;
			}
			for (int r = 0; r < 4; r++) {
				if (r != col) {
					double factor = rows[r][col];
					for (int c = 0; c < 8; c++) {
						rows[r][c] -= factor * rows[col][c];
					}
				}
			}
		}
		double[] out = new double[16];
		for (int r = 0; r < 4; r++) {
			for (int c = 0; c < 4; c++) {
				out[c * 4 + r] = rows[r][4 + c];
			}
		}
		return out;
	}
}

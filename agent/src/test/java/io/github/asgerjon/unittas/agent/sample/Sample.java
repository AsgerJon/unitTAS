package io.github.asgerjon.unittas.agent.sample;

import java.util.ArrayList;
import java.util.List;

/**
 * The methods WrapCheck has the agent's rewriter wrap, one of each kind the game's hooked methods are (SPEC.md 19.7
 * step 6a): an int, a void, a static with every kind of argument, a reference, a boolean, a double, overloads, a body
 * with loops, a switch and a try. Each says it ran in SEEN, where the check's hooks write too.
 */
public class Sample {

	public static final List<String> SEEN = new ArrayList<>();

	public int counted;

	public int count(int by) {
		SEEN.add("count");
		counted += by;
		return counted;
	}

	public void tick() {
		SEEN.add("tick");
	}

	public static long mix(long a, double b, String c, boolean d, char e, float f) {
		SEEN.add("mix");
		return a + (long) b + c.length() + (d ? 1 : 0) + e + (long) f;
	}

	public String title() {
		SEEN.add("title");
		return "game";
	}

	public boolean grabbed() {
		SEEN.add("grabbed");
		return false;
	}

	public double half(double x) {
		SEEN.add("half");
		return x / 2;
	}

	public String pick(int which) {
		return "int " + which;
	}

	public String pick(String which) {
		return "string " + which;
	}

	/** Branches, a loop, a switch and a caught exception: the original's own stack maps, kept as they were. */
	public int loops(int n) {
		int total = 0;
		for (int i = 0; i < n; i++) {
			try {
				if (i % 3 == 0) {
					throw new IllegalStateException("every third");
				}
				total += i;
			} catch (IllegalStateException e) {
				total -= 1;
			}
		}
		switch (n % 4) {
			case 0:
				return total * 2;
			case 1:
				return total + 100;
			case 2:
				long wide = total;
				return (int) (wide * wide % 1000);
			default:
				return -total;
		}
	}
}

package io.github.asgerjon.unittas.probe;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * A world's loading, step by step (debug.trace, the port's trace(); SPEC.md 19.7 step 9), for a world stuck as it
 * loads: from world.create's or world.open's start (GameWorlds.traceStart) to the player in (traceStop), each step with
 * its time and thread, as 1.7.10's TasTrace has the local connection's. The steps: the integrated server launched, its
 * first tick, the client's level, the client's player, the world loaded. Also in debug.threads' game state.
 */
final class ModernTrace {

	private static final int MAX_STEPS = 400;

	private static volatile boolean recording;
	private static volatile long start;
	private static final List<String> STEPS = Collections.synchronizedList(new ArrayList<>());
	private static final Set<String> ONCE = Collections.synchronizedSet(new HashSet<>());

	private ModernTrace() {
	}

	/** A world starts loading: the steps so far cleared, its first noted. */
	static void start() {
		STEPS.clear();
		ONCE.clear();
		start = System.nanoTime();
		recording = true;
		note("launching the integrated server");
	}

	/** The world is loaded: its last step noted, and no more till the next. */
	static void stop() {
		note("the test world is loaded");
		recording = false;
	}

	/** A step, the first time it comes while a world loads. */
	static void once(String step) {
		if (recording && ONCE.add(step)) {
			note(step);
		}
	}

	private static void note(String step) {
		if (!recording || STEPS.size() >= MAX_STEPS) {
			return;
		}
		long ms = (System.nanoTime() - start) / 1_000_000L;
		STEPS.add(String.format("%6d ms  %-28s %s", ms, "[" + Thread.currentThread().getName() + "]", step));
	}

	/** The steps of the last world's loading (the one loading now, if one is). */
	static List<String> lines() {
		synchronized (STEPS) {
			return new ArrayList<>(STEPS);
		}
	}
}

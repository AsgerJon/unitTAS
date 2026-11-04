package io.github.asgerjon.unittas;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * The local connection's steps while unitTAS's test world loads (for a world stuck at "Loading world"): each
 * step with its time and thread, from the integrated server's launch to the client joining the game. Recorded only
 * while a run loads its world (the hooks, {@code mixins.client.*Trace}, ask {@link #recording} first);
 * written to the results as loading-trace.txt, and into hang-threads.txt when the world doesn't load, so a hang names
 * the step that never came.
 */
public final class TasTrace {

	private static final int MAX_EVENTS = 400, PACKETS_EACH_WAY = 8;

	private static volatile boolean recording;
	private static long start;
	private static final List<String> EVENTS = Collections.synchronizedList(new ArrayList<>());
	private static final Set<String> ONCE = Collections.synchronizedSet(new HashSet<>());
	/** Packets noted: client reads, client sends, server reads, server sends. */
	private static final AtomicInteger[] PACKETS = {new AtomicInteger(), new AtomicInteger(), new AtomicInteger(), new AtomicInteger()};

	private TasTrace() {
	}

	public static boolean recording() {
		return recording;
	}

	static void start() {
		EVENTS.clear();
		ONCE.clear();
		for (AtomicInteger count : PACKETS) {
			count.set(0);
		}
		start = System.nanoTime();
		recording = true;
		note("launching the integrated server");
	}

	static void stop() {
		note("the test world is loaded");
		recording = false;
	}

	public static void note(String event) {
		if (!recording || EVENTS.size() >= MAX_EVENTS) {
			return;
		}
		long ms = (System.nanoTime() - start) / 1_000_000L;
		EVENTS.add(String.format("%6d ms  %-28s %s", ms, "[" + Thread.currentThread().getName() + "]", event));
	}

	/** The event, the first time its key comes. */
	public static void noteOnce(String key, String event) {
		if (recording && ONCE.add(key)) {
			note(event);
		}
	}

	/** One of the first packets each way on each side. */
	public static void packet(boolean clientSide, boolean sending, Object packet, String how) {
		if (!recording) {
			return;
		}
		if (PACKETS[(clientSide ? 0 : 2) + (sending ? 1 : 0)].incrementAndGet() <= PACKETS_EACH_WAY) {
			note((clientSide ? "client " : "server ") + (sending ? "sends " : "reads ") + packet.getClass().getSimpleName() + how);
		}
	}

	public static List<String> lines() {
		synchronized (EVENTS) {
			return new ArrayList<>(EVENTS);
		}
	}

	static String text() {
		StringBuilder out = new StringBuilder();
		for (String line : lines()) {
			out.append(line).append('\n');
		}
		return out.toString();
	}

	/** Into the results folder; returns the file's name. */
	static String write(File results, String name) {
		File file = new File(results, name);
		try {
			Files.write(file.toPath(), text().getBytes(StandardCharsets.UTF_8));
			return file.getName();
		} catch (Exception e) {
			return "nowhere (" + e + ")";
		}
	}
}

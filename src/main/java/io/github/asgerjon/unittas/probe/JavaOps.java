package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import io.github.asgerjon.unittas.TasGame;
import io.github.asgerjon.unittas.UnitTas;
import io.github.asgerjon.unittas.probe.link.Json;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.regex.Pattern;

/**
 * java.run (PROTOCOL.md 8.14), given its body at preInit: today's Java runner, unchanged, started over the socket. It
 * starts from the title screen, as a request.properties run does; each line of its report comes as a java.result
 * event; at its end the game stays up, its world is closed, and the answer names the report and its counts. While it
 * goes, the game's operations answer NotReady (Probe.request). A cancel aborts the Java run as the watch's stop does.
 */
final class JavaOps {

	/** A suite's name, as @TasSuite gives it. */
	private static final Pattern SUITE = Pattern.compile("^[A-Za-z0-9_.-]{1,64}$");
	/** A java.result's detail is cut here. */
	private static final int DETAIL_CHARS = 8000;
	/** How long an aborted run may take to stop (it finishes the step it is in, then writes its report). */
	private static final int CANCEL_SECONDS = 300;
	/** The runner's world, closed after it, like world.close's. */
	private static final int CLOSE_SECONDS = 180;

	private JavaOps() {
	}

	static void bind(Probe probe) {
		probe.op("java.run").does(JavaOps::run);
	}

	private static JsonElement run(Call call) throws ProbeException, InterruptedException {
		Probe probe = call.probe;
		if ("server".equals(probe.start.role)) {
			throw new ProbeException("Unsupported", "java.run is singleplayer only: a dedicated server has no Java runner",
				null);
		}
		Properties request = request(call);
		WorldOps.noWorldOpen(probe, "java.run");
		Snapshot snapshot = probe.snapshot;
		if (!snapshot.menu) {
			throw new ProbeException("NotReady", "java.run starts from the title screen, as a Java run does; the screen is "
				+ snapshot.screen, Json.object("state", snapshot.state, "screen", snapshot.screen));
		}
		if (!probe.javaRun.compareAndSet(false, true)) {
			throw new ProbeException("NotReady", "a java.run is going already", Json.object("java_run", true));
		}
		try {
			return runJava(probe, call, request);
		} finally {
			probe.javaRun.set(false);
		}
	}

	private static JsonElement runJava(Probe probe, Call call, Properties request) throws ProbeException,
		InterruptedException {
		CountDownLatch over = new CountDownLatch(1);
		Object[] end = new Object[3];
		TasGame.Listener listener = new TasGame.Listener() {
			@Override
			public void result(String name, String outcome, double seconds, String detail) {
				String text = detail == null ? "" : detail;
				probe.event("java.result", Json.object("test", name, "outcome", outcome, "seconds", seconds,
					"detail", text.length() > DETAIL_CHARS ? text.substring(0, DETAIL_CHARS) + "..." : text));
			}

			@Override
			public void done(File report, boolean ok, Map<String, Integer> counts) {
				end[0] = report;
				end[1] = ok;
				end[2] = counts;
				over.countDown();
			}
		};
		FutureTask<TasGame> starting = Sides.get().post(Side.CLIENT, () -> UnitTas.startForProbe(request, listener));
		TasGame game;
		try {
			game = starting.get(Sides.STALL_SECONDS, TimeUnit.SECONDS);
		} catch (TimeoutException e) {
			starting.cancel(false);
			throw new ProbeException("Stalled", "the client didn't tick to start the Java run within " + Sides.STALL_SECONDS
				+ " s", Json.object("side", "client"));
		} catch (ExecutionException e) {
			Throwable cause = e.getCause();
			throw new ProbeException("GameError", "the Java run didn't start: " + cause, Json.object("trace",
				Probe.trace(cause == null ? e : cause)));
		}
		try {
			over.await();
		} catch (InterruptedException cancelled) {
			game.cancel("java.run was cancelled");
			if (!over.await(CANCEL_SECONDS, TimeUnit.SECONDS)) {
				throw new ProbeException("TimedOut", "java.run was cancelled, but the Java run didn't stop within "
					+ CANCEL_SECONDS + " s", Json.object("seconds", CANCEL_SECONDS));
			}
			leave(probe, call);
			throw cancelled;
		}
		leave(probe, call);
		File report = (File) end[0];
		if (report == null) {
			throw new ProbeException("ProbeError", "the Java run ended without writing its report", null);
		}
		return Json.object("report", report.getAbsolutePath(), "ok", end[1], "counts", end[2]);
	}

	/** The runner's world closed, if one is open: the game is back at the title screen, as java.run found it. */
	private static void leave(Probe probe, Call call) throws InterruptedException {
		Snapshot snapshot = probe.snapshot;
		if (!snapshot.serverRunning && !"world".equals(snapshot.state)) {
			return;
		}
		try {
			WorldOps.closeOpen(probe, CLOSE_SECONDS);
		} catch (ProbeException e) {
			call.warn("the Java run's world didn't close: " + e.getMessage());
		}
	}

	/** request.properties' keys from java.run's arguments, each checked first: a refused java.run makes nothing. */
	private static Properties request(Call call) throws ProbeException {
		Properties out = new Properties();
		out.setProperty("suites", String.join(",", names(call, "suites", SUITE, "a suite's name")));
		String filter = call.string("filter", null);
		if (filter != null) {
			out.setProperty("filter", filter);
		}
		String results = call.string("results", null);
		if (results == null || !new File(results).isAbsolute()) {
			throw ProbeException.badRequest("results", "java.run needs results, the absolute folder for its report and"
				+ " screenshots, not " + call.args.get("results"));
		}
		out.setProperty("results", results);
		out.setProperty("saves", String.join(",", names(call, "saves", WorldOps.FOLDER, "a save's folder (a plain name)")));
		String oldSaves = call.string("oldsaves", null);
		if (oldSaves != null) {
			if (!new File(oldSaves).isAbsolute()) {
				throw ProbeException.badRequest("oldsaves", "oldsaves is an absolute folder, not " + oldSaves);
			}
			out.setProperty("oldsaves", oldSaves);
		}
		out.setProperty("watched", Boolean.toString(call.flag("watched", false)));
		out.setProperty("watch.pictures", Long.toString(call.number("watch_pictures", 10, 0, 3600)));
		out.setProperty("watch.decide", Long.toString(call.number("watch_decide", 300, 10, 86400)));
		return out;
	}

	/** A list of names, each matching the pattern; none when the argument isn't given. */
	private static List<String> names(Call call, String key, Pattern each, String what) throws ProbeException {
		List<String> out = new ArrayList<>();
		if (!call.has(key)) {
			return out;
		}
		JsonElement given = call.args.get(key);
		if (!given.isJsonArray()) {
			throw ProbeException.badRequest(key, key + " is a list of names, not " + given);
		}
		for (JsonElement name : (JsonArray) given) {
			if (!name.isJsonPrimitive() || !name.getAsJsonPrimitive().isString() || !each.matcher(name.getAsString()).matches()) {
				throw ProbeException.badRequest(key, key + " holds " + what + " each, not " + name);
			}
			out.add(name.getAsString());
		}
		return out;
	}
}

package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/**
 * Every operation this probe has (PROTOCOL.md 8), declared when the probe starts, so the hello lists them all. The
 * bodies that need no Minecraft class are given here; those that do are given at preInit (ClientOps), and before that
 * the game isn't ready for them anyway.
 */
final class Ops {

	/** The longest wait.until may be asked to wait, in ticks (a little under a day of the game's time at 20 a second). */
	private static final long MAX_TICKS = 2_000_000L;

	private Ops() {
	}

	static void declare(Probe probe) {
		// the session (8.1)
		// those marked alongsideJava answer while a java.run goes too: they don't touch the game (8.14)
		probe.register(Op.probe("status").whileLoading().alongsideJava().does(call -> status(call.probe)));
		probe.register(Op.probe("events.set").whileLoading().alongsideJava().does(Ops::eventsSet));
		probe.register(Op.probe("quit").whileLoading().alongsideJava().does(call -> new JsonObject())
			.then(done -> done.quit("asked")));
		probe.register(Op.probe("log.write").whileLoading().alongsideJava().does(Ops::logWrite));
		probe.register(Op.probe("cancel").whileLoading().alongsideJava().does(call -> {
			if (!call.has("id")) {
				throw ProbeException.badRequest("id", "cancel needs the id of the request to cancel");
			}
			long id = call.number("id", -1, 1, Long.MAX_VALUE);
			return Json.object("cancelled", call.probe.cancel(id));
		}));
		// ticks and waiting (8.2)
		probe.register(Op.probe("ticks.wait").alongsideJava().does(Ops::ticksWait));
		probe.register(Op.probe("wait.until").does(Ops::waitUntil));
		probe.register(Op.onSide("batch", Side.CLIENT, Side.SERVER).needingASide().does(Ops::batch));
		// debugging (8.12)
		probe.register(Op.onSide("debug.lag", Side.CLIENT, Side.SERVER).does(Ops::lag));
		probe.register(Op.probe("debug.threads").whileLoading().alongsideJava().does(Ops::threads));
		probe.register(Op.probe("debug.trace").whileLoading().alongsideJava()
			.does(call -> Json.object("lines", io.github.asgerjon.unittas.TasTrace.lines())));
		// today's Java runner (8.14), given its body at preInit (JavaOps)
		probe.register(Op.probe("java.run"));
		// worlds (8.3), given their bodies at preInit (WorldOps)
		probe.register(Op.probe("world.create"));
		probe.register(Op.probe("world.open"));
		probe.register(Op.probe("world.close"));
		probe.register(Op.onSide("world.get", Side.SERVER).reading());
		probe.register(Op.onSide("world.rules.set", Side.SERVER));
		probe.register(Op.onSide("world.time.set", Side.SERVER));
		probe.register(Op.onSide("world.weather.set", Side.SERVER));
		probe.register(Op.onSide("world.difficulty.set", Side.SERVER));
		// the player, the inventory, containers, commands, entities, screens, the mods' hooks (8.1, 8.4 to 8.9), given
		// their bodies at preInit (GameOps)
		probe.register(Op.onSide("command.run", Side.SERVER));
		probe.register(Op.onSide("player.get", Side.SERVER, Side.CLIENT).reading());
		probe.register(Op.onSide("player.teleport", Side.SERVER));
		probe.register(Op.onSide("inventory.get", Side.SERVER, Side.CLIENT).reading());
		probe.register(Op.onSide("container.get", Side.CLIENT, Side.SERVER).reading());
		probe.register(Op.onSide("entity.list", Side.SERVER, Side.CLIENT).reading());
		probe.register(Op.onSide("screen.open", Side.CLIENT));
		probe.register(Op.onSide("screen.close", Side.CLIENT));
		probe.register(Op.onSide("hooks.run", Side.SERVER, Side.CLIENT).choosing(args -> {
			String hook = Json.string(args, "hook");
			return "beforeRun".equals(hook) || "afterRun".equals(hook) ? Side.CLIENT : Side.SERVER;
		}));
		// the reset (8.4, 9.5), given its bodies at preInit (ResetOps)
		probe.register(Op.onSide("client.reset", Side.CLIENT));
		probe.register(Op.onSide("player.reset", Side.SERVER));
		probe.register(Op.onSide("world.reset", Side.SERVER));
		// the game's things (8.4 to 8.10), given their bodies at preInit (ThingOps)
		probe.register(Op.onSide("player.look", Side.CLIENT));
		probe.register(Op.onSide("inventory.set", Side.SERVER));
		probe.register(Op.onSide("block.get", Side.SERVER, Side.CLIENT).reading());
		probe.register(Op.onSide("block.set", Side.SERVER));
		probe.register(Op.onSide("entity.spawn", Side.SERVER));
		probe.register(Op.onSide("entity.get", Side.SERVER, Side.CLIENT).reading());
		probe.register(Op.onSide("entity.remove", Side.SERVER));
		probe.register(Op.onSide("key.down", Side.CLIENT));
		probe.register(Op.onSide("key.up", Side.CLIENT));
		probe.register(Op.onSide("key.tap", Side.CLIENT));
		probe.register(Op.onSide("screen.type", Side.CLIENT));
		probe.register(Op.onSide("screen.key", Side.CLIENT));
		probe.register(Op.onSide("chat.read", Side.CLIENT).reading());
		probe.register(Op.onSide("chat.send", Side.CLIENT));
		probe.register(Op.onSide("camera.set", Side.CLIENT));
		probe.register(Op.onSide("sound.play", Side.CLIENT));
		probe.register(Op.onSide("screenshot", Side.CLIENT));
		// reflection (8.11), given its bodies at preInit (ThingOps); the refs are the probe's own
		probe.register(Op.onSide("reflect.get", Side.SERVER, Side.CLIENT).reading().needingASide());
		probe.register(Op.onSide("reflect.set", Side.SERVER, Side.CLIENT).needingASide());
		probe.register(Op.probe("refs.release").alongsideJava().does(call -> {
			com.google.gson.JsonElement ids = call.args.get("refs");
			if (ids == null || !ids.isJsonArray()) {
				throw ProbeException.badRequest("refs", "refs.release needs refs, a list of ref numbers");
			}
			for (com.google.gson.JsonElement id : ids.getAsJsonArray()) {
				call.probe.refs.release(id.getAsInt(), "refs.release released it");
			}
			return new JsonObject();
		}));
		probe.register(Op.probe("refs.clear").alongsideJava().does(call -> {
			call.probe.refs.clear("refs.clear released it");
			return new JsonObject();
		}));
		// the client's own, given their bodies at preInit (ClientOps)
		probe.register(Op.onSide("screen.get", Side.CLIENT).reading());
	}

	// ---------------------------------------------------------------- the session

	private static JsonElement status(Probe probe) {
		Snapshot snapshot = probe.snapshot;
		Sides sides = Sides.get();
		long now = System.currentTimeMillis();
		Runtime runtime = Runtime.getRuntime();
		long megabyte = 1024L * 1024L;
		boolean server = snapshot.serverRunning;
		long clientAt = sides.tickedAt(Side.CLIENT);
		long serverAt = sides.tickedAt(Side.SERVER);
		JsonObject window = snapshot.ready ? Json.object(
			"title", snapshot.windowTitle,
			"width", snapshot.width,
			"height", snapshot.height,
			"pointer_grabbed", snapshot.pointerGrabbed) : null;
		return Json.object(
			"state", snapshot.state,
			"role", probe.start.role,
			"sides", server ? Arrays.asList("client", "server") : Collections.singletonList("client"),
			"joined", null,
			"players", Collections.emptyList(),
			"screen", snapshot.screen,
			"paused", snapshot.paused,
			"ticks", Json.object("client", sides.ticks(Side.CLIENT), "server", server ? sides.ticks(Side.SERVER) : null),
			"ago_ms", Json.object(
				"client", clientAt == 0 ? null : now - clientAt,
				"server", server && serverAt != 0 ? now - serverAt : null),
			"world", server ? Json.object("folder", snapshot.worldFolder, "dimension", snapshot.dimension) : null,
			"window", window,
			"memory_mb", Json.object(
				"used", (runtime.totalMemory() - runtime.freeMemory()) / megabyte,
				"max", runtime.maxMemory() / megabyte),
			"refs", probe.refs.size());
	}

	private static JsonElement eventsSet(Call call) throws ProbeException {
		Events events = call.probe.events;
		// every argument checked before any is set: a bad request changes nothing
		Boolean chat = call.has("chat") ? call.flag("chat", true) : null;
		Boolean sound = call.has("sound") ? call.flag("sound", true) : null;
		Boolean screen = call.has("screen") ? call.flag("screen", true) : null;
		String log = call.string("log", null);
		if (log != null && !Events.LOG_LEVELS.contains(log)) {
			throw ProbeException.badRequest("log", "log is one of " + Events.LOG_LEVELS + ", not " + log);
		}
		if (chat != null) {
			events.chat = chat;
		}
		if (sound != null) {
			events.sound = sound;
		}
		if (screen != null) {
			events.screen = screen;
		}
		if (log != null) {
			events.log = log;
		}
		return Json.object("chat", events.chat, "sound", events.sound, "screen", events.screen, "log", events.log);
	}

	// ---------------------------------------------------------------- ticks and waiting

	/** Throws NotReady when the side has no thread: no server while no world is open. */
	static void needThread(Probe probe, Side side) throws ProbeException {
		if (side == Side.SERVER && !probe.snapshot.serverRunning) {
			throw new ProbeException("NotReady", "no world is open, so there is no server side to wait for",
				Json.object("state", probe.snapshot.state, "screen", probe.snapshot.screen));
		}
	}

	private static int stallSeconds(Call call) throws ProbeException {
		return (int) call.number("stall_seconds", Sides.STALL_SECONDS, 1, 3600);
	}

	private static JsonElement ticksWait(Call call) throws ProbeException, InterruptedException {
		JsonObject until = call.object("until");
		Side side;
		long target;
		if (until != null) {
			if (until.entrySet().size() != 1) {
				throw ProbeException.badRequest("until", "until names one side's tick: {\"client\": n} or {\"server\": n}");
			}
			String name = until.entrySet().iterator().next().getKey();
			side = Side.of(name);
			if (side == null) {
				throw ProbeException.badRequest("until", "until's side is client or server, not " + name);
			}
			if (call.has("side") && call.sideArg("side", side) != side) {
				throw ProbeException.badRequest("side", "side and until name different sides");
			}
			target = call.with(until, null).number(name, 0, 0, Long.MAX_VALUE);
		} else {
			side = call.sideArg("side", Side.CLIENT);
			target = -1;
		}
		long n = call.number("n", 1, 0, 100_000_000L);
		int stall = stallSeconds(call);
		needThread(call.probe, side);
		Sides sides = Sides.get();
		long from = sides.ticks(side);
		long goal = target >= 0 ? target : from + n;
		long waited;
		try {
			waited = sides.waitUntilTick(side, goal, stall);
		} catch (Sides.Stalled stalled) {
			throw stalled(call.probe, stalled);
		}
		// the count goes up one a tick, so it passed through the goal exactly: that is the tick it was met at
		return Json.object("waited_ms", waited, "from", from, "tick", Math.max(goal, from));
	}

	/** A side that stopped ticking, as the protocol's Stalled error. */
	static ProbeException stalled(Probe probe, Sides.Stalled stalled) {
		boolean paused = probe.snapshot.paused;
		String screen = probe.snapshot.screen;
		String message = stalled.getMessage() + (paused && screen != null ? " (the game is paused: " + screen + " is open)" : "");
		return new ProbeException("Stalled", message, Json.object(
			"side", stalled.side.wire,
			"since_tick_ms", stalled.sinceTickMs,
			"screen", screen,
			"paused", paused));
	}

	/**
	 * wait.until: an instant read checked at the end of every tick of the side, by the side's thread itself, so no tick
	 * goes unchecked (a check from here, between messages, could miss one). Not holding after max_ticks checks is an
	 * answer, not an error: the test says what it saw last.
	 */
	private static JsonElement waitUntil(Call call) throws ProbeException, InterruptedException {
		Side side = call.sideArg("side", Side.CLIENT);
		String opName = call.string("op", null);
		if (opName == null) {
			throw ProbeException.badRequest("op", "wait.until needs the op to check");
		}
		Op inner = call.probe.op(opName);
		if (inner == null) {
			throw ProbeException.badRequest("op", "this probe has no operation " + opName);
		}
		if (!inner.instant() || !inner.reads()) {
			throw ProbeException.badRequest("op", opName + " can't be checked every tick: wait.until takes an instant read"
				+ " (" + opName + (inner.instant() ? " changes the game" : " waits") + ")");
		}
		if (!inner.allows(side)) {
			throw ProbeException.badRequest("op", opName + " doesn't run on the " + side.wire);
		}
		JsonObject innerArgs = call.has("args") ? call.object("args") : new JsonObject();
		Check test = Check.of(call.args.get("test"));
		long maxTicks = call.number("max_ticks", 100, 1, MAX_TICKS);
		int stall = stallSeconds(call);
		needThread(call.probe, side);
		Call innerCall = call.with(innerArgs, side);
		CompletableFuture<JsonObject> outcome = new CompletableFuture<>();
		Sides sides = Sides.get();
		long[] checks = {0};
		sides.everyTick(side, () -> {
			if (outcome.isDone()) {
				return true;
			}
			JsonElement value;
			try {
				value = inner.run(innerCall);
			} catch (ProbeException | InterruptedException | RuntimeException e) {
				outcome.completeExceptionally(e);
				return true;
			}
			checks[0]++;
			if (test.holds(value)) {
				outcome.complete(Json.object("held", true, "tick", sides.ticks(side), "checks", checks[0], "value", value));
				return true;
			}
			if (checks[0] >= maxTicks) {
				outcome.complete(Json.object("held", false, "checks", checks[0], "value", value));
				return true;
			}
			return false;
		});
		call.running.onCancel(() -> outcome.cancel(false));
		try {
			while (true) {
				long since = System.currentTimeMillis() - sides.tickedAt(side);
				if (since > stall * 1000L) {
					outcome.cancel(false);
					throw stalled(call.probe, new Sides.Stalled(side, since, stall));
				}
				try {
					return outcome.get(500, TimeUnit.MILLISECONDS);
				} catch (TimeoutException e) {
					// checked again at the next tick
				}
			}
		} catch (ExecutionException e) {
			Throwable cause = e.getCause();
			if (cause instanceof ProbeException) {
				throw (ProbeException) cause;
			}
			throw new ProbeException("ProbeError", "wait.until's check failed: " + cause, null);
		} catch (java.util.concurrent.CancellationException e) {
			throw new InterruptedException("cancelled");
		} finally {
			outcome.cancel(false);
		}
	}

	/**
	 * batch: instant operations on one side, in one tick, in order (PROTOCOL.md 4.3). All of them are checked before any
	 * runs: an operation that isn't instant, isn't the side's, or isn't there makes the whole batch a BadRequest.
	 */
	private static JsonElement batch(Call call) throws ProbeException, InterruptedException {
		JsonElement list = call.args.get("ops");
		if (list == null || !list.isJsonArray()) {
			throw ProbeException.badRequest("ops", "batch needs ops, a list of {\"op\": ..., \"args\": ...}");
		}
		boolean stopOnError = call.flag("stop_on_error", true);
		List<Op> ops = new ArrayList<>();
		List<JsonObject> args = new ArrayList<>();
		int index = 0;
		for (JsonElement entry : list.getAsJsonArray()) {
			String where = "batch entry " + index++;
			if (!entry.isJsonObject() || Json.string(entry.getAsJsonObject(), "op") == null) {
				throw ProbeException.badRequest("ops", where + " has no op");
			}
			JsonObject each = entry.getAsJsonObject();
			String name = Json.string(each, "op");
			Op op = call.probe.op(name);
			if (op == null) {
				throw ProbeException.badRequest("ops", where + ": this probe has no operation " + name);
			}
			if (!op.instant() || op.name.equals("batch")) {
				throw ProbeException.badRequest("ops", where + ": " + name + " isn't instant, so it can't be in a batch");
			}
			if (!op.allows(call.side)) {
				throw ProbeException.badRequest("ops", where + ": " + name + " doesn't run on the " + call.side.wire);
			}
			JsonElement given = each.get("args");
			if (given != null && !given.isJsonNull() && !given.isJsonObject()) {
				throw ProbeException.badRequest("ops", where + ": its args must be an object");
			}
			ops.add(op);
			args.add(given == null || given.isJsonNull() ? new JsonObject() : given.getAsJsonObject());
		}
		JsonArray results = new JsonArray();
		boolean failed = false;
		for (int i = 0; i < ops.size(); i++) {
			JsonObject result;
			if (failed && stopOnError) {
				result = Json.object("ok", false, "error", Json.object("type", "Cancelled", "message",
					"not run: an earlier operation in the batch failed"));
			} else {
				try {
					result = Json.object("ok", true, "value", ops.get(i).run(call.with(args.get(i), call.side)));
				} catch (ProbeException e) {
					failed = true;
					JsonObject error = Json.object("type", e.type, "message", e.getMessage());
					if (e.fields != null) {
						for (java.util.Map.Entry<String, JsonElement> field : e.fields.entrySet()) {
							error.add(field.getKey(), field.getValue());
						}
					}
					result = Json.object("ok", false, "error", error);
				}
			}
			result.add("at", call.probe.at());
			results.add(result);
		}
		return results;
	}

	// ---------------------------------------------------------------- debugging

	/** debug.lag: the side sleeps a while in each of its next ticks: a slow game on purpose, for the stall rule's tests. */
	// ---------------------------------------------------------------- the log and debugging

	/** A line into the game's log under the logger unitTAS (8.1): the tests' edges, for a person reading latest.log. */
	private static JsonElement logWrite(Call call) throws ProbeException {
		String message = call.string("message", null);
		if (message == null) {
			throw ProbeException.badRequest("message", "log.write needs a message, a string");
		}
		String level = call.string("level", "info");
		switch (level) {
			case "debug":
				Probe.LOG.debug("{}", message);
				break;
			case "info":
				Probe.LOG.info("{}", message);
				break;
			case "warn":
				Probe.LOG.warn("{}", message);
				break;
			case "error":
				Probe.LOG.error("{}", message);
				break;
			default:
				throw ProbeException.badRequest("level", "level is debug, info, warn or error, not " + level);
		}
		return new JsonObject();
	}

	/** How long the game's state may take to read before debug.threads goes without it. */
	private static final int STATE_SECONDS = 2;

	/**
	 * Every thread's stack with its locks, after the game's state, as hang-threads.txt (8.12). The threads come from the
	 * JDK alone. The game's state is read on a thread of its own, for 2 s at most: a lock a stuck game thread holds (the
	 * server's connection list, say) can't hold this answer up, and the threads then show who holds what.
	 */
	private static JsonElement threads(Call call) throws InterruptedException {
		java.util.function.Supplier<String> state = call.probe.gameState;
		String game;
		if (state == null) {
			game = "the game's state: not known yet (it is, from the mod's preInit on)\n";
		} else {
			java.util.concurrent.FutureTask<String> read = new java.util.concurrent.FutureTask<>(state::get);
			Thread reader = new Thread(read, "unitTAS probe, the game's state");
			reader.setDaemon(true);
			reader.start();
			try {
				game = read.get(STATE_SECONDS, TimeUnit.SECONDS);
			} catch (TimeoutException e) {
				game = "the game's state: unreadable within " + STATE_SECONDS + " s (a lock it needs is held: the threads"
					+ " below say by whom)\n";
			} catch (ExecutionException e) {
				game = "the game's state: unreadable (" + e.getCause() + ")\n";
			}
		}
		return Json.object("text", game + "\n" + Threads.dump());
	}

	private static JsonElement lag(Call call) throws ProbeException {
		if (!call.has("ms")) {
			throw ProbeException.badRequest("ms", "debug.lag needs ms, how long each tick sleeps");
		}
		long ms = call.number("ms", -1, 1, 60_000);
		long ticks = call.number("ticks", 1, 1, 10_000);
		long[] left = {ticks};
		Sides.get().everyTick(call.side, () -> {
			try {
				Thread.sleep(ms);
			} catch (InterruptedException e) {
				Thread.currentThread().interrupt();
				return true;
			}
			return --left[0] <= 0;
		});
		return new JsonObject();
	}
}

package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;

import java.io.File;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.FutureTask;
import java.util.regex.Pattern;

/**
 * The world operations' bodies (PROTOCOL.md 8.3), version-free (SPEC.md 12, D5): the game's own calls are the port's
 * {@link GameWorlds}, and a port's client hooks bind these. Making, opening and closing a world are the probe's own:
 * the client thread is busy for a while in each (it waits for the integrated server to start or stop), so they don't
 * go by the stall rule; they watch from the probe's thread until the player is in (or out) and settled, or until their
 * own max_seconds, and say once a second how far they are. The rest run on the server thread.
 */
final class WorldOps {

	/** A save's folder: a plain name in the game's saves. */
	static final Pattern FOLDER = Pattern.compile("^[A-Za-z0-9_.-]{1,64}$");
	/** The test world's folder, name and seed, unless asked otherwise. */
	static final String TEST_FOLDER = "unittas";
	static final String TEST_NAME = "unitTAS";
	static final long SEED = 20261029L;
	/** The protocol's names: the world types, the game modes, the difficulties. */
	static final List<String> TYPES = Arrays.asList("default", "flat", "large_biomes", "amplified");
	static final List<String> GAME_MODES = Arrays.asList("survival", "creative", "adventure");
	static final List<String> DIFFICULTIES = Arrays.asList("peaceful", "easy", "normal", "hard");

	private WorldOps() {
	}

	/** The world operations' bodies, from the port's client hooks: its worlds are the port's. */
	static void bind(Probe probe) {
		GameWorlds worlds = probe.port.worlds();
		probe.op("world.create").does(call -> create(call, worlds));
		probe.op("world.open").does(call -> open(call, worlds));
		probe.op("world.close").does(WorldOps::close);
		probe.op("world.difficulty.set").does(call -> difficulty(call, worlds));
		bindServer(probe, worlds);
	}

	/**
	 * The server thread's world operations alone, on those worlds: a dedicated server's (SPEC.md 19.7 step 10b), which
	 * makes, opens and closes no world, and sets no difficulty (it sets the client's option too).
	 */
	static void bindServer(Probe probe, GameWorlds worlds) {
		probe.op("world.get").does(call -> worlds.describe());
		probe.op("world.rules.set").does(call -> rules(call, worlds));
		probe.op("world.time.set").does(call -> time(call, worlds));
		probe.op("world.weather.set").does(call -> weather(call, worlds));
		probe.op("world.prepare").does(call -> {
			worlds.prepare();
			return new JsonObject();
		});
	}

	// ---------------------------------------------------------------- making, opening, closing

	private static String folder(Call call, String otherwise) throws ProbeException {
		String folder = call.string("folder", otherwise);
		if (folder == null) {
			throw ProbeException.badRequest("folder", "the save's folder is needed");
		}
		if (!FOLDER.matcher(folder).matches()) {
			throw ProbeException.badRequest("folder", "a save's folder is a plain name (letters, digits, _ . -), not " + folder);
		}
		return folder;
	}

	static void noWorldOpen(Probe probe, String what) throws ProbeException {
		Snapshot snapshot = probe.snapshot;
		if (snapshot.serverRunning || "world".equals(snapshot.state) || snapshot.changing) {
			throw new ProbeException("NotReady", what + " needs the title screen: a world is open"
				+ (snapshot.worldFolder == null ? "" : " (" + snapshot.worldFolder + ")") + "; close it first",
				Json.object("state", snapshot.state, "screen", snapshot.screen));
		}
	}

	/** A name the protocol lists, or BadRequest naming them. */
	private static String oneOf(Call call, String key, String otherwise, List<String> names) throws ProbeException {
		String given = call.string(key, otherwise);
		if (given == null || !names.contains(given)) {
			throw ProbeException.badRequest(key, key + " is " + String.join(", ", names.subList(0, names.size() - 1))
				+ " or " + names.get(names.size() - 1) + ", not " + given);
		}
		return given;
	}

	/** world.create's layers: [{"id": …, "meta": n, "count": n}, …], bottom up, at least one. */
	private static java.util.List<FlatLayer> layers(Call call) throws ProbeException {
		com.google.gson.JsonElement given = call.args.get("layers");
		if (given == null || !given.isJsonArray() || given.getAsJsonArray().size() == 0) {
			throw ProbeException.badRequest("layers", "layers is a list of {\"id\", \"meta\", \"count\"}, bottom up, at least one");
		}
		java.util.List<FlatLayer> out = new java.util.ArrayList<>();
		for (com.google.gson.JsonElement each : given.getAsJsonArray()) {
			if (!each.isJsonObject()) {
				throw ProbeException.badRequest("layers", "a layer is {\"id\", \"meta\", \"count\"}, not " + each);
			}
			com.google.gson.JsonObject layer = each.getAsJsonObject();
			String id = Json.string(layer, "id");
			int meta = layer.has("meta") ? layer.get("meta").getAsInt() : 0;
			int count = layer.has("count") ? layer.get("count").getAsInt() : 1;
			if (id == null || meta < 0 || count < 1) {
				throw ProbeException.badRequest("layers", "a layer is a block's id, a meta of 0 or more, a count of 1 or more: " + each);
			}
			out.add(new FlatLayer(id, meta, count));
		}
		return out;
	}

	private static JsonElement create(Call call, GameWorlds worlds) throws ProbeException, InterruptedException {
		Probe probe = call.probe;
		String folder = folder(call, TEST_FOLDER);
		String name = call.string("name", TEST_NAME);
		long seed = call.number("seed", SEED, Long.MIN_VALUE, Long.MAX_VALUE);
		String type = oneOf(call, "type", "flat", TYPES);
		String generator;
		if (call.has("layers")) {
			// a flat world by its layers and biome, which the port writes as its version's own text (SPEC.md 17.4)
			if (call.has("generator")) {
				throw ProbeException.badRequest("layers", "a flat world is given by its layers or by generator text, not both");
			}
			if (!"flat".equals(type)) {
				throw ProbeException.badRequest("layers", "layers are a flat world's, not a " + type + " world's");
			}
			generator = worlds.flatLayers(layers(call), call.string("biome", ""));
		} else {
			generator = call.string("generator", "flat".equals(type) ? worlds.testLayers() : "");
		}
		worlds.checkGenerator(type, generator);
		String mode = oneOf(call, "game_mode", "creative", GAME_MODES);
		boolean cheats = call.flag("cheats", true);
		boolean structures = call.flag("structures", true);
		long settle = call.number("settle_ticks", 40, 0, 72000);
		long maxSeconds = call.number("max_seconds", 180, 1, 3600);
		String pictures = pictures(call);
		noWorldOpen(probe, "world.create");
		if (new File(probe.gameDir, "saves/" + folder).exists()) {
			throw new ProbeException("Exists", "saves/" + folder + " is there already: world.create makes a new world",
				Json.object("what", folder));
		}
		long started = System.currentTimeMillis();
		FutureTask<Void> launch = Sides.get().post(Side.CLIENT, () -> {
			worlds.traceStart();
			worlds.create(folder, name, seed, type, generator, mode, cheats, structures);
			return null;
		});
		watchIn(call, worlds, folder, launch, settle, maxSeconds, started, pictures);
		JsonElement spawn = onServer(() -> worlds.describe().get("spawn"));
		return Json.object("folder", folder, "load_ms", System.currentTimeMillis() - started, "spawn", spawn);
	}

	private static JsonElement open(Call call, GameWorlds worlds) throws ProbeException, InterruptedException {
		Probe probe = call.probe;
		String folder = folder(call, null);
		long settle = call.number("settle_ticks", 40, 0, 72000);
		long maxSeconds = call.number("max_seconds", 180, 1, 3600);
		String pictures = pictures(call);
		noWorldOpen(probe, "world.open");
		if (!new File(probe.gameDir, "saves/" + folder + "/level.dat").isFile()) {
			throw new ProbeException("NotFound", "no save called " + folder + " in " + new File(probe.gameDir, "saves"),
				Json.object("what", folder));
		}
		long started = System.currentTimeMillis();
		FutureTask<Void> launch = Sides.get().post(Side.CLIENT, () -> {
			worlds.traceStart();
			worlds.open(folder);
			return null;
		});
		watchIn(call, worlds, folder, launch, settle, maxSeconds, started, pictures);
		JsonElement name = onServer(() -> worlds.describe().get("name"));
		return Json.object("folder", folder, "name", name, "load_ms", System.currentTimeMillis() - started);
	}

	/**
	 * Watches the client going into the world: in on both sides, past the terrain screen, then settled for the ticks
	 * asked. A world event says how far it is once a second; max_seconds gives TimedOut, with the loading trace.
	 * What the game shows is watched too (Opening): a client left at the title screen while its server runs is a
	 * dropped login, pictured (into the request's `pictures` folder), left and opened again once; dropped again, it is
	 * Disconnected.
	 */
	private static void watchIn(Call call, GameWorlds worlds, String folder, FutureTask<Void> launch, long settle,
		long maxSeconds, long started, String pictures) throws ProbeException, InterruptedException {
		Probe probe = call.probe;
		Snapshot snapshot = probe.snapshot;
		Sides sides = Sides.get();
		Opening opening = new Opening();
		int dropped = 0;
		snapshot.changing = true;
		try {
			long nextEvent = started;
			long inSince = -1;
			while (true) {
				failed(launch, "open " + folder);
				long now = System.currentTimeMillis();
				String hung = launch.isDone() && opening.dropped(snapshot.menu, snapshot.serverRunning, snapshot.inWorld,
					sides.ticks(Side.CLIENT), sides.ticks(Side.SERVER)) ? Opening.DROPPED : null;
				if (hung != null) {
					dropped++;
					String picture = dropPicture(worlds, pictures, folder, dropped);
					probe.event("world", Json.object("state", "dropped", "folder", folder, "ms", now - started, "screen",
						snapshot.screen, "picture", picture));
					if (dropped > Opening.RETRIES) {
						throw new ProbeException("Disconnected", hung + "; and again after it was opened once more"
							+ (picture == null ? "" : " (its picture: " + picture + ")"), Json.object("reason", hung,
							"picture", picture, "screen", snapshot.screen));
					}
					call.warn(hung + ": left and opened again" + (picture == null ? "" : " (its picture: " + picture + ")"));
					// left as Save and Quit leaves a world (its server stopped), then the folder opened again: world.create's
					// world was made by its first try
					launch = Sides.get().post(Side.CLIENT, () -> {
						worlds.close();
						worlds.open(folder);
						return null;
					});
					opening.reset();
					continue;
				}
				if (snapshot.inWorld) {
					long ticks = sides.ticks(Side.CLIENT);
					if (inSince < 0) {
						inSince = ticks;
					}
					if (ticks - inSince >= settle) {
						break;
					}
				} else {
					inSince = -1;
				}
				if (now - started > maxSeconds * 1000L) {
					throw new ProbeException("TimedOut", folder + " didn't open within " + maxSeconds + " s", Json.object(
						"seconds", maxSeconds, "screen", snapshot.screen, "trace", probe.port.trace()));
				}
				if (now >= nextEvent) {
					probe.event("world", Json.object("state", "loading", "folder", folder, "ms", now - started,
						"screen", snapshot.screen));
					nextEvent = now + 1000;
				}
				Thread.sleep(50);
			}
			// the state the operation ends in, at once: the next client tick would say so too, but status may come first
			snapshot.state = "world";
		} finally {
			snapshot.changing = false;
		}
		worlds.traceStop();
		probe.event("world", Json.object("state", "open", "folder", folder, "ms", System.currentTimeMillis() - started));
	}

	/** The request's `pictures` folder, for the opening guard's pictures: an absolute folder, or null for none. */
	private static String pictures(Call call) throws ProbeException {
		String pictures = call.string("pictures", null);
		if (pictures != null && !new File(pictures).isAbsolute()) {
			throw ProbeException.badRequest("pictures", "pictures is an absolute folder, not " + pictures);
		}
		return pictures;
	}

	/** The dropped opening's picture, into the `pictures` folder; its path, or null (none asked for, or it failed). */
	private static String dropPicture(GameWorlds worlds, String pictures, String folder, int dropped) {
		if (pictures == null) {
			return null;
		}
		File file = new File(pictures, folder + "-dropped-" + dropped + ".png");
		try {
			Sides.get().run(Side.CLIENT, () -> {
				worlds.picture(file);
				return null;
			}, Sides.STALL_SECONDS, queued -> { });
			return file.getAbsolutePath();
		} catch (Exception e) {
			// a picture is evidence, not the operation: its failure is said by its absence
			return null;
		}
	}

	private static JsonElement close(Call call) throws ProbeException, InterruptedException {
		Probe probe = call.probe;
		Snapshot snapshot = probe.snapshot;
		long maxSeconds = call.number("max_seconds", 180, 1, 3600);
		if (!snapshot.serverRunning && !"world".equals(snapshot.state)) {
			throw new ProbeException("NotReady", "no world is open to close", Json.object("state", snapshot.state,
				"screen", snapshot.screen));
		}
		return Json.object("close_ms", closeOpen(probe, maxSeconds));
	}

	/**
	 * Leaves the open world for the title screen, as the pause menu's button does, and waits until the server has
	 * stopped (its writes on disk) and the title shows: world.close's work, and java.run's after the Java run. Its ms.
	 */
	static long closeOpen(Probe probe, long maxSeconds) throws ProbeException, InterruptedException {
		GameWorlds worlds = probe.port.worlds();
		Snapshot snapshot = probe.snapshot;
		String folder = snapshot.worldFolder;
		long started = System.currentTimeMillis();
		snapshot.changing = true;
		try {
			probe.event("world", Json.object("state", "closing", "folder", folder, "ms", 0));
			FutureTask<Void> leave = Sides.get().post(Side.CLIENT, () -> {
				worlds.close();
				return null;
			});
			// out once the server has stopped (its saves on disk: it flushes its writes as it stops) and the title shows
			while (!(leave.isDone() && snapshot.serverStopped && snapshot.menu && !snapshot.inWorld)) {
				failed(leave, "close " + folder);
				if (System.currentTimeMillis() - started > maxSeconds * 1000L) {
					throw new ProbeException("TimedOut", folder + " didn't close within " + maxSeconds + " s",
						Json.object("seconds", maxSeconds, "screen", snapshot.screen));
				}
				Thread.sleep(50);
			}
			snapshot.state = "menu";
		} finally {
			snapshot.changing = false;
		}
		long ms = System.currentTimeMillis() - started;
		probe.refs.clear(Side.SERVER, "its world (" + folder + ") closed");
		probe.event("world", Json.object("state", "closed", "folder", folder, "ms", ms));
		return ms;
	}

	/**
	 * A world step that threw: the game's failure (a mod's world load, say), as GameError with its trace; a
	 * ProbeException the port threw is the answer as it is (a request the game refused, say).
	 */
	private static void failed(FutureTask<Void> step, String what) throws ProbeException {
		if (!step.isDone()) {
			return;
		}
		try {
			step.get();
		} catch (ExecutionException e) {
			Throwable cause = e.getCause();
			if (cause instanceof ProbeException) {
				throw (ProbeException) cause;
			}
			throw new ProbeException("GameError", "the game failed to " + what + ": " + cause, Json.object(
				"exception", cause == null ? null : cause.getClass().getName(), "trace", Probe.trace(cause == null ? e : cause)));
		} catch (CancellationException | InterruptedException e) {
			throw new ProbeException("ProbeError", "the step to " + what + " never ran", null);
		}
	}

	private static JsonElement onServer(Callable<JsonElement> read) throws ProbeException, InterruptedException {
		try {
			return Sides.get().run(Side.SERVER, read, Sides.STALL_SECONDS, null);
		} catch (InterruptedException | RuntimeException e) {
			throw e;
		} catch (Exception e) {
			throw new ProbeException("ProbeError", "reading the world failed: " + e, null);
		}
	}

	// ---------------------------------------------------------------- the server thread

	private static JsonElement rules(Call call, GameWorlds worlds) throws ProbeException {
		JsonObject given = call.object("rules");
		if (given == null || given.entrySet().isEmpty()) {
			throw ProbeException.badRequest("rules", "rules names the game rules to set, by this game's own names, each"
				+ " with its value: {\"<rule>\": false}");
		}
		Map<String, String> values = new LinkedHashMap<>();
		for (Map.Entry<String, JsonElement> rule : given.entrySet()) {
			JsonElement value = rule.getValue();
			if (!value.isJsonPrimitive()) {
				throw ProbeException.badRequest("rules", rule.getKey() + " is set to true, false, a number or a string");
			}
			String text = value.getAsJsonPrimitive().isNumber() && value.getAsDouble() == Math.floor(value.getAsDouble())
				? Long.toString(value.getAsLong()) : value.getAsString();
			values.put(rule.getKey(), text);
		}
		List<String> unknown = worlds.unknownRules(values.keySet());
		if (!unknown.isEmpty()) {
			throw new ProbeException("NotFound", "this game has no rule " + String.join(", ", unknown)
				+ " (the probe never makes one)", Json.object("what", unknown));
		}
		worlds.setRules(values);
		return new JsonObject();
	}

	private static JsonElement time(Call call, GameWorlds worlds) throws ProbeException {
		if (!call.has("time")) {
			throw ProbeException.badRequest("time", "world.time.set needs the time");
		}
		long time = call.number("time", 0, 0, Long.MAX_VALUE);
		JsonElement dimension = call.has("dimension") ? call.args.get("dimension") : JsonNull.INSTANCE;
		if (!dimension.isJsonNull() && !worlds.knowsDimension(dimension)) {
			throw new ProbeException("NotFound", "no dimension " + dimension, Json.object("what", dimension));
		}
		worlds.setTime(time, dimension);
		return new JsonObject();
	}

	private static JsonElement weather(Call call, GameWorlds worlds) throws ProbeException {
		String weather = call.string("weather", null);
		boolean hold = call.flag("hold", true);
		if (weather == null) {
			throw ProbeException.badRequest("weather", "world.weather.set needs the weather: clear, rain or thunder");
		}
		switch (weather) {
			case "clear":
				worlds.setWeather(false, false, hold);
				break;
			case "rain":
				worlds.setWeather(true, false, hold);
				break;
			case "thunder":
				worlds.setWeather(true, true, hold);
				break;
			default:
				throw ProbeException.badRequest("weather", "the weather is clear, rain or thunder, not " + weather);
		}
		return new JsonObject();
	}

	private static JsonElement difficulty(Call call, GameWorlds worlds) throws ProbeException {
		String name = call.string("difficulty", null);
		String difficulty = name == null ? "" : name.toLowerCase(Locale.ROOT);
		if (!DIFFICULTIES.contains(difficulty)) {
			throw ProbeException.badRequest("difficulty", "difficulty is peaceful, easy, normal or hard, not " + name);
		}
		worlds.setDifficulty(difficulty);
		// the client's own option, as the game's difficulty button sets both
		Sides.get().post(Side.CLIENT, () -> {
			worlds.clientDifficulty(difficulty);
			return null;
		});
		return new JsonObject();
	}
}

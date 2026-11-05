package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.TasTrace;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.world.EnumDifficulty;
import net.minecraft.world.WorldSettings;
import net.minecraft.world.WorldType;

import java.io.File;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.FutureTask;
import java.util.regex.Pattern;

/**
 * The world operations' bodies (PROTOCOL.md 8.3), given at preInit. Making, opening and closing a world are the probe's
 * own: the client thread is busy for a while in each (it waits for the integrated server to start or stop), so they
 * don't go by the stall rule; they watch from the probe's thread until the player is in (or out) and settled, or until
 * their own max_seconds, and say once a second how far they are. The rest run on the server thread.
 */
final class WorldOps {

	/** A save's folder: a plain name in the game's saves. */
	static final Pattern FOLDER = Pattern.compile("^[A-Za-z0-9_.-]{1,64}$");

	private WorldOps() {
	}

	static void bind(Probe probe) {
		probe.op("world.create").does(WorldOps::create);
		probe.op("world.open").does(WorldOps::open);
		probe.op("world.close").does(WorldOps::close);
		probe.op("world.get").does(call -> Worlds.describe());
		probe.op("world.rules.set").does(WorldOps::rules);
		probe.op("world.time.set").does(WorldOps::time);
		probe.op("world.weather.set").does(WorldOps::weather);
		probe.op("world.difficulty.set").does(WorldOps::difficulty);
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

	private static JsonElement create(Call call) throws ProbeException, InterruptedException {
		Probe probe = call.probe;
		String folder = folder(call, Worlds.FOLDER);
		String name = call.string("name", Worlds.NAME);
		long seed = call.number("seed", Worlds.SEED, Long.MIN_VALUE, Long.MAX_VALUE);
		String typeName = call.string("type", "flat");
		WorldType type = Worlds.type(typeName);
		if (type == null) {
			throw ProbeException.badRequest("type", "type is default, flat, large_biomes or amplified, not " + typeName);
		}
		String generator = call.string("generator", type == WorldType.FLAT ? Worlds.FLAT_LAYERS : "");
		String modeName = call.string("game_mode", "creative");
		WorldSettings.GameType mode;
		switch (modeName) {
			case "survival":
				mode = WorldSettings.GameType.SURVIVAL;
				break;
			case "creative":
				mode = WorldSettings.GameType.CREATIVE;
				break;
			case "adventure":
				mode = WorldSettings.GameType.ADVENTURE;
				break;
			default:
				throw ProbeException.badRequest("game_mode", "game_mode is survival, creative or adventure, not " + modeName);
		}
		boolean cheats = call.flag("cheats", true);
		boolean structures = call.flag("structures", true);
		long settle = call.number("settle_ticks", 40, 0, 72000);
		long maxSeconds = call.number("max_seconds", 180, 1, 3600);
		noWorldOpen(probe, "world.create");
		if (new File(probe.gameDir, "saves/" + folder).exists()) {
			throw new ProbeException("Exists", "saves/" + folder + " is there already: world.create makes a new world",
				Json.object("what", folder));
		}
		long started = System.currentTimeMillis();
		FutureTask<Void> launch = Sides.get().post(Side.CLIENT, () -> {
			TasTrace.start();
			Worlds.create(Minecraft.getMinecraft(), folder, name, seed, type, generator, mode, cheats, structures);
			return null;
		});
		watchIn(probe, folder, launch, settle, maxSeconds, started);
		JsonElement spawn = onServer(() -> Worlds.describe().get("spawn"));
		return Json.object("folder", folder, "load_ms", System.currentTimeMillis() - started, "spawn", spawn);
	}

	private static JsonElement open(Call call) throws ProbeException, InterruptedException {
		Probe probe = call.probe;
		String folder = folder(call, null);
		long settle = call.number("settle_ticks", 40, 0, 72000);
		long maxSeconds = call.number("max_seconds", 180, 1, 3600);
		noWorldOpen(probe, "world.open");
		if (!new File(probe.gameDir, "saves/" + folder + "/level.dat").isFile()) {
			throw new ProbeException("NotFound", "no save called " + folder + " in " + new File(probe.gameDir, "saves"),
				Json.object("what", folder));
		}
		long started = System.currentTimeMillis();
		FutureTask<Void> launch = Sides.get().post(Side.CLIENT, () -> {
			TasTrace.start();
			Worlds.open(Minecraft.getMinecraft(), folder);
			return null;
		});
		watchIn(probe, folder, launch, settle, maxSeconds, started);
		JsonElement name = onServer(() -> Worlds.describe().get("name"));
		return Json.object("folder", folder, "name", name, "load_ms", System.currentTimeMillis() - started);
	}

	/**
	 * Watches the client going into the world: in on both sides, past the terrain screen, then settled for the ticks
	 * asked. A world event says how far it is once a second; max_seconds gives TimedOut, with the loading trace.
	 */
	private static void watchIn(Probe probe, String folder, FutureTask<Void> launch, long settle, long maxSeconds,
		long started) throws ProbeException, InterruptedException {
		Snapshot snapshot = probe.snapshot;
		Sides sides = Sides.get();
		snapshot.changing = true;
		try {
			long nextEvent = started;
			long inSince = -1;
			while (true) {
				failed(launch, "open " + folder);
				long now = System.currentTimeMillis();
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
						"seconds", maxSeconds, "screen", snapshot.screen, "trace", TasTrace.lines()));
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
		TasTrace.stop();
		probe.event("world", Json.object("state", "open", "folder", folder, "ms", System.currentTimeMillis() - started));
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
		Snapshot snapshot = probe.snapshot;
		String folder = snapshot.worldFolder;
		long started = System.currentTimeMillis();
		snapshot.changing = true;
		try {
			probe.event("world", Json.object("state", "closing", "folder", folder, "ms", 0));
			FutureTask<Void> leave = Sides.get().post(Side.CLIENT, () -> {
				Worlds.close(Minecraft.getMinecraft());
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

	/** A world step that threw: the game's failure (a mod's world load, say), as GameError with its trace. */
	private static void failed(FutureTask<Void> step, String what) throws ProbeException {
		if (!step.isDone()) {
			return;
		}
		try {
			step.get();
		} catch (ExecutionException e) {
			Throwable cause = e.getCause();
			throw new ProbeException("GameError", "the game failed to " + what + ": " + cause, Json.object(
				"exception", cause == null ? null : cause.getClass().getName(), "trace", Probe.trace(cause == null ? e : cause)));
		} catch (CancellationException | InterruptedException e) {
			throw new ProbeException("ProbeError", "the step to " + what + " never ran", null);
		}
	}

	private static JsonElement onServer(java.util.concurrent.Callable<JsonElement> read) throws ProbeException, InterruptedException {
		try {
			return Sides.get().run(Side.SERVER, read, Sides.STALL_SECONDS, null);
		} catch (InterruptedException | RuntimeException e) {
			throw e;
		} catch (Exception e) {
			throw new ProbeException("ProbeError", "reading the world failed: " + e, null);
		}
	}

	// ---------------------------------------------------------------- the server thread

	private static JsonElement rules(Call call) throws ProbeException {
		JsonObject given = call.object("rules");
		if (given == null || given.entrySet().isEmpty()) {
			throw ProbeException.badRequest("rules", "rules names the game rules to set: {\"doDaylightCycle\": false}");
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
		List<String> unknown = Worlds.unknownRules(values.keySet());
		if (!unknown.isEmpty()) {
			throw new ProbeException("NotFound", "this game has no rule " + String.join(", ", unknown)
				+ " (1.7.10 would make one silently; the probe doesn't)", Json.object("what", unknown));
		}
		Worlds.setRules(values);
		return new JsonObject();
	}

	private static JsonElement time(Call call) throws ProbeException {
		if (!call.has("time")) {
			throw ProbeException.badRequest("time", "world.time.set needs the time");
		}
		long time = call.number("time", 0, 0, Long.MAX_VALUE);
		Integer dimension = null;
		if (call.has("dimension")) {
			JsonElement given = call.args.get("dimension");
			dimension = dimensionNumber(given);
			if (dimension == null) {
				throw new ProbeException("NotFound", "no dimension " + given, Json.object("what", given));
			}
		}
		Worlds.setTime(time, dimension);
		return new JsonObject();
	}

	/** A dimension by its protocol name or (in 1.7.10) its number; null for none. */
	static Integer dimensionNumber(JsonElement given) {
		if (given.isJsonPrimitive() && given.getAsJsonPrimitive().isNumber()) {
			return given.getAsInt();
		}
		String name = given.isJsonPrimitive() ? given.getAsString() : "";
		switch (name) {
			case "minecraft:overworld":
				return 0;
			case "minecraft:the_nether":
				return -1;
			case "minecraft:the_end":
				return 1;
			default:
				if (name.startsWith("dim:")) {
					try {
						return Integer.parseInt(name.substring(4));
					} catch (NumberFormatException e) {
						return null;
					}
				}
				return null;
		}
	}

	private static JsonElement weather(Call call) throws ProbeException {
		String weather = call.string("weather", null);
		boolean hold = call.flag("hold", true);
		if (weather == null) {
			throw ProbeException.badRequest("weather", "world.weather.set needs the weather: clear, rain or thunder");
		}
		switch (weather) {
			case "clear":
				Worlds.setWeather(false, false, hold);
				break;
			case "rain":
				Worlds.setWeather(true, false, hold);
				break;
			case "thunder":
				Worlds.setWeather(true, true, hold);
				break;
			default:
				throw ProbeException.badRequest("weather", "the weather is clear, rain or thunder, not " + weather);
		}
		return new JsonObject();
	}

	private static JsonElement difficulty(Call call) throws ProbeException {
		String name = call.string("difficulty", null);
		EnumDifficulty difficulty = null;
		for (EnumDifficulty each : EnumDifficulty.values()) {
			if (each.name().equalsIgnoreCase(name == null ? "" : name)) {
				difficulty = each;
			}
		}
		if (difficulty == null) {
			throw ProbeException.badRequest("difficulty", "difficulty is peaceful, easy, normal or hard, not " + name);
		}
		Worlds.setDifficulty(difficulty);
		EnumDifficulty chosen = difficulty;
		// the client's own option, as the game's difficulty button sets both
		Sides.get().post(Side.CLIENT, () -> {
			Minecraft.getMinecraft().gameSettings.difficulty = chosen;
			return null;
		});
		return new JsonObject();
	}
}

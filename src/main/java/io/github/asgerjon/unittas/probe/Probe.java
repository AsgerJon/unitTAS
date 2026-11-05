package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.UnitTasMod;
import io.github.asgerjon.unittas.UnitTasMode;
import io.github.asgerjon.unittas.probe.link.Json;
import io.github.asgerjon.unittas.probe.link.Link;
import io.github.asgerjon.unittas.probe.link.StartFile;
import net.minecraftforge.common.ForgeVersion;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.File;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * unitTAS's probe in a 1.7.10 Forge game (PROTOCOL.md): asleep unless an orchestrator left a start file in the game's
 * folder. Then it wakes from the coremod, before any mod loads, and as soon as Minecraft is launched it dials the
 * orchestrator, says hello and runs what it is asked ({@link #launched} says why not sooner).
 * It knows nothing of tests. This class touches no Minecraft class (it starts too early for that): the game's side is
 * {@link ClientHooks}, registered from the mod's preInit.
 */
public final class Probe implements Link.Handler {

	static final Logger LOG = LogManager.getLogger("unitTAS");
	public static final String PORT = "1.7.10-forge";
	public static final String MINECRAFT = "1.7.10";
	/** The protocol versions this probe speaks. */
	private static final int[] PROTOCOLS = {1};
	/** How often the heartbeat (the tick event) goes, from the probe's own thread, whether or not the game ticks. */
	private static final long HEARTBEAT_MILLIS = 1000;
	/** After a quit began on a game that is up, how long before the probe ends the process itself. */
	private static final int WATCHDOG_SECONDS = 30;
	/** The same for a game that is still loading: it finishes loading first, which a modpack takes its time over. */
	private static final int WATCHDOG_LOADING_SECONDS = 300;

	private static volatile Probe probe;

	final StartFile start;
	final File gameDir;
	final boolean obfuscated;
	final Snapshot snapshot = new Snapshot();
	final Events events = new Events();
	final ChatLog chat = new ChatLog();
	final Refs refs = new Refs();
	private final Link link;
	private final Map<String, Op> ops = new TreeMap<>();
	/** The requests being run, by id, for cancel. */
	private final Map<Long, Running> running = new java.util.concurrent.ConcurrentHashMap<>();
	private final ExecutorService work = Executors.newCachedThreadPool(runnable -> {
		Thread thread = new Thread(runnable, "unitTAS probe");
		thread.setDaemon(true);
		return thread;
	});
	private final AtomicBoolean quitting = new AtomicBoolean();
	private final AtomicBoolean dialled = new AtomicBoolean();
	/** A java.run is going (JavaOps): only the operations marked alongsideJava answer meanwhile. */
	final AtomicBoolean javaRun = new AtomicBoolean();
	/** The game's state for debug.threads (TasHang's, ClientHooks sets it at preInit); null before. */
	volatile java.util.function.Supplier<String> gameState;
	/** How the game is made to quit once there is a game to quit (ClientHooks sets it at preInit). */
	private volatile Runnable leave;

	private Probe(StartFile start, File gameDir, boolean obfuscated) {
		this.start = start;
		this.gameDir = gameDir;
		this.obfuscated = obfuscated;
		Ops.declare(this);
		this.link = new Link(start, hello(), this);
	}

	/**
	 * From the coremod (injectData), before any mod loads: the start file read and deleted, the log listened to. The
	 * link waits for {@link #launched}. Without a start file nothing at all happens; with one that can't be used, the
	 * probe says why and stays asleep.
	 */
	public static synchronized void early(File gameDir, boolean obfuscated) {
		if (probe != null || gameDir == null) {
			return;
		}
		StartFile start;
		try {
			start = StartFile.take(gameDir);
		} catch (IllegalStateException e) {
			LOG.error("unitTAS probe: {}; the probe stays asleep", e.getMessage());
			return;
		}
		if (start == null) {
			return;
		}
		if (!start.deleted) {
			LOG.warn("unitTAS probe: can't delete {}; delete it before the next ordinary game", new File(gameDir, StartFile.PATH));
		}
		// the window's behaviours (PROTOCOL.md 2.5): titled unitTAS, the pointer and the real input left alone
		UnitTasMode.running = true;
		Probe made = new Probe(start, gameDir, obfuscated);
		probe = made;
		ProbeLog.attach(made);
		Runtime.getRuntime().addShutdownHook(new Thread(made::closing, "unitTAS probe closing"));
		LOG.info("unitTAS probe: woken as {} ({}); it dials once Minecraft is launched", start.name, start.role);
	}

	/**
	 * Minecraft is launched (MixinMinecraft, at the end of its constructor): the probe dials. Not before: until
	 * LaunchWrapper launches Minecraft, its tweakers are still adding class transformers, and its class loader goes
	 * through that list without a lock. A class loaded on another thread meanwhile could fail (a
	 * ConcurrentModificationException), and LaunchClassLoader then refuses it for the rest of the game: our own, or
	 * Gson's, which Minecraft needs too (2026-11-05, both seen). So the probe starts no thread of its own until then,
	 * and the main thread is the only one loading classes. preInit calls this too, in case that mixin didn't apply;
	 * then it says so.
	 */
	public static void launched(String lateAt) {
		Probe made = probe;
		if (made == null || !made.dialled.compareAndSet(false, true)) {
			return;
		}
		if (lateAt != null) {
			LOG.warn("unitTAS probe: Minecraft's constructor never woke the link (MixinMinecraft not applied?); it dials at {}",
				lateAt);
		}
		LOG.info("unitTAS probe: dialling 127.0.0.1:{} as {} ({})", made.start.port, made.start.name, made.start.role);
		made.link.start();
		Thread heartbeat = new Thread(made::heartbeat, "unitTAS probe heartbeat");
		heartbeat.setDaemon(true);
		heartbeat.start();
	}

	/**
	 * The tick event, once a second for as long as the link lasts (PROTOCOL.md 7): the sides' tick counts and how long
	 * ago each ticked, the screen, the state. From this thread, so it comes while the game threads are stuck too: the
	 * watch tells a slow game from a stuck one by it. Kept by the link until the welcome, like any event.
	 */
	private void heartbeat() {
		while (!link.ended()) {
			sleep(HEARTBEAT_MILLIS);
			if (link.ended() || Thread.currentThread().isInterrupted()) {
				return;
			}
			if (!link.welcomed()) {
				continue;
			}
			try {
				Sides sides = Sides.get();
				long now = System.currentTimeMillis();
				boolean server = snapshot.serverRunning;
				long clientAt = sides.tickedAt(Side.CLIENT);
				long serverAt = sides.tickedAt(Side.SERVER);
				link.event("tick", Json.object(
					"client", sides.ticks(Side.CLIENT),
					"server", server ? sides.ticks(Side.SERVER) : null,
					"client_ago_ms", clientAt == 0 ? null : now - clientAt,
					"server_ago_ms", server && serverAt != 0 ? now - serverAt : null,
					"screen", snapshot.screen,
					"state", snapshot.state,
					"paused", snapshot.paused));
			} catch (RuntimeException e) {
				LOG.warn("unitTAS probe: a heartbeat failed: {}", e.toString());
			}
		}
	}

	/**
	 * The game is crashing (MixinMinecraft, as it shows its crash report, which is saved by then): the orchestrator
	 * hears it, with the report's file and what it says, before the JVM goes, and then the quit, with reason crash.
	 * No Minecraft class here: the mixin passes plain values.
	 */
	public static void crashed(File report, String description, Throwable cause) {
		Probe made = probe;
		if (made == null) {
			return;
		}
		String summary = (description == null ? "no description" : description) + (cause == null ? "" : ": " + cause
			+ (cause.getStackTrace().length == 0 ? "" : " at " + cause.getStackTrace()[0]));
		LOG.error("unitTAS probe: the game crashed: {} (its crash report: {})", summary, report);
		made.link.event("crash", Json.object("report", report == null ? null : report.getAbsolutePath(), "summary", summary));
		if (made.quitting.compareAndSet(false, true)) {
			made.snapshot.state = "quitting";
			made.link.event("quit", Json.object("reason", "crash"));
		}
		made.link.flush(2000);
	}

	public static boolean active() {
		return probe != null;
	}

	/** The probe, or null in an ordinary game. */
	public static Probe get() {
		return probe;
	}

	void register(Op op) {
		synchronized (ops) {
			ops.put(op.name, op);
		}
	}

	/** The operation of that name, or null. */
	Op op(String name) {
		synchronized (ops) {
			return ops.get(name);
		}
	}

	/** Cancels the request with that id if it isn't too late (PROTOCOL.md 4.6). */
	boolean cancel(long id) {
		Running found = running.get(id);
		return found != null && found.cancel();
	}

	private JsonObject hello() {
		JsonArray protocols = new JsonArray();
		for (int version : PROTOCOLS) {
			protocols.add(Json.of(version));
		}
		List<String> names = new ArrayList<>();
		synchronized (ops) {
			names.addAll(ops.keySet());
		}
		String pid = ManagementFactory.getRuntimeMXBean().getName().split("@", 2)[0];
		return Json.object(
			"protocol", protocols,
			"token", start.token,
			"name", start.name,
			"role", start.role,
			"probe", Json.object("version", UnitTasMod.VERSION, "port", PORT),
			"minecraft", MINECRAFT,
			"loader", Json.object("name", "forge", "version", ForgeVersion.majorVersion + "." + ForgeVersion.minorVersion + "."
				+ ForgeVersion.revisionVersion + "." + ForgeVersion.buildVersion),
			"java", Json.object("version", System.getProperty("java.version"), "max_memory_mb",
				Runtime.getRuntime().maxMemory() / (1024 * 1024)),
			// a real 1.7.10 client names Minecraft's members by Searge; a development run by MCP
			"names", obfuscated ? "srg" : "mcp",
			"development", !obfuscated,
			"pid", Long.parseLong(pid),
			"game_dir", gameDir.getAbsolutePath(),
			"ops", names,
			"events", Events.KINDS);
	}

	// ---------------------------------------------------------------- the link's handler

	@Override
	public void request(Link from, JsonElement id, String name, JsonElement sideGiven, JsonObject args) {
		Op op = op(name);
		if (op == null) {
			from.error(id, "Unsupported", "this probe (" + PORT + ") has no operation " + name, Json.object("op", name));
			return;
		}
		if (!snapshot.ready && !op.beforeReady()) {
			from.error(id, "NotReady", name + " can't run while the game loads", Json.object("state", "loading"));
			return;
		}
		if (javaRun.get() && !op.duringJava()) {
			from.error(id, "NotReady", name + " waits while a java.run goes: only the probe's own operations answer"
				+ " until it ends", Json.object("state", snapshot.state, "java_run", true));
			return;
		}
		Side side;
		try {
			side = sideFor(op, sideGiven, args);
		} catch (ProbeException e) {
			from.error(id, e.type, e.getMessage(), e.fields);
			return;
		}
		long key = id.getAsLong();
		Running run = new Running(key);
		if (running.putIfAbsent(key, run) != null) {
			from.error(id, "BadRequest", "request " + key + " is still running: ids never repeat on a connection",
				Json.object("field", "id"));
			return;
		}
		work.execute(() -> {
			// a cancel that came too late for another request never reaches this one (Running takes care)
			Thread.interrupted();
			run.waitingOn(Thread.currentThread());
			JsonElement value = null;
			ProbeException failure = null;
			Call call = new Call(this, args, side, run);
			try {
				value = side == null ? op.run(call) : op.settle(call, onSide(op, call));
			} catch (ProbeException e) {
				failure = e;
			} catch (InterruptedException e) {
				failure = new ProbeException("Cancelled", name + " was cancelled", null);
			} catch (RuntimeException | Error e) {
				failure = new ProbeException("ProbeError", name + " failed in the probe: " + e, Json.object("trace", trace(e)));
			} finally {
				run.finish();
				running.remove(key);
				Thread.interrupted();
			}
			if (failure != null) {
				from.error(id, failure.type, failure.getMessage(), failure.fields);
			} else {
				from.answer(id, value, call.warnings);
				op.after(this);
			}
		});
	}

	/** The side the request runs on: null on the probe's own thread; BadRequest (field "side") for one it can't. */
	private static Side sideFor(Op op, JsonElement given, JsonObject args) throws ProbeException {
		if (op.sides == null) {
			if (given != null) {
				throw ProbeException.badRequest("side", op.name + " runs on the probe's own thread and takes no side");
			}
			return null;
		}
		if (given == null) {
			if (op.sideRequired()) {
				throw ProbeException.badRequest("side", op.name + " needs a side: client or server");
			}
			return op.defaultSide(args);
		}
		Side side = given.isJsonPrimitive() && given.getAsJsonPrimitive().isString() ? Side.of(given.getAsString()) : null;
		if (side == null) {
			throw ProbeException.badRequest("side", "side is client or server, not " + given);
		}
		if (!op.allows(side)) {
			throw ProbeException.badRequest("side", op.name + " runs on the " + op.sides[0].wire + " only");
		}
		return side;
	}

	/** An instant operation, on its side's thread at the side's next tick, waited for with the stall rule. */
	private JsonElement onSide(Op op, Call call) throws ProbeException, InterruptedException {
		Ops.needThread(this, call.side);
		try {
			return Sides.get().run(call.side, () -> {
				if (!call.running.begin()) {
					throw new InterruptedException("cancelled before it started");
				}
				return op.run(call);
			}, Sides.STALL_SECONDS, call.running::queued);
		} catch (Sides.Stalled stalled) {
			throw Ops.stalled(this, stalled);
		} catch (ProbeException | InterruptedException | RuntimeException e) {
			throw e;
		} catch (Exception e) {
			throw new ProbeException("ProbeError", op.name + " failed in the probe: " + e, Json.object("trace", trace(e)));
		}
	}

	@Override
	public void ended(Link from, String why) {
		LOG.warn("unitTAS probe: {}; the game quits", why);
		quit(from.welcomed() ? "orchestrator gone" : why);
	}

	@Override
	public JsonObject at() {
		Sides sides = Sides.get();
		return Json.object("client", sides.ticks(Side.CLIENT), "server", snapshot.serverRunning ? sides.ticks(Side.SERVER) : null);
	}

	/** An event to the orchestrator (dropped if the link has ended). */
	void event(String kind, JsonObject fields) {
		link.event(kind, fields);
	}

	// ---------------------------------------------------------------- quitting

	boolean quitting() {
		return quitting.get();
	}

	/** ClientHooks hands over how to quit the game; a quit asked for before then happens now. */
	void leaveBy(Runnable how) {
		leave = how;
		if (quitting.get()) {
			how.run();
		}
	}

	/**
	 * The game quits (PROTOCOL.md 10): the quit event first, then the game's own way out, never an exit of the probe's
	 * own (FML's security manager allows that only to FML and Minecraft). Before there is a game to quit, at the
	 * coremod's time, it quits as soon as there is (leaveBy).
	 */
	void quit(String reason) {
		if (!quitting.compareAndSet(false, true)) {
			return;
		}
		snapshot.state = "quitting";
		LOG.info("unitTAS probe: the game quits ({})", reason);
		link.event("quit", Json.object("reason", reason));
		link.flush(2000);
		Runnable how = leave;
		if (how != null) {
			how.run();
		}
		Thread watchdog = new Thread(this::watch, "unitTAS probe watchdog");
		watchdog.setDaemon(true);
		watchdog.start();
	}

	/**
	 * The last resort, if the game hasn't gone in time: the process asks itself to terminate (SIGTERM), which the JVM
	 * handles itself, past FML's security manager, running its shutdown hooks. The orchestrator ends the process too
	 * once its own limit is past; this is for a game left with nobody.
	 */
	private void watch() {
		long since = System.currentTimeMillis();
		while (!snapshot.ready && System.currentTimeMillis() - since < WATCHDOG_LOADING_SECONDS * 1000L) {
			sleep(1000);
		}
		sleep(WATCHDOG_SECONDS * 1000L);
		LOG.error("unitTAS probe: the game hasn't quit in time; it is made to");
		try {
			Class<?> signal = Class.forName("sun.misc.Signal");
			Object term = signal.getConstructor(String.class).newInstance("TERM");
			Method raise = signal.getMethod("raise", signal);
			raise.invoke(null, term);
		} catch (ReflectiveOperationException | RuntimeException e) {
			LOG.error("unitTAS probe: can't end the process ({}); the orchestrator has to", e.toString());
		}
	}

	/** The JVM is going: if nobody asked for it (the window closed, a crash), the orchestrator hears why. */
	private void closing() {
		if (quitting.compareAndSet(false, true)) {
			link.event("quit", Json.object("reason", "window closed"));
			link.flush(1000);
		}
	}

	private static void sleep(long millis) {
		try {
			Thread.sleep(millis);
		} catch (InterruptedException e) {
			Thread.currentThread().interrupt();
		}
	}

	static String trace(Throwable t) {
		java.io.StringWriter text = new java.io.StringWriter();
		t.printStackTrace(new java.io.PrintWriter(text));
		String all = text.toString();
		return all.length() > 8000 ? all.substring(0, 8000) + "..." : all;
	}
}

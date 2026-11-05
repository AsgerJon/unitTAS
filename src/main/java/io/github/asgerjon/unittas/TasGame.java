package io.github.asgerjon.unittas;

import cpw.mods.fml.common.FMLCommonHandler;
import cpw.mods.fml.common.eventhandler.SubscribeEvent;
import cpw.mods.fml.common.gameevent.TickEvent;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiMainMenu;
import net.minecraft.entity.player.EntityPlayerMP;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.EnumDifficulty;
import net.minecraft.world.WorldSettings;
import net.minecraft.world.WorldType;
import net.minecraft.world.storage.ISaveFormat;
import net.minecraftforge.client.event.ClientChatReceivedEvent;
import net.minecraftforge.common.MinecraftForge;
import io.github.asgerjon.unittas.probe.Side;
import io.github.asgerjon.unittas.probe.Sides;
import io.github.asgerjon.unittas.probe.Window;
import io.github.asgerjon.unittas.probe.Worlds;

import java.io.File;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * The game side of a unitTAS run: makes the test world from the main menu, starts the runner once the player stands in
 * it, runs the test thread's steps on the client and server threads, counts their ticks, keeps the chat the client
 * receives, and stops a test that runs out of time (in a watched run, the watch asks first: {@link TasWatch}).
 */
public final class TasGame {

	static final String WORLD_FOLDER = Worlds.FOLDER;
	/** Bedrock, two dirt, grass: the surface is y 3, a player stands at y 4. The empty last field: no structures. */
	static final String FLAT_LAYERS = Worlds.FLAT_LAYERS;
	static final long SEED = Worlds.SEED;
	private static final int SETTLE_TICKS = 40;
	private static final int WORLD_TIMEOUT_TICKS = 20 * 180;
	/**
	 * The test world loads in about 10 s: at 60 it is stuck, and the evidence is taken before the game quits: pictures
	 * of the window while it loads and the threads' dump. A watched run asks the watcher instead.
	 */
	private static final int LOAD_TIMEOUT_TICKS = 20 * TasWatch.LOAD_SECONDS;
	private static final int STEP_TIMEOUT_SECONDS = 15;

	/** A step that didn't come back, or a test that ran out of time or was stopped. */
	static final class Timeout extends RuntimeException {
		/** True when the game stopped running steps or ticking; false when the test was stopped (its time, the watcher). */
		final boolean stuck;

		Timeout(String message, boolean stuck) {
			super(message);
			this.stuck = stuck;
		}
	}

	/** One line of chat as the client got it: with formatting codes, and without. */
	static final class ChatLine {
		final String formatted;
		final String plain;

		ChatLine(String formatted, String plain) {
			this.formatted = formatted;
			this.plain = plain;
		}
	}

	enum Stage {MENU, LOADING, RUNNING, DONE}

	/**
	 * Who started a run from the probe (java.run, PROTOCOL.md 8.14), told of each line of the report as it comes and of
	 * the run's end. Such a run leaves the game up: the probe closes the runner's world itself.
	 */
	public interface Listener {
		/** A line of the report: the test's name (or the problem's), java.result's outcome, its seconds, the text under it. */
		void result(String name, String outcome, double seconds, String detail);

		/** The run is over, on the client thread: its report (null if none was written), whether it passed, its counts. */
		void done(File report, boolean ok, Map<String, Integer> counts);
	}

	private final UnitTas.Request request;
	private final TasWatch watch;
	/** The probe's java.run, or null for a run of its own (request.properties), which quits the game at its end. */
	private final Listener listener;
	/** The report as written, for the listener. */
	private volatile File reportFile;
	private volatile boolean reportOk;
	private volatile Map<String, Integer> reportCounts;
	/** The game's ticks and the steps run on them, the probe's own (one for the game, shared). */
	private final Sides sides = Sides.get();
	private final List<ChatLine> chat = new ArrayList<>();
	/** When the test world began loading (System.currentTimeMillis()). */
	private volatile long loadingSince;
	private volatile Stage stage = Stage.MENU;
	private int stageTicks;
	private int settledTicks;
	private volatile Thread runnerThread;

	/** The test clock: changed only under clockLock, so a late stop can never reach the next test. */
	private final Object clockLock = new Object();
	/** When the running test must be done by, in client ticks; 0 between tests. */
	private volatile long deadline;
	/** Counts the clocks started: a stop names the one it means. */
	private volatile int testNumber;
	private volatile int testLimitSeconds;
	/** Why the running test is being stopped (its steps' Timeout says it), or null for its time running out. */
	private volatile String stopReason;
	private volatile String abortReason;
	private volatile String giveUpLoading;

	/** What the run does now, for the watch: the test or the phase, and the step within it. */
	private volatile String activity = "starting";
	private volatile String doing;
	private volatile boolean inTest;
	private volatile long testStartedAt;

	/** The run's settings are in place (and the hooks' beforeRun called): finish puts the player's back. */
	private boolean prepared;
	private boolean pauseOnLostFocus;
	private EnumDifficulty difficulty;

	/** The test world's number, as the report names it: 1 for the run's first world, one more for each new one. */
	private volatile int worldNumber = 1;

	/** The run going on, for the test helpers that have no game of their own (player() off the server thread warns here). */
	private static volatile TasGame current;
	/** The running test's warnings, each made where it was raised, so the report can say where. */
	private final List<Throwable> warnings = new ArrayList<>();

	TasGame(UnitTas.Request request) {
		this(request, null);
	}

	TasGame(UnitTas.Request request, Listener listener) {
		this.request = request;
		this.listener = listener;
		this.watch = new TasWatch(this);
		current = this;
	}

	/** Under the probe, its own tick handlers count the ticks (ClientHooks): counted here too, each would count twice. */
	private boolean countsTicks() {
		return listener == null;
	}

	/** A line of the report, as it is added: the listener hears it. */
	void resultLine(String name, String outcome, double seconds, String detail) {
		if (listener != null) {
			try {
				listener.result(name, outcome, seconds, detail);
			} catch (RuntimeException e) {
				UnitTas.LOG.error("unitTAS: the java.run's listener failed on {}", name, e);
			}
		}
	}

	/** The report as it was written: where, whether it passed, its counts. */
	void reported(File file, boolean ok, Map<String, Integer> counts) {
		reportFile = file;
		reportOk = ok;
		reportCounts = counts;
	}

	/**
	 * Stops the run as the watch's stop does (java.run's cancel): the running test now, and no test after it. A run
	 * still making its world gives that up at the client's next tick.
	 */
	public void cancel(String reason) {
		abort(reason);
		if (stage != Stage.RUNNING) {
			giveUpLoading(reason);
		}
	}

	UnitTas.Request request() {
		return request;
	}

	void startWatch() {
		watch.start();
	}

	/** The watch, to ask it about a situation (only in a watched run; null otherwise). */
	TasWatch watch() {
		return request.watched ? watch : null;
	}

	@SubscribeEvent
	public void onClientTick(TickEvent.ClientTickEvent event) {
		if (countsTicks()) {
			sides.noteThread(Side.CLIENT);
		}
		Minecraft mc = Minecraft.getMinecraft();
		if (event.phase == TickEvent.Phase.START) {
			ignoreRealInput(mc);
			return;
		}
		stageTicks++;
		switch (stage) {
			case MENU: {
				if (mc.currentScreen instanceof GuiMainMenu && !request.saves.isEmpty()) {
					// save mode: the runner opens each save itself
					prepareRun(mc, false);
					stage = Stage.RUNNING;
					startRunner();
				} else if (mc.currentScreen instanceof GuiMainMenu) {
					stage = Stage.LOADING;
					stageTicks = 0;
					loadingSince = System.currentTimeMillis();
					activity = "making the test world";
					request.progress("making the test world");
					createWorld(mc);
				} else if (stageTicks > WORLD_TIMEOUT_TICKS) {
					// another screen stands in front of the main menu (a mod's notice, say)
					String problem = "the main menu never showed (the screen is " + (mc.currentScreen == null ? "none" : mc.currentScreen.getClass().getName()) + ")";
					request.progress(problem);
					TasRunner.reportUnstarted(this, "TasGame.mainMenu", problem);
					finish(mc);
				}
				break;
			}
			case LOADING: {
				String givenUp = giveUpLoading;
				if (givenUp == null && (mc.thePlayer == null || mc.theWorld == null || serverPlayerOrNull() == null)) {
					settledTicks = 0;
					if (stageTicks == 100 || stageTicks % 400 == 0) {
						String picture = TasHang.picture(mc, request.results, stageTicks / 20);
						request.progress("loading for " + stageTicks / 20 + " s: the screen is "
								+ (mc.currentScreen == null ? "none" : mc.currentScreen.getClass().getSimpleName()) + ", picture " + picture);
					}
					// a watched run asks the watcher (TasWatch), which gives up through giveUpLoading
					if (!request.watched && stageTicks > LOAD_TIMEOUT_TICKS) {
						givenUp = "the test world didn't load in " + LOAD_TIMEOUT_TICKS / 20 + " s";
					}
				}
				if (givenUp != null) {
					TasTrace.write(request.results, "loading-trace.txt");
					String dump = TasHang.dump(mc, request.results);
					String problem = givenUp + "; threads and connection in " + dump;
					request.progress(problem);
					TasRunner.reportUnstarted(this, "TasGame.loadTestWorld", problem);
					finish(mc);
				} else if (mc.thePlayer != null && mc.theWorld != null && serverPlayerOrNull() != null && ++settledTicks >= SETTLE_TICKS) {
					// the chunks around the player are in by now
					TasTrace.stop();
					TasTrace.write(request.results, "loading-trace.txt");
					stage = Stage.RUNNING;
					startRunner();
				}
				break;
			}
			case RUNNING: {
				// a watched run asks the watcher first (TasWatch), which stops the test through stopTest
				if (!request.watched && testOverTime()) {
					stopTest(testNumber, null);
				}
				break;
			}
			default:
				break;
		}
		if (countsTicks()) {
			sides.ticked(Side.CLIENT);
		}
	}

	@SubscribeEvent
	public void onServerTick(TickEvent.ServerTickEvent event) {
		if (!countsTicks()) {
			return;
		}
		sides.noteThread(Side.SERVER);
		if (event.phase != TickEvent.Phase.END) {
			return;
		}
		sides.ticked(Side.SERVER);
	}

	@SubscribeEvent
	public void onChat(ClientChatReceivedEvent event) {
		if (event.message != null) {
			synchronized (chat) {
				chat.add(new ChatLine(event.message.getFormattedText(), event.message.getUnformattedText()));
			}
		}
	}

	private void startRunner() {
		activity = "starting the tests";
		runnerThread = new Thread(new TasRunner(this), "unitTAS");
		runnerThread.setDaemon(true);
		runnerThread.start();
	}

	/**
	 * The tests are the only input: the real mouse and keyboard events go before the game reads them (this runs at the
	 * start of the tick, ahead of the screens and the game), so the window works without focus and a stray click
	 * doesn't disturb a test. The game counts as focused while no screen is open, as holding a key to mine needs.
	 */
	private void ignoreRealInput(Minecraft mc) {
		if (stage == Stage.DONE) {
			return;
		}
		Window.ignoreRealInput(mc);
	}

	/** A fresh world each run: the old test world goes first (only that folder), then creative, cheats, flat, a fixed seed. */
	private void createWorld(Minecraft mc) {
		prepareRun(mc, true);
		// a run that died left its kept world: this run keeps its own
		dropPristine();
		ISaveFormat saves = mc.getSaveLoader();
		saves.flushCache();
		saves.deleteWorldDirectory(WORLD_FOLDER);
		TasTrace.start();
		Worlds.create(mc, WORLD_FOLDER, Worlds.NAME, SEED, WorldType.FLAT, FLAT_LAYERS, WorldSettings.GameType.CREATIVE, true, true);
	}

	/**
	 * The run's own settings, the player's kept aside to put back at the end: no pause on lost focus, (in the test
	 * world, not a save's) Easy, and whatever the mods' hooks set for their tests.
	 */
	private void prepareRun(Minecraft mc, boolean easy) {
		backUpOptions(mc);
		backUpConfig(mc);
		pauseOnLostFocus = mc.gameSettings.pauseOnLostFocus;
		difficulty = mc.gameSettings.difficulty;
		mc.gameSettings.pauseOnLostFocus = false;
		if (easy) {
			mc.gameSettings.difficulty = EnumDifficulty.EASY;
		}
		prepared = true;
		TasPlugins.each("beforeRun", request, TasHooks::beforeRun);
	}

	// ---------------------------------------------------------------- save mode; on the client thread

	/** Opens a save from the game's saves folder, as the world list's Play does. */
	void openSave(String folder) {
		Worlds.open(Minecraft.getMinecraft(), folder);
	}

	/** The player is in the world on both sides, past the terrain screen. */
	boolean inWorld() {
		return Worlds.inWorld(Minecraft.getMinecraft());
	}

	/** inWorld, read from another thread: a guess good enough for the watch (false when the read goes wrong). */
	boolean inWorldFromAfar() {
		try {
			return inWorld();
		} catch (RuntimeException e) {
			return false;
		}
	}

	/** Save and quit to the title screen, as the pause menu's button does. */
	void quitToMenu() {
		Worlds.close(Minecraft.getMinecraft());
	}

	/**
	 * The player's options.txt, kept aside while the run goes: a test that changes an option, or a mod that saves its
	 * own options there, writes the whole file, with the run's own settings in it (pause on lost focus off, Easy).
	 */
	private static File optionsBackup(Minecraft mc) {
		return new File(mc.mcDataDir, "unittas/options.txt.backup");
	}

	private void backUpOptions(Minecraft mc) {
		File options = new File(mc.mcDataDir, "options.txt");
		File backup = optionsBackup(mc);
		try {
			if (backup.isFile()) {
				// an earlier run died before putting it back; the copy is the player's
				Files.copy(backup.toPath(), options.toPath(), StandardCopyOption.REPLACE_EXISTING);
			} else if (options.isFile() && (backup.getParentFile().isDirectory() || backup.getParentFile().mkdirs())) {
				Files.copy(options.toPath(), backup.toPath());
			}
		} catch (IOException e) {
			request.progress("can't keep options.txt aside: " + e);
		}
	}

	private void restoreOptions(Minecraft mc) {
		File backup = optionsBackup(mc);
		if (backup.isFile()) {
			try {
				Files.copy(backup.toPath(), new File(mc.mcDataDir, "options.txt").toPath(), StandardCopyOption.REPLACE_EXISTING);
				Files.delete(backup.toPath());
			} catch (IOException e) {
				request.progress("can't put options.txt back (the copy is in " + backup + "): " + e);
			}
		}
	}

	/**
	 * The game's config/ (Forge's settings and the mods'), kept aside as options.txt is: a test that changes a mod's
	 * setting writes the mod's file with the run's value in it. Put back exactly at the end: changed files restored,
	 * files the run made removed. The copy counts only once it is whole (its marker is written last), so a run that
	 * died while copying never puts back half a folder.
	 */
	private static File configBackup(Minecraft mc) {
		return new File(mc.mcDataDir, "unittas/config.backup");
	}

	private static File configBackupWhole(Minecraft mc) {
		return new File(mc.mcDataDir, "unittas/config.backup.whole");
	}

	private void backUpConfig(Minecraft mc) {
		File config = new File(mc.mcDataDir, "config");
		File backup = configBackup(mc);
		File whole = configBackupWhole(mc);
		try {
			if (whole.isFile()) {
				// an earlier run died before putting it back; the copy is the player's
				copyExactly(backup.toPath(), config.toPath());
				return;
			}
			deleteTree(backup.toPath());
			copyExactly(config.toPath(), backup.toPath());
			Files.write(whole.toPath(), new byte[0]);
		} catch (IOException | UncheckedIOException e) {
			request.progress("can't keep config/ aside: " + e);
		}
	}

	private void restoreConfig(Minecraft mc) {
		File whole = configBackupWhole(mc);
		if (!whole.isFile()) {
			return;
		}
		File backup = configBackup(mc);
		try {
			copyExactly(backup.toPath(), new File(mc.mcDataDir, "config").toPath());
			Files.delete(whole.toPath());
			deleteTree(backup.toPath());
		} catch (IOException | UncheckedIOException e) {
			request.progress("can't put config/ back (the copy is in " + backup + "): " + e);
		}
	}

	/** Makes the folder `to` hold exactly what `from` holds: every file copied over, anything `from` lacks removed. */
	private static void copyExactly(Path from, Path to) throws IOException {
		Files.createDirectories(to);
		// deepest first, so a folder that goes is empty by its turn
		List<Path> there = below(to);
		Collections.reverse(there);
		for (Path path : there) {
			if (!Files.exists(from.resolve(to.relativize(path)), LinkOption.NOFOLLOW_LINKS)) {
				Files.delete(path);
			}
		}
		for (Path path : below(from)) {
			Path target = to.resolve(from.relativize(path));
			if (Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) {
				Files.createDirectories(target);
			} else {
				Files.copy(path, target, StandardCopyOption.REPLACE_EXISTING, LinkOption.NOFOLLOW_LINKS);
			}
		}
	}

	private static void deleteTree(Path root) throws IOException {
		List<Path> paths = below(root);
		Collections.reverse(paths);
		for (Path path : paths) {
			Files.delete(path);
		}
		Files.deleteIfExists(root);
	}

	/** Everything under the folder (not the folder itself), each folder before what it holds; none if it isn't one. */
	private static List<Path> below(Path root) throws IOException {
		if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) {
			return new ArrayList<>();
		}
		try (Stream<Path> paths = Files.walk(root)) {
			return paths.filter(path -> !path.equals(root)).collect(Collectors.toCollection(ArrayList::new));
		}
	}

	/**
	 * Puts the player's settings back and quits the game (on the client thread). A java.run's game stays up instead:
	 * the run lets go of the game's events, and the probe hears that it is over.
	 */
	void finish(Minecraft mc) {
		stage = Stage.DONE;
		activity = listener == null ? "quitting" : "done";
		if (listener == null) {
			UnitTasMode.running = false;
		}
		if (prepared) {
			TasPlugins.each("afterRun", request, TasHooks::afterRun);
			mc.gameSettings.pauseOnLostFocus = pauseOnLostFocus;
			if (difficulty != null) {
				mc.gameSettings.difficulty = difficulty;
			}
		}
		restoreOptions(mc);
		restoreConfig(mc);
		dropPristine();
		if (listener == null) {
			mc.shutdown();
			return;
		}
		FMLCommonHandler.instance().bus().unregister(this);
		MinecraftForge.EVENT_BUS.unregister(this);
		if (current == this) {
			current = null;
		}
		listener.done(reportFile, reportOk, reportCounts);
	}

	// ---------------------------------------------------------------- the test clock, and stopping

	/** The test's time limit starts now. */
	void startClock(int seconds) {
		synchronized (clockLock) {
			testNumber++;
			testLimitSeconds = seconds;
			stopReason = null;
			deadline = sides.ticks(Side.CLIENT) + seconds * 20L;
		}
	}

	/** No more stops for this test once this returns (clear the thread's interrupt after it). */
	void stopClock() {
		synchronized (clockLock) {
			deadline = 0;
		}
	}

	boolean testOverTime() {
		long until = deadline;
		return until > 0 && sides.ticks(Side.CLIENT) > until;
	}

	/** More time for the running test (the watcher's "wait"), counted from now if it is already past its limit. */
	void extendClock(int test, int seconds) {
		synchronized (clockLock) {
			if (deadline > 0 && test == testNumber) {
				deadline = Math.max(deadline, sides.ticks(Side.CLIENT)) + seconds * 20L;
			}
		}
	}

	/**
	 * Stops the running test now: its step or wait throws Timeout with the reason (null: it ran out of time). Nothing
	 * happens when that test is already over.
	 */
	void stopTest(int test, String reason) {
		synchronized (clockLock) {
			Thread runner = runnerThread;
			if (deadline == 0 || test != testNumber || runner == null) {
				return;
			}
			deadline = 0;
			stopReason = reason;
			runner.interrupt();
		}
	}

	/** Stops the run: the running test now, and no test after it. */
	void abort(String reason) {
		abortReason = reason;
		stopTest(testNumber, reason);
	}

	/** Why the run was aborted, or null. */
	String aborted() {
		return abortReason;
	}

	/** The watch gives up on the test world; the client ends the run at its next tick. */
	void giveUpLoading(String reason) {
		giveUpLoading = reason;
	}

	private String stoppedBecause() {
		String reason = stopReason;
		return reason != null ? reason : "the test ran out of time";
	}

	// ---------------------------------------------------------------- what the watch reads

	void activity(String now) {
		activity = now;
	}

	String activity() {
		return activity;
	}

	/** The step within the test (a wait, say), for the watch; null for none. */
	void doing(String now) {
		doing = now;
	}

	String doing() {
		return doing;
	}

	void testStarts(String label) {
		activity = label;
		doing = null;
		testStartedAt = System.currentTimeMillis();
		synchronized (warnings) {
			warnings.clear();
		}
		inTest = true;
	}

	/**
	 * A warning for the running test when the caller isn't on the server thread: the server's objects (its player, its
	 * world) belong to that thread, and read from another they usually work and sometimes don't. A warning, not a
	 * failure, for now.
	 */
	static void expectServerThread(String what) {
		TasGame game = current;
		if (game == null || !game.inTest) {
			return;
		}
		Thread server = game.sides.thread(Side.SERVER);
		Thread here = Thread.currentThread();
		if (server != null && here != server) {
			String from = here == game.sides.thread(Side.CLIENT) ? "the client thread" : "the test's thread";
			synchronized (game.warnings) {
				game.warnings.add(new Throwable(what + " outside a server step (onServer): it reads the server's objects from " + from));
			}
		}
	}

	/** The running test's warnings so far; they are the caller's after this. */
	List<Throwable> takeWarnings() {
		synchronized (warnings) {
			List<Throwable> taken = new ArrayList<>(warnings);
			warnings.clear();
			return taken;
		}
	}

	void testEnds() {
		inTest = false;
		doing = null;
	}

	boolean inTest() {
		return inTest;
	}

	long testStartedAt() {
		return testStartedAt;
	}

	int testNumber() {
		return testNumber;
	}

	int worldNumber() {
		return worldNumber;
	}

	/** The next class's world is a new one, as the report counts them. */
	void nextWorld() {
		worldNumber++;
	}

	// ---------------------------------------------------------------- the test world, kept as made

	private static File worldFolder() {
		return new File(Minecraft.getMinecraft().mcDataDir, "saves/" + WORLD_FOLDER);
	}

	/** The test world as it was made, for each class's fresh world: in the game's own folder, not among the saves. */
	private static File pristineFolder() {
		return new File(Minecraft.getMinecraft().mcDataDir, "unittas/world.pristine");
	}

	/** Copies the closed test world aside, as it is now. */
	void keepPristine() throws IOException {
		copyExactly(worldFolder().toPath(), pristineFolder().toPath());
	}

	/** Puts the kept copy back over the closed test world, exactly: what was made in it since is gone, the End too. */
	void restorePristine() throws IOException {
		copyExactly(pristineFolder().toPath(), worldFolder().toPath());
	}

	private void dropPristine() {
		try {
			deleteTree(pristineFolder().toPath());
		} catch (IOException | UncheckedIOException e) {
			request.progress("can't remove the kept test world " + pristineFolder() + ": " + e);
		}
	}

	int testLimitSeconds() {
		return testLimitSeconds;
	}

	Stage stage() {
		return stage;
	}

	boolean done() {
		return stage == Stage.DONE;
	}

	long loadingSince() {
		return loadingSince;
	}

	long clientTickedAt() {
		return sides.tickedAt(Side.CLIENT);
	}

	long serverTickedAt() {
		return sides.tickedAt(Side.SERVER);
	}

	boolean clientTickedWithin(int seconds) {
		return System.currentTimeMillis() - clientTickedAt() < seconds * 1000L;
	}

	/** An integrated server is up (it may be paused, then it doesn't tick). */
	boolean serverExpected() {
		MinecraftServer server = MinecraftServer.getServer();
		return server != null && !server.isServerStopped() && serverTickedAt() > 0;
	}

	/** Both sides ticked within the time (the server only if one is up). */
	boolean tickingLately(int seconds) {
		long now = System.currentTimeMillis();
		return clientTickedWithin(seconds) && (!serverExpected() || now - serverTickedAt() < seconds * 1000L);
	}

	// ---------------------------------------------------------------- steps and ticks

	/** Runs a step on the client thread at its next tick and returns its result; at once if already on that thread. */
	<T> T client(Callable<T> step) {
		return await(Side.CLIENT, step);
	}

	/** Runs a step on the server thread at its next tick and returns its result; at once if already on that thread. */
	<T> T server(Callable<T> step) {
		return await(Side.SERVER, step);
	}

	/**
	 * The step on that side's thread (Sides), with this run's own failures: Timeout when the side stopped ticking (stuck)
	 * or the test was stopped meanwhile (not stuck).
	 */
	private <T> T await(Side side, Callable<T> step) {
		try {
			return sides.run(side, step, STEP_TIMEOUT_SECONDS, null);
		} catch (Sides.Stalled e) {
			throw new Timeout("the " + side.wire + " stopped ticking: no tick in " + STEP_TIMEOUT_SECONDS + " s (paused or stuck?)", true);
		} catch (InterruptedException e) {
			throw new Timeout(stoppedBecause(), false);
		} catch (RuntimeException e) {
			throw e;
		} catch (Exception e) {
			throw new RuntimeException(e);
		}
	}

	void clientTicks(int ticks) {
		waitTicks(ticks, true);
	}

	void serverTicks(int ticks) {
		waitTicks(ticks, false);
	}

	/**
	 * Waits until that side has ticked this often. It gives up only when no tick has come for the step limit (the
	 * timer starts again at each tick), so a game that is slow but ticking (10 ticks a second in a heavy test) gets
	 * there however long it takes; the test's own time limit still applies.
	 */
	private void waitTicks(int ticks, boolean client) {
		Side side = client ? Side.CLIENT : Side.SERVER;
		if (sides.onThread(side)) {
			throw new IllegalStateException("can't wait for " + side.wire + " ticks inside a " + side.wire
				+ " step: that thread doesn't tick while it runs the step");
		}
		try {
			sides.waitTicks(side, ticks, STEP_TIMEOUT_SECONDS);
		} catch (Sides.Stalled e) {
			throw new Timeout("the " + side.wire + " stopped ticking: no tick in " + STEP_TIMEOUT_SECONDS + " s (paused or stuck?)", true);
		} catch (InterruptedException e) {
			throw new Timeout(stoppedBecause(), false);
		}
	}

	/** Whether that side still ticks (one tick within the step limit); for the runner, outside a test's clock. */
	boolean ticking(boolean client) {
		try {
			waitTicks(1, client);
			return true;
		} catch (Timeout e) {
			return false;
		}
	}

	long clientTickCount() {
		return sides.ticks(Side.CLIENT);
	}

	/** Where the chat stands now; {@link #chatSince} gives what came after. */
	int chatMark() {
		synchronized (chat) {
			return chat.size();
		}
	}

	List<ChatLine> chatSince(int mark) {
		synchronized (chat) {
			return new ArrayList<>(chat.subList(Math.min(mark, chat.size()), chat.size()));
		}
	}

	/** The one player, on the server side; call on the server thread. */
	static EntityPlayerMP serverPlayer() {
		EntityPlayerMP player = serverPlayerOrNull();
		if (player == null) {
			throw new IllegalStateException("No player on the server");
		}
		return player;
	}

	private static EntityPlayerMP serverPlayerOrNull() {
		return Worlds.serverPlayerOrNull();
	}
}

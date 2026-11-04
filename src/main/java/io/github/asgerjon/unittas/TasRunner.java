package io.github.asgerjon.unittas;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiDownloadTerrain;
import net.minecraft.client.gui.GuiMainMenu;
import net.minecraft.client.gui.GuiScreen;
import net.minecraft.client.settings.KeyBinding;
import net.minecraft.entity.Entity;
import net.minecraft.entity.player.EntityPlayer;
import net.minecraft.entity.player.EntityPlayerMP;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.EnumDifficulty;
import net.minecraft.world.GameRules;
import net.minecraft.world.WorldServer;
import net.minecraft.world.WorldSettings;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Comparator;
import java.util.Date;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * The test thread, as Python's unittest runs a suite: every public no-argument method whose name starts with `test`,
 * in name order, each on a fresh instance with setUp before and tearDown after. Between tests the player and the world
 * are put back (creative, empty inventory, no effects, at the spawn point, no other entities). A failure or error takes
 * a screenshot. At the end: the report, and the game quits.
 */
final class TasRunner implements Runnable {

	/** The spawn point every test starts from, on the flat world's grass. */
	static final double START_X = 0.5;
	static final double START_Y = 4.0;
	static final double START_Z = 0.5;

	private enum Outcome {
		OK("ok"), FAIL("FAIL"), ERROR("ERROR"), SKIP("skipped"),
		/** @ExpectedFailure: failed as marked; and passed although marked, which fails the run. */
		EXPECTED_FAILURE("expected failure"), UNEXPECTED_SUCCESS("unexpected success"),
		/** unitTAS's own, not a test: a suite that doesn't exist, a class that can't run, a stop, a world that didn't load. */
		PROBLEM("problem");

		final String word;

		Outcome(String word) {
			this.word = word;
		}
	}

	private static final class Result {
		final String name;
		Outcome outcome;
		String detail = "";
		double seconds;
		List<TasGame.ChatLine> chat = new ArrayList<>();
		String screenshot;
		/** Why there is no screenshot, when one was wanted. */
		String noScreenshot;
		/** The game stopped ticking or running steps during this test. */
		boolean stuck;
		/** What the test did that works but shouldn't be relied on, each with where it was. */
		final List<String> warnings = new ArrayList<>();

		Result(String name) {
			this.name = name;
		}

		static Result problem(String name, String detail) {
			Result result = new Result(name);
			result.outcome = Outcome.PROBLEM;
			result.detail = detail;
			return result;
		}
	}

	/** A test: its method, run on an instance of the class its suite names (the method may be inherited). */
	private static final class Test {
		final Class<? extends TasTestCase> testClass;
		final Method method;
		/** `Class.method`, by the class that was asked for. */
		final String name;

		Test(Class<? extends TasTestCase> testClass, Method method) {
			this.testClass = testClass;
			this.method = method;
			this.name = testClass.getSimpleName() + "." + method.getName();
		}
	}

	private final TasGame game;
	private final UnitTas.Request request;
	private final List<Result> results = new ArrayList<>();

	TasRunner(TasGame game) {
		this.game = game;
		this.request = game.request();
	}

	/** A report for a run that never got to its tests (the world didn't load, say): the problem as its one error. */
	static void reportUnstarted(TasGame game, String name, String problem) {
		TasRunner runner = new TasRunner(game);
		runner.results.add(Result.problem(name, problem));
		runner.writeReport(0.0);
	}

	@Override
	public void run() {
		long start = System.currentTimeMillis();
		try {
			for (String problem : TasPlugins.problems()) {
				results.add(Result.problem("unitTAS.plugins", problem));
			}
			List<Test> tests = allTests();
			if (!request.saves.isEmpty()) {
				runSaves(tests);
			} else {
				game.activity("preparing the test world");
				prepareWorld();
				int number = 0;
				for (Test test : tests) {
					number++;
					Result result = runOne(test, "", true, "test " + number + "/" + tests.size() + " ");
					results.add(result);
					request.progress(String.format(Locale.ROOT, "test %d/%d %s ... %s", number, tests.size(), result.name, result.outcome.word));
					if (stopIfAborted(tests.size() - number) || stopIfStuck(result, tests.size() - number)) {
						break;
					}
				}
			}
		} catch (Throwable t) {
			results.add(Result.problem("unitTAS", stackTrace(t)));
			request.progress("unitTAS itself failed: " + t);
		}
		game.activity("writing the report");
		writeReport((System.currentTimeMillis() - start) / 1000.0);
		try {
			game.client(() -> {
				game.finish(Minecraft.getMinecraft());
				return null;
			});
		} catch (RuntimeException e) {
			UnitTas.LOG.error("Couldn't quit the game", e);
		}
	}

	private List<Test> allTests() {
		List<Test> tests = new ArrayList<>();
		for (String suite : request.suites) {
			Collection<String> classes = TasSuites.classNames(suite);
			if (classes == null) {
				Collection<String> names = TasSuites.names();
				String problem = "no suite called '" + suite + "' (there are: "
					+ (names.isEmpty() ? "none, no class is marked @TasSuite" : String.join(", ", names)) + ")";
				results.add(Result.problem("unitTAS.suites", problem));
				request.progress(problem);
				continue;
			}
			for (String className : classes) {
				Class<? extends TasTestCase> testClass = load(className);
				if (testClass != null) {
					tests.addAll(testsOf(testClass));
				}
			}
		}
		return tests;
	}

	/** The test class by name, or null (and an error in the report) when it can't run. */
	private Class<? extends TasTestCase> load(String className) {
		try {
			Class<?> type = Class.forName(className, true, TasRunner.class.getClassLoader());
			if (!TasTestCase.class.isAssignableFrom(type)) {
				results.add(Result.problem(className, "marked @TasSuite, but it doesn't extend TasTestCase"));
				return null;
			}
			if (Modifier.isAbstract(type.getModifiers())) {
				results.add(Result.problem(className, "marked @TasSuite, but abstract: mark the classes that extend it instead"));
				return null;
			}
			return type.asSubclass(TasTestCase.class);
		} catch (ClassNotFoundException | LinkageError e) {
			results.add(Result.problem(className, "can't load it: " + stackTrace(e)));
			return null;
		}
	}

	/** Seconds a save has to load (a world in another dimension, made elsewhere, loads slower than the flat test world). */
	private static final int SAVE_LOAD_SECONDS = 180;
	private static final int SAVE_SETTLE_TICKS = 60;

	/**
	 * Save mode: each save opened from the main menu in turn, twice (as found, then as this game saved it), the tests
	 * run in it as they find it: no resets, no game rule changes (they would change the save).
	 */
	private void runSaves(List<Test> tests) {
		int total = tests.size() * request.saves.size() * 2;
		int number = 0;
		for (int pass = 1; pass <= 2; pass++) {
			for (String folder : request.saves) {
				if (stopIfAborted(total - number)) {
					return;
				}
				game.activity("opening " + folder + ", load " + pass);
				TasLogErrors log = new TasLogErrors();
				TasSave save = new TasSave(folder, pass, request.oldSaves, log);
				try {
					log.listen();
				} catch (AssertionError e) {
					save.listenerProblem = e.getMessage();
				}
				request.progress("opening " + folder + (pass == 1 ? " as it was found" : " again, as this game saved it"));
				long asked = System.currentTimeMillis();
				String problem = openAndSettle(folder);
				save.loadSeconds = (System.currentTimeMillis() - asked) / 1000.0;
				save.loadErrors.addAll(log.errors);
				save.loadWarnings.addAll(log.warnings);
				TasSave.current = save;
				String suffix = " [" + folder + ", load " + pass + "]";
				if (problem != null) {
					results.add(Result.problem("TasRunner.openSave" + suffix, problem));
					request.progress(problem);
				} else {
					request.progress(String.format(Locale.ROOT, "%s loaded in %.0f s", folder, save.loadSeconds));
					for (Test test : tests) {
						number++;
						Result result = runOne(test, suffix, false, "test " + number + "/" + total + " ");
						results.add(result);
						request.progress(String.format(Locale.ROOT, "test %d/%d %s ... %s", number, total, result.name, result.outcome.word));
						if (stopIfAborted(total - number) || stopIfStuck(result, total - number)) {
							TasSave.current = null;
							log.quiet();
							return;
						}
					}
				}
				TasSave.current = null;
				log.quiet();
				game.activity("closing " + folder + ", load " + pass);
				String quit = quitAndWait();
				if (quit != null) {
					results.add(Result.problem("TasRunner.quitSave" + suffix, quit));
					request.progress(quit);
					return;
				}
			}
		}
	}

	/** Opens the save and waits for the player in it and the chunks around; null, or what went wrong. */
	private String openAndSettle(String folder) {
		try {
			game.client(() -> {
				game.openSave(folder);
				return null;
			});
		} catch (TasGame.Timeout e) {
			// the client thread is still starting the server (it shows the loading screen meanwhile): wait on below
		} catch (RuntimeException e) {
			return "couldn't open " + folder + ": " + stackTrace(e);
		}
		long started = System.currentTimeMillis();
		long giveUp = started + SAVE_LOAD_SECONDS * 1000L;
		while (true) {
			boolean in;
			try {
				in = game.client(game::inWorld);
			} catch (TasGame.Timeout e) {
				in = false;
			}
			if (in) {
				break;
			}
			if (System.currentTimeMillis() > giveUp) {
				// a watched run asks first
				TasWatch watch = game.watch();
				if (watch != null) {
					TasWatch.Decision decision = watch.ask(folder + " hasn't loaded in " + (System.currentTimeMillis() - started) / 1000 + " s", true,
						() -> !game.inWorldFromAfar(), "give up on this save and go on with the next",
						"unitTAS gives up on this save and goes on with the next");
					if (decision.action == TasWatch.Action.WAIT) {
						giveUp = System.currentTimeMillis() + decision.seconds * 1000L;
						continue;
					}
					if (decision.action == TasWatch.Action.CLEARED) {
						continue;
					}
					if (decision.action == TasWatch.Action.ABORT) {
						game.abort("the watcher aborted the run (alarm " + decision.alarm + "): " + decision.why);
					}
				}
				String picture;
				try {
					picture = game.client(() -> TasHang.picture(Minecraft.getMinecraft(), request.results, SAVE_LOAD_SECONDS));
				} catch (RuntimeException e) {
					picture = "none, the client is stuck";
				}
				return folder + " didn't load in " + SAVE_LOAD_SECONDS + " s (picture " + picture + ")";
			}
			sleep(250);
		}
		game.clientTicks(SAVE_SETTLE_TICKS);
		return null;
	}

	/** Save and quit to the title screen, and wait for the integrated server to have stopped; null, or the problem. */
	private String quitAndWait() {
		try {
			game.client(() -> {
				game.quitToMenu();
				return null;
			});
		} catch (TasGame.Timeout e) {
			// still saving: wait on below
		}
		long started = System.currentTimeMillis();
		long giveUp = started + SAVE_LOAD_SECONDS * 1000L;
		while (true) {
			MinecraftServer server = MinecraftServer.getServer();
			boolean stopped = server == null || server.isServerStopped();
			boolean menu;
			try {
				menu = game.client(() -> Minecraft.getMinecraft().currentScreen instanceof GuiMainMenu);
			} catch (TasGame.Timeout e) {
				menu = false;
			}
			if (stopped && menu) {
				return null;
			}
			if (System.currentTimeMillis() >= giveUp) {
				// a watched run asks first
				TasWatch watch = game.watch();
				if (watch == null) {
					break;
				}
				TasWatch.Decision decision = watch.ask("the save hasn't closed in " + (System.currentTimeMillis() - started) / 1000 + " s", true,
					() -> {
						MinecraftServer now = MinecraftServer.getServer();
						return now != null && !now.isServerStopped();
					}, "stop the run here (as abort)", "unitTAS stops the run here");
				if (decision.action == TasWatch.Action.WAIT) {
					giveUp = System.currentTimeMillis() + decision.seconds * 1000L;
				} else if (decision.action != TasWatch.Action.CLEARED) {
					break;
				}
			}
			sleep(250);
		}
		return "the save didn't close in " + (System.currentTimeMillis() - started) / 1000 + " s";
	}

	private static void sleep(long millis) {
		try {
			Thread.sleep(millis);
		} catch (InterruptedException e) {
			Thread.currentThread().interrupt();
		}
	}

	/** Steady conditions: no day and night, no weather, no mobs spawning on their own, no fire spread. */
	private void prepareWorld() {
		game.server(() -> {
			for (WorldServer world : MinecraftServer.getServer().worldServers) {
				GameRules rules = world.getGameRules();
				rules.setOrCreateGameRule("doDaylightCycle", "false");
				rules.setOrCreateGameRule("doMobSpawning", "false");
				rules.setOrCreateGameRule("doFireTick", "false");
				rules.setOrCreateGameRule("mobGriefing", "false");
				world.setWorldTime(6000);
				world.getWorldInfo().setRaining(false);
				world.getWorldInfo().setThundering(false);
			}
			return null;
		});
	}

	private List<Test> testsOf(Class<? extends TasTestCase> testClass) {
		List<Test> tests = new ArrayList<>();
		for (Method method : testClass.getMethods()) {
			if (method.getName().startsWith("test") && method.getParameterTypes().length == 0 && !Modifier.isStatic(method.getModifiers())) {
				Test test = new Test(testClass, method);
				if (request.filter == null || test.name.contains(request.filter)) {
					tests.add(test);
				}
			}
		}
		tests.sort(Comparator.comparing(test -> test.method.getName()));
		return tests;
	}

	/** One test; the label ("test 3/40 ") goes before its name in what the watch shows. */
	private Result runOne(Test test, String suffix, boolean resetFirst, String label) {
		Result result = new Result(test.name + suffix);
		game.testStarts(label + result.name);
		int chatMark = game.chatMark();
		long start = System.currentTimeMillis();
		ExpectedFailure expected = expectedFailure(test);
		Throwable problem = null;
		// the problem came from the test method itself (not setUp, tearDown or the run): what @ExpectedFailure covers
		boolean fromTest = false;
		boolean pictured = false;
		try {
			TasTestCase instance = test.testClass.getConstructor().newInstance();
			instance.attach(game);
			if (resetFirst) {
				reset();
			}
			// each test starts with no sounds heard, in save mode too (where nothing else is put back)
			UnitTasMode.clearSounds();
			chatMark = game.chatMark();
			game.startClock(instance.timeoutSeconds());
			instance.setUp();
			try {
				test.method.invoke(instance);
			} catch (Throwable t) {
				problem = unwrap(t);
				fromTest = true;
				// an expected failure goes without a picture: it says nothing new
				if (!(problem instanceof TasTestCase.Skip) && !asMarked(expected, problem)) {
					// the failure's picture before tearDown puts things away; tearDown then gets its own full time
					game.stopClock();
					Thread.interrupted();
					result.screenshot = screenshot(result);
					pictured = true;
					game.startClock(instance.timeoutSeconds());
				}
			} finally {
				try {
					instance.tearDown();
				} catch (Throwable t) {
					Throwable also = unwrap(t);
					if (problem == null) {
						problem = also;
					} else if (also != problem) {
						problem.addSuppressed(also);
					}
				}
			}
			if (problem == null) {
				// a sound the game doesn't have plays nothing, without a word: one the test caused fails it
				synchronized (UnitTasMode.SOUNDS_UNKNOWN) {
					if (!UnitTasMode.SOUNDS_UNKNOWN.isEmpty()) {
						problem = new AssertionError("played sounds the game doesn't have (silent): " + new ArrayList<>(UnitTasMode.SOUNDS_UNKNOWN_FROM));
					}
				}
			}
		} catch (Throwable t) {
			// making the instance, the reset, or setUp
			problem = unwrap(t);
		} finally {
			game.stopClock();
			Thread.interrupted();
		}
		if (problem == null && expected != null) {
			result.outcome = Outcome.UNEXPECTED_SUCCESS;
			result.detail = "marked @ExpectedFailure(\"" + expected.value() + "\"), but it passed: the mark can go";
		} else if (problem == null) {
			result.outcome = Outcome.OK;
		} else if (problem instanceof TasTestCase.Skip) {
			result.outcome = Outcome.SKIP;
			result.detail = problem.getMessage();
		} else if (fromTest && asMarked(expected, problem) && problem.getSuppressed().length == 0) {
			// as marked (a tearDown that also failed makes it what it is instead)
			result.outcome = Outcome.EXPECTED_FAILURE;
			result.detail = "expected: " + expected.value() + "\n"
				+ (problem instanceof AssertionError ? "AssertionError: " + problem.getMessage() : problem.toString()) + where(problem, test);
		} else if (problem instanceof AssertionError) {
			result.outcome = Outcome.FAIL;
			result.detail = "AssertionError: " + problem.getMessage() + where(problem, test);
			for (Throwable also : problem.getSuppressed()) {
				result.detail += "\ntearDown also failed: " + stackTrace(also);
			}
		} else {
			result.outcome = Outcome.ERROR;
			result.detail = stackTrace(problem);
		}
		result.stuck |= stuck(problem);
		if ((result.outcome == Outcome.FAIL || result.outcome == Outcome.ERROR) && !pictured) {
			result.screenshot = screenshot(result);
		}
		if (result.noScreenshot != null) {
			result.detail += "\n(no screenshot: " + result.noScreenshot + ")";
		}
		result.seconds = (System.currentTimeMillis() - start) / 1000.0;
		result.chat = game.chatSince(chatMark);
		for (Throwable warning : game.takeWarnings()) {
			// once for each place: a warning in a loop is one warning
			String line = warning.getMessage() + where(warning, test);
			if (!result.warnings.contains(line)) {
				result.warnings.add(line);
			}
		}
		game.testEnds();
		return result;
	}

	/** The test's @ExpectedFailure: on its method, or on its class (or a class above it). */
	private static ExpectedFailure expectedFailure(Test test) {
		ExpectedFailure mark = test.method.getAnnotation(ExpectedFailure.class);
		return mark != null ? mark : test.testClass.getAnnotation(ExpectedFailure.class);
	}

	/**
	 * The problem is one the mark covers: anything the test throws but unitTAS's own stops (out of time, the game
	 * stopped answering, the watcher's fail), which say nothing of what the test checks.
	 */
	private static boolean asMarked(ExpectedFailure expected, Throwable problem) {
		if (expected == null || problem instanceof TasTestCase.Skip) {
			return false;
		}
		for (Throwable t = problem; t != null; t = t.getCause()) {
			if (t instanceof TasGame.Timeout) {
				return false;
			}
		}
		return true;
	}

	private String screenshot(Result result) {
		try {
			return TasTestCase.screenshot(game, result.name);
		} catch (RuntimeException e) {
			result.noScreenshot = e.getMessage();
			result.stuck |= stuck(e);
			return null;
		}
	}

	private static Throwable unwrap(Throwable t) {
		return t instanceof InvocationTargetException && t.getCause() != null ? t.getCause() : t;
	}

	/** Whether the game stopped answering (a step or a tick that never came), anywhere in the problem's causes. */
	private static boolean stuck(Throwable problem) {
		for (Throwable t = problem; t != null; t = t.getCause()) {
			if (t instanceof TasGame.Timeout && ((TasGame.Timeout) t).stuck) {
				return true;
			}
		}
		return false;
	}

	/** "\n  at FooTests.testBar(FooTests.java:42)": the first frame in the test's own classes, or "" if none is. */
	private static String where(Throwable problem, Test test) {
		Set<String> own = new HashSet<>();
		for (Class<?> type = test.testClass; type != null && type != TasTestCase.class; type = type.getSuperclass()) {
			own.add(type.getName());
		}
		for (StackTraceElement frame : problem.getStackTrace()) {
			// the class itself, or one nested in it (a lambda's class is the class itself)
			for (String name = frame.getClassName(); ; name = name.substring(0, name.lastIndexOf('$'))) {
				if (own.contains(name)) {
					return "\n  at " + frame;
				}
				if (name.lastIndexOf('$') < 0) {
					break;
				}
			}
		}
		return "";
	}

	/**
	 * After a test the game stopped answering: if it no longer ticks, nothing else can run (each step would wait out
	 * its 15 s), so the run stops here, with the threads' dump. Returns whether it stopped.
	 */
	private boolean stopIfStuck(Result result, int left) {
		if (!result.stuck) {
			return false;
		}
		String why = stalled();
		// a watched run asks first, for as long as the watcher says to wait
		TasWatch watch = game.watch();
		while (why != null && watch != null) {
			TasWatch.Decision decision = watch.ask(why + " after " + result.name, true, () -> !game.tickingLately(5),
				"go on with the next test", "the run stops here, as it does unwatched");
			switch (decision.action) {
				case WAIT:
					waitForTicking(decision.seconds);
					why = stalled();
					break;
				case FAIL:
				case CLEARED:
					return false;
				case ABORT: {
					String problem = "the watcher stopped the run (alarm " + decision.alarm + ") after " + result.name + ": "
						+ decision.why + "; " + left + " test" + (left == 1 ? "" : "s") + " not run";
					results.add(Result.problem("unitTAS.aborted", problem));
					request.progress(problem);
					return true;
				}
				default:
					// no answer: as unwatched
					watch = null;
					break;
			}
		}
		if (why == null) {
			return false;
		}
		String dump;
		try {
			dump = TasHang.dump(Minecraft.getMinecraft(), request.results);
		} catch (RuntimeException e) {
			dump = "nowhere (" + e + ")";
		}
		String problem = why + " after " + result.name + "; the run stops here, " + left + " test" + (left == 1 ? "" : "s")
			+ " not run (threads in " + dump + ")";
		results.add(Result.problem("unitTAS.stopped", problem));
		request.progress(problem);
		return true;
	}

	/** The run stops when it was aborted (the watcher's abort); returns whether it stopped. */
	private boolean stopIfAborted(int left) {
		String reason = game.aborted();
		if (reason == null) {
			return false;
		}
		String problem = reason + "; " + left + " test" + (left == 1 ? "" : "s") + " not run";
		results.add(Result.problem("unitTAS.aborted", problem));
		request.progress(problem);
		return true;
	}

	/** Waits until the game ticks again, or the seconds have passed. */
	private void waitForTicking(int seconds) {
		long until = System.currentTimeMillis() + seconds * 1000L;
		while (System.currentTimeMillis() < until && !game.tickingLately(2)) {
			sleep(1000);
		}
	}

	/** Null when the game still ticks on both sides (an open screen, which may pause the server, closed first). */
	private String stalled() {
		Thread.interrupted();
		if (!game.ticking(true)) {
			return "the client stopped ticking";
		}
		try {
			game.client(() -> {
				Minecraft mc = Minecraft.getMinecraft();
				if (mc.currentScreen != null) {
					mc.displayGuiScreen((GuiScreen) null);
				}
				return null;
			});
		} catch (TasGame.Timeout e) {
			return "the client stopped running steps";
		}
		if (!game.ticking(false)) {
			return "the server stopped ticking";
		}
		return null;
	}

	/**
	 * Back to the start: no screen, no keys held, the player as new at the spawn point, the world empty of entities.
	 */
	private void reset() {
		game.client(() -> {
			Minecraft mc = Minecraft.getMinecraft();
			if (mc.currentScreen != null) {
				mc.displayGuiScreen((GuiScreen) null);
			}
			KeyBinding.unPressAllKeys();
			// the first hotbar slot, so a given item is the held one
			mc.thePlayer.inventory.currentItem = 0;
			mc.gameSettings.difficulty = EnumDifficulty.EASY;
			mc.gameSettings.thirdPersonView = 0;
			mc.gameSettings.hideGUI = false;
			return null;
		});
		// a test that left the player in another dimension: back to the overworld as the End's exit does (the only way
		// out of the End), which makes a new player entity
		boolean respawned = game.server(() -> {
			EntityPlayerMP player = TasGame.serverPlayer();
			if (player.dimension == 0) {
				return false;
			}
			// the connection must take the new entity, as vanilla's respawn request does; otherwise the client's packets
			// keep going to the removed one
			player.playerNetServerHandler.playerEntity = MinecraftServer.getServer().getConfigurationManager().recreatePlayerEntity(player, 0, true);
			return true;
		});
		for (int tick = 0; respawned && tick < 200; tick++) {
			if (game.client(() -> {
				Minecraft mc = Minecraft.getMinecraft();
				return mc.thePlayer != null && mc.thePlayer.dimension == 0 && !(mc.currentScreen instanceof GuiDownloadTerrain);
			})) {
				break;
			}
			game.clientTicks(1);
		}
		game.server(() -> {
			EntityPlayerMP player = TasGame.serverPlayer();
			// out of a bed an earlier test left the player in, and no bed of its to respawn at
			if (player.isPlayerSleeping()) {
				player.wakeUpPlayer(true, true, false);
			}
			player.setSpawnChunk(null, false, 0);
			player.inventory.clearInventory(null, -1);
			player.clearItemInUse();
			player.inventoryContainer.detectAndSendChanges();
			player.clearActivePotions();
			// arrows from earlier tests stay drawn stuck in the player, over what the next test's shots show
			player.setArrowCountInEntity(0);
			player.setGameType(WorldSettings.GameType.CREATIVE);
			// creative keeps the player flying if it was (1.7.10's game types stop flying only outside creative)
			player.capabilities.isFlying = false;
			player.sendPlayerAbilities();
			// no experience: below level 0 clears all of it, and the player's own addExperienceLevel sends it
			player.addExperienceLevel(-(player.experienceLevel + 1));
			player.extinguish();
			player.setHealth(player.getMaxHealth());
			player.getFoodStats().addStats(20, 20.0F);
			player.fallDistance = 0.0F;
			if (player.ridingEntity != null) {
				player.mountEntity(null);
			}
			player.playerNetServerHandler.setPlayerLocation(START_X, START_Y, START_Z, 0.0F, 0.0F);
			for (WorldServer world : MinecraftServer.getServer().worldServers) {
				world.difficultySetting = EnumDifficulty.EASY;
				world.setAllowedSpawnTypes(true, true);
				for (Object loaded : new ArrayList<Object>(world.loadedEntityList)) {
					if (!(loaded instanceof EntityPlayer)) {
						((Entity) loaded).setDead();
					}
				}
				world.weatherEffects.clear();
				// clear weather held: 1.7.10 has no weather-cycle rule, so its timers would turn rain on mid-run (a
				// `/weather clear 10s` left 200 ticks on them, and a long run reaches the natural turn), and rain darkens
				// the day and puts out fire; tests that want weather set it themselves
				world.getWorldInfo().setRaining(false);
				world.getWorldInfo().setThundering(false);
				world.getWorldInfo().setRainTime(1000000);
				world.getWorldInfo().setThunderTime(1000000);
				world.rainingStrength = world.prevRainingStrength = 0.0F;
				world.thunderingStrength = world.prevThunderingStrength = 0.0F;
			}
			// the mods' own part of the player (an off-hand slot, say)
			TasPlugins.resetPlayer(player);
			return null;
		});
		// the client's own rain too (code on the client may ask it)
		game.client(() -> {
			Minecraft mc = Minecraft.getMinecraft();
			if (mc.theWorld != null) {
				mc.theWorld.rainingStrength = mc.theWorld.prevRainingStrength = 0.0F;
				mc.theWorld.thunderingStrength = mc.theWorld.prevThunderingStrength = 0.0F;
			}
			return null;
		});
		game.clientTicks(3);
	}

	/**
	 * report.txt, as unittest prints its results: a line for each test, what went wrong under those that didn't pass,
	 * then the counts. unitTAS's own problems are counted apart from the tests, and fail the run as an error does; so
	 * does an unexpected success. The last line is OK or FAILED, which the scripts read for their exit code.
	 */
	private void writeReport(double seconds) {
		int tests = 0;
		int failures = 0;
		int errors = 0;
		int skipped = 0;
		int expectedFailures = 0;
		int unexpectedSuccesses = 0;
		int problems = 0;
		int warnings = 0;
		StringBuilder report = new StringBuilder();
		report.append("unitTAS report, ").append(new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.ROOT).format(new Date()))
			.append(", suites: ").append(String.join(", ", request.suites));
		if (request.filter != null) {
			report.append(", only '").append(request.filter).append("'");
		}
		report.append("\n\n");
		for (Result result : results) {
			report.append(String.format(Locale.ROOT, "%s ... %s (%.1f s)%n", result.name, result.outcome.word, result.seconds));
			switch (result.outcome) {
				case FAIL:
					failures++;
					break;
				case ERROR:
					errors++;
					break;
				case SKIP:
					skipped++;
					break;
				case EXPECTED_FAILURE:
					expectedFailures++;
					break;
				case UNEXPECTED_SUCCESS:
					unexpectedSuccesses++;
					break;
				case PROBLEM:
					problems++;
					break;
				default:
					break;
			}
			if (result.outcome != Outcome.PROBLEM) {
				tests++;
			}
			if (result.outcome != Outcome.OK) {
				for (String line : result.detail.split("\n")) {
					report.append("    ").append(line).append('\n');
				}
			}
			for (String warning : result.warnings) {
				String[] lines = warning.split("\n");
				report.append("    warning: ").append(lines[0]).append('\n');
				for (int i = 1; i < lines.length; i++) {
					report.append("    ").append(lines[i]).append('\n');
				}
				warnings++;
			}
			if (result.screenshot != null) {
				report.append("    screenshot: ").append(result.screenshot).append('\n');
			}
			if (result.outcome == Outcome.FAIL || result.outcome == Outcome.ERROR) {
				report.append("    chat during the test:\n");
				for (TasGame.ChatLine line : result.chat) {
					report.append("      | ").append(line.plain).append('\n');
				}
			}
		}
		report.append("----------------------------------------------------------------------\n");
		report.append(String.format(Locale.ROOT, "Ran %d %s in %.1f s", tests, tests == 1 ? "test" : "tests", seconds));
		if (problems > 0) {
			report.append(", ").append(problems).append(problems == 1 ? " problem" : " problems").append(" outside them");
		}
		if (warnings > 0) {
			report.append(", ").append(warnings).append(warnings == 1 ? " warning" : " warnings");
		}
		report.append("\n\n");
		// as unittest counts them, and unitTAS's own problems last
		List<String> counts = new ArrayList<>();
		String[] names = {"failures", "errors", "skipped", "expected failures", "unexpected successes", "problems"};
		int[] numbers = {failures, errors, skipped, expectedFailures, unexpectedSuccesses, problems};
		for (int i = 0; i < names.length; i++) {
			if (numbers[i] > 0) {
				counts.add(names[i] + "=" + numbers[i]);
			}
		}
		boolean ok = failures + errors + unexpectedSuccesses + problems == 0;
		String within = counts.isEmpty() ? "" : " (" + String.join(", ", counts) + ")";
		report.append(ok ? "OK" + within : "FAILED" + within).append('\n');
		File folder = request.results;
		if (!folder.isDirectory() && !folder.mkdirs()) {
			UnitTas.LOG.error("Can't make {}", folder);
		}
		try (Writer out = new OutputStreamWriter(new FileOutputStream(new File(folder, "report.txt")), StandardCharsets.UTF_8)) {
			out.write(report.toString());
		} catch (IOException e) {
			UnitTas.LOG.error("Can't write the report", e);
		}
		request.progress(ok ? "done: OK" : "done: FAILED");
	}

	/**
	 * The throwable with its causes and the ones it suppressed, each cut where unitTAS's plumbing starts (reflection,
	 * the step queue's FutureTask): the frames kept are the test's and the game's.
	 */
	static String stackTrace(Throwable t) {
		StringBuilder out = new StringBuilder();
		describe(t, "", out, Collections.newSetFromMap(new IdentityHashMap<>()));
		int end = out.length();
		while (end > 0 && out.charAt(end - 1) == '\n') {
			end--;
		}
		return out.substring(0, end);
	}

	private static void describe(Throwable t, String caption, StringBuilder out, Set<Throwable> seen) {
		if (!seen.add(t)) {
			out.append(caption).append("[seen above: ").append(t).append("]\n");
			return;
		}
		out.append(caption).append(t).append('\n');
		StackTraceElement[] frames = t.getStackTrace();
		int shown = 0;
		while (shown < frames.length && !plumbing(frames[shown])) {
			out.append("  at ").append(frames[shown]).append('\n');
			shown++;
		}
		if (shown < frames.length) {
			out.append("  ... ").append(frames.length - shown).append(" more\n");
		}
		for (Throwable suppressed : t.getSuppressed()) {
			describe(suppressed, "Suppressed: ", out, seen);
		}
		if (t.getCause() != null) {
			describe(t.getCause(), "Caused by: ", out, seen);
		}
	}

	private static boolean plumbing(StackTraceElement frame) {
		String owner = frame.getClassName();
		return owner.startsWith("sun.reflect.") || owner.startsWith("jdk.internal.reflect.")
			|| owner.equals("java.lang.reflect.Method") || owner.equals("java.util.concurrent.FutureTask");
	}
}

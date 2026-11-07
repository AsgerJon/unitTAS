package io.github.asgerjon.unittas;

import io.github.asgerjon.unittas.probe.Opening;
import io.github.asgerjon.unittas.probe.Reset;
import io.github.asgerjon.unittas.probe.Side;
import io.github.asgerjon.unittas.probe.Sides;
import io.github.asgerjon.unittas.probe.Worlds;
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
import net.minecraft.world.WorldServer;
import net.minecraft.world.WorldSettings;
import net.minecraft.world.WorldType;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.UncheckedIOException;
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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.function.Consumer;

/**
 * The test thread, as Python's unittest runs a suite: every public no-argument method whose name starts with `test`,
 * in name order, each on a fresh instance with setUp before and tearDown after. Between tests the player and the world
 * are put back (creative, empty inventory, no effects, at the spawn point, no other entities). A failure or error takes
 * a screenshot. At the end: the report, and the game quits.
 */
final class TasRunner implements Runnable {

	/** The spawn point every test starts from, on the flat world's grass. */
	static final double START_X = Reset.START_X;
	static final double START_Y = Reset.START_Y;
	static final double START_Z = Reset.START_Z;
	/** A class's own world (@TasWorld): a save folder apart, so the kept superflat world is never touched. */
	static final String CLASS_FOLDER = "unittas-class";

	/** Where the reset puts the player in the open world: the flat world's start, or a class world's own. */
	private volatile double startX = START_X;
	private volatile double startY = START_Y;
	private volatile double startZ = START_Z;
	/** The @TasWorld the open world was made for, or null while it is the run's superflat world. */
	private TasWorld classWorldOpen;

	private enum Outcome {
		OK("ok", "ok"), FAIL("FAIL", "fail"), ERROR("ERROR", "error"), SKIP("skipped", "skipped"),
		/** @ExpectedFailure: failed as marked; and passed although marked, which fails the run. */
		EXPECTED_FAILURE("expected failure", "expected_failure"), UNEXPECTED_SUCCESS("unexpected success", "unexpected_success"),
		/**
		 * No verdict at all (SPEC.md 9.8): the game stopped ticking during the test, so no test result could be had. Never
		 * an ERROR, whatever the test was marked: said first in the report, and it fails the run.
		 */
		NO_RESULT("NO RESULT", "no_result"),
		/** unitTAS's own, not a test: a suite that doesn't exist, a class that can't run, a stop, a world that didn't load. */
		PROBLEM("problem", "problem");

		/** As the report says it. */
		final String word;
		/** As java.result says it (PROTOCOL.md 8.14). */
		final String wire;

		Outcome(String word, String wire) {
			this.word = word;
			this.wire = wire;
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
		/** The world line the report prints before this one: the first line of a class says which world it ran in. */
		String worldNote;

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
	/** The tests counted so far and in all ("test 3/40"), for the progress lines and "N tests not run". */
	private int number;
	private int total;
	/** The world line for the next class's first line in the report ("world 2: fresh for GiveTests ..."). */
	private String worldNote;
	/** How many of the plugins' problems are in the report already. */
	private int pluginProblemsSeen;
	/** The tests not run because the game stayed stuck: they have no result either, and the report's headline counts them. */
	private int notRunStuck;

	TasRunner(TasGame game) {
		this.game = game;
		this.request = game.request();
	}

	/** A report for a run that never got to its tests (the world didn't load, say): the problem as its one error. */
	static void reportUnstarted(TasGame game, String name, String problem) {
		TasRunner runner = new TasRunner(game);
		runner.record(Result.problem(name, problem));
		runner.writeReport(0.0);
	}

	@Override
	public void run() {
		long start = System.currentTimeMillis();
		try {
			for (String problem : TasPlugins.problems()) {
				record(Result.problem("unitTAS.plugins", problem));
			}
			pluginProblemsSeen = TasPlugins.problems().size();
			List<Test> tests = allTests();
			if (!request.saves.isEmpty()) {
				runSaves(tests);
			} else {
				game.activity("preparing the test world");
				prepareWorld();
				total = tests.size();
				String problem = null;
				if (needsFreshWorlds(tests)) {
					// the world as made, kept aside: each class after the first gets it back (unless @SharedWorld)
					game.activity("keeping the test world aside");
					problem = keepPristine();
				}
				if (problem != null) {
					problem = "couldn't keep the test world aside for the classes' fresh worlds: " + problem + "; " + notRun(total);
					record(Result.problem("unitTAS.world", problem));
					request.progress(problem);
				} else {
					worldHooks("setUpWorld");
					runTests(tests, "", true, true);
					worldHooks("tearDownWorld");
				}
			}
		} catch (Throwable t) {
			record(Result.problem("unitTAS", stackTrace(t)));
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
				record(Result.problem("unitTAS.suites", problem));
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
				record(Result.problem(className, "marked @TasSuite, but it doesn't extend TasTestCase"));
				return null;
			}
			if (Modifier.isAbstract(type.getModifiers())) {
				record(Result.problem(className, "marked @TasSuite, but abstract: mark the classes that extend it instead"));
				return null;
			}
			return type.asSubclass(TasTestCase.class);
		} catch (ClassNotFoundException | LinkageError e) {
			record(Result.problem(className, "can't load it: " + stackTrace(e)));
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
		total = tests.size() * request.saves.size() * 2;
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
					record(Result.problem("TasRunner.openSave" + suffix, problem));
					request.progress(problem);
				} else {
					request.progress(String.format(Locale.ROOT, "%s loaded in %.0f s", folder, save.loadSeconds));
					// the saves are the worlds: no fresh ones, no world hooks (they would change the saves)
					if (!runTests(tests, suffix, false, false)) {
						TasSave.current = null;
						log.quiet();
						return;
					}
				}
				TasSave.current = null;
				log.quiet();
				game.activity("closing " + folder + ", load " + pass);
				String quit = quitAndWait();
				if (quit != null) {
					record(Result.problem("TasRunner.quitSave" + suffix, quit));
					request.progress(quit);
					return;
				}
			}
		}
	}

	/** Opens the save and waits for the player in it and the chunks around; null, or what went wrong. */
	private String openAndSettle(String folder) {
		return settle(folder, () -> game.openSave(folder));
	}

	/**
	 * Begins a world on the client thread (opens a save, or makes a world) and waits for the player in it and the chunks
	 * around, with the opening guard (a dropped login opens the save again); null, or what went wrong.
	 */
	private String settle(String folder, Runnable begin) {
		try {
			game.client(() -> {
				begin.run();
				return null;
			});
		} catch (TasGame.Timeout e) {
			// the client thread is still starting the server (it shows the loading screen meanwhile): wait on below
		} catch (RuntimeException e) {
			return "couldn't open " + folder + ": " + stackTrace(e);
		}
		long started = System.currentTimeMillis();
		long giveUp = started + SAVE_LOAD_SECONDS * 1000L;
		// the opening guard (Opening): a login the integrated server dropped is pictured and the save opened again, once
		Opening opening = new Opening();
		Sides sides = Sides.get();
		int dropped = 0;
		while (true) {
			boolean in;
			boolean title;
			try {
				in = game.client(game::inWorld);
				title = !in && game.client(() -> Minecraft.getMinecraft().currentScreen instanceof GuiMainMenu);
			} catch (TasGame.Timeout e) {
				in = false;
				title = false;
			}
			if (in) {
				break;
			}
			MinecraftServer server = MinecraftServer.getServer();
			boolean serverUp = server != null && !server.isServerStopped() && sides.tickedAt(Side.SERVER) > 0;
			String hung = opening.dropped(title, serverUp, false, sides.ticks(Side.CLIENT), sides.ticks(Side.SERVER))
				? Opening.DROPPED : null;
			if (hung != null) {
				dropped++;
				String name = folder + "-dropped-" + dropped + ".png";
				String picture;
				try {
					picture = game.client(() -> TasHang.picture(Minecraft.getMinecraft(), request.results, name));
				} catch (RuntimeException e) {
					picture = "none (" + e.getMessage() + ")";
				}
				if (dropped > Opening.RETRIES) {
					return folder + ": " + hung + "; and again after it was opened once more (picture " + picture + ")";
				}
				request.progress(folder + ": " + hung + ": left and opened again (picture " + picture + ")");
				try {
					game.client(() -> {
						// left as Save and Quit leaves a world (its server stopped), then the save opened again
						Worlds.close(Minecraft.getMinecraft());
						game.openSave(folder);
						return null;
					});
				} catch (TasGame.Timeout e) {
					// the client thread is starting the server again: wait on below
				}
				opening.reset();
				continue;
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
	/** The steady world (Worlds.prepare), the same body as the probe's world.prepare: one way to set a test world. */
	private void prepareWorld() {
		game.server(() -> {
			Worlds.prepare();
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

	private static String notRun(int left) {
		return left + " test" + (left == 1 ? "" : "s") + " not run";
	}

	/**
	 * A class after the first that isn't @SharedWorld needs the world as made, and so does any class after one with a
	 * world of its own (@TasWorld): then it's kept aside before the first.
	 */
	private static boolean needsFreshWorlds(List<Test> tests) {
		for (Test test : tests) {
			if (test.testClass.isAnnotationPresent(TasWorld.class)) {
				return true;
			}
			if (test.testClass != tests.get(0).testClass && !test.testClass.isAnnotationPresent(SharedWorld.class)) {
				return true;
			}
		}
		return false;
	}

	/** Closes the test world, copies it aside as it is (made, its game rules set), and opens it again; null, or what went wrong. */
	private String keepPristine() {
		String quit = quitAndWait();
		if (quit != null) {
			return quit;
		}
		try {
			game.keepPristine();
		} catch (IOException | UncheckedIOException e) {
			return "couldn't copy it: " + e;
		}
		return openAndSettle(TasGame.WORLD_FOLDER);
	}

	/**
	 * A class's fresh world: the world closed, the copy kept as it was made put back over it, exactly (what the classes
	 * since made, the End included, is gone), and opened again. Null, or what went wrong.
	 */
	private String freshWorld() {
		worldHooks("tearDownWorld");
		String quit = quitAndWait();
		if (quit != null) {
			return quit;
		}
		try {
			game.restorePristine();
		} catch (IOException | UncheckedIOException e) {
			return "couldn't put the kept world back: " + e;
		}
		String open = openAndSettle(TasGame.WORLD_FOLDER);
		if (open != null) {
			return open;
		}
		startX = START_X;
		startY = START_Y;
		startZ = START_Z;
		classWorldOpen = null;
		game.nextWorld();
		worldHooks("setUpWorld");
		return null;
	}

	/**
	 * A class's own world (@TasWorld): the open world closed (its tearDownWorld first), an earlier class world's folder
	 * gone, the world made fresh in CLASS_FOLDER with the class's settings and waited for, given the run's steady
	 * settings (prepareWorld), its setUpWorld run. The reset's start from then is where the game put the player in it:
	 * a world with real terrain has no fixed height to put it at. Null, or what went wrong.
	 */
	private String classWorld(TasWorld world) {
		WorldType type = Worlds.type(world.type());
		if (type == null) {
			return "its @TasWorld type is " + world.type() + ", not default, flat, large_biomes or amplified";
		}
		String generator = world.generator().isEmpty() && type == WorldType.FLAT ? Worlds.FLAT_LAYERS : world.generator();
		worldHooks("tearDownWorld");
		String quit = quitAndWait();
		if (quit != null) {
			return quit;
		}
		game.client(() -> {
			Minecraft.getMinecraft().getSaveLoader().flushCache();
			Minecraft.getMinecraft().getSaveLoader().deleteWorldDirectory(CLASS_FOLDER);
			return null;
		});
		String made = settle(CLASS_FOLDER, () -> Worlds.create(Minecraft.getMinecraft(), CLASS_FOLDER, Worlds.NAME,
			world.seed(), type, generator, WorldSettings.GameType.CREATIVE, true, world.structures()));
		if (made != null) {
			return made;
		}
		prepareWorld();
		double[] at = game.server(() -> {
			EntityPlayerMP player = TasGame.serverPlayer();
			return new double[]{player.posX, player.posY, player.posZ};
		});
		startX = at[0];
		startY = at[1];
		startZ = at[2];
		classWorldOpen = world;
		game.nextWorld();
		worldHooks("setUpWorld");
		return null;
	}

	/** The plugins' setUpWorld or tearDownWorld, on the server thread; a hook that throws is a problem in the report. */
	private void worldHooks(String which) {
		Consumer<TasHooks> call = "setUpWorld".equals(which) ? TasHooks::setUpWorld : TasHooks::tearDownWorld;
		game.server(() -> {
			TasPlugins.each(which, request, call);
			return null;
		});
		List<String> problems = TasPlugins.problems();
		for (int i = pluginProblemsSeen; i < problems.size(); i++) {
			record(Result.problem("unitTAS.plugins", problems.get(i)));
		}
		pluginProblemsSeen = problems.size();
	}

	/**
	 * The tests in order, a class at a time: the class's world (where fresh worlds are given: the run's own for the
	 * first class, for each later one the kept world put back, unless it is @SharedWorld), its setUpClass, its tests,
	 * its tearDownClass. False when the run stopped.
	 */
	private boolean runTests(List<Test> tests, String suffix, boolean resetFirst, boolean freshWorlds) {
		String previous = null;
		int i = 0;
		while (i < tests.size()) {
			Class<? extends TasTestCase> testClass = tests.get(i).testClass;
			int end = i;
			while (end < tests.size() && tests.get(end).testClass == testClass) {
				end++;
			}
			String name = testClass.getSimpleName();
			TasWorld own = testClass.getAnnotation(TasWorld.class);
			if (freshWorlds) {
				if (own != null) {
					if (testClass.isAnnotationPresent(SharedWorld.class) && own.equals(classWorldOpen)) {
						worldNote = "world " + game.worldNumber() + ", shared: " + name + " runs in it as " + previous + " left it";
					} else {
						game.activity("making " + name + "'s own world");
						long asked = System.currentTimeMillis();
						String problem = classWorld(own);
						if (problem != null) {
							problem = "couldn't give " + name + " its own world: " + problem + "; " + notRun(total - number);
							record(Result.problem("unitTAS.world", problem));
							request.progress(problem);
							return false;
						}
						worldNote = String.format(Locale.ROOT, "world %d: fresh for %s, made as it asks (type %s, seed %d; made in"
							+ " %.1f s)", game.worldNumber(), name, own.type(), own.seed(), (System.currentTimeMillis() - asked) / 1000.0);
					}
				} else if (previous == null && classWorldOpen == null) {
					worldNote = "world " + game.worldNumber() + ": the run's first, for " + name;
				} else if (testClass.isAnnotationPresent(SharedWorld.class) && classWorldOpen == null) {
					worldNote = "world " + game.worldNumber() + ", shared: " + name + " runs in it as " + previous + " left it";
				} else {
					game.activity("putting the test world back for " + name);
					long asked = System.currentTimeMillis();
					String problem = freshWorld();
					if (problem != null) {
						problem = "couldn't give " + name + " a fresh world: " + problem + "; " + notRun(total - number);
						record(Result.problem("unitTAS.world", problem));
						request.progress(problem);
						return false;
					}
					worldNote = String.format(Locale.ROOT, "world %d: fresh for %s (the kept world put back, opened in %.1f s)",
						game.worldNumber(), name, (System.currentTimeMillis() - asked) / 1000.0);
				}
				request.progress(worldNote);
			}
			previous = name;
			if (!runClass(testClass, tests.subList(i, end), suffix, resetFirst)) {
				return false;
			}
			i = end;
		}
		return true;
	}

	/** A line of the report, as it comes: a java.run's probe hears it at once (TasGame.resultLine). */
	private void record(Result result) {
		results.add(result);
		game.resultLine(result.name, result.outcome.wire, result.seconds, result.detail);
	}

	/** A result of the running class, in the report and the progress; the class's first takes its world line. */
	private void addResult(Result result) {
		if (worldNote != null && result.outcome != Outcome.PROBLEM) {
			result.worldNote = worldNote;
			worldNote = null;
		}
		record(result);
		request.progress(String.format(Locale.ROOT, "test %d/%d %s ... %s", number, total, result.name, result.outcome.word));
	}

	/** One class, as unittest runs one: setUpClass, its tests, tearDownClass. False when the run stopped. */
	private boolean runClass(Class<? extends TasTestCase> testClass, List<Test> tests, String suffix, boolean resetFirst) {
		Result setUp = runFixture(testClass, "setUpClass", suffix, resetFirst);
		if (setUp.outcome == Outcome.SKIP) {
			for (Test test : tests) {
				number++;
				Result skipped = new Result(test.name + suffix);
				skipped.outcome = Outcome.SKIP;
				skipped.detail = "setUpClass: " + setUp.detail;
				addResult(skipped);
			}
			return !stopIfAborted(total - number);
		}
		if (setUp.outcome != Outcome.OK) {
			number += tests.size();
			setUp.detail += "\n(its " + notRun(tests.size()) + ")";
			addResult(setUp);
			return !(stopIfAborted(total - number) || stopIfStuck(setUp, total - number));
		}
		Result last = null;
		for (Test test : tests) {
			number++;
			Result result = runOne(test, suffix, resetFirst, "test " + number + "/" + total + " ");
			if (last == null) {
				result.warnings.addAll(0, prefixed(setUp.warnings, "setUpClass: "));
			}
			addResult(result);
			last = result;
			if (stopIfAborted(total - number) || stopIfStuck(result, total - number)) {
				return false;
			}
		}
		Result tearDown = runFixture(testClass, "tearDownClass", suffix, false);
		if (tearDown.outcome == Outcome.OK || tearDown.outcome == Outcome.SKIP) {
			last.warnings.addAll(prefixed(tearDown.warnings, "tearDownClass: "));
			return true;
		}
		addResult(tearDown);
		return !(stopIfAborted(total - number) || stopIfStuck(tearDown, total - number));
	}

	private static List<String> prefixed(List<String> warnings, String prefix) {
		List<String> out = new ArrayList<>();
		for (String warning : warnings) {
			out.add(prefix + warning);
		}
		return out;
	}

	/**
	 * setUpClass or tearDownClass, on an instance of its own, with the class's time limit. Its result goes in the
	 * report only when it didn't pass; anything it throws is an error, as in unittest (skipTest skips the class).
	 */
	private Result runFixture(Class<? extends TasTestCase> testClass, String which, String suffix, boolean resetFirst) {
		Result result = new Result(testClass.getSimpleName() + "." + which + suffix);
		game.testStarts(result.name);
		int chatMark = game.chatMark();
		long start = System.currentTimeMillis();
		Throwable problem = null;
		try {
			TasTestCase instance = testClass.getConstructor().newInstance();
			instance.attach(game);
			if (resetFirst) {
				reset();
			}
			chatMark = game.chatMark();
			game.startClock(instance.timeoutSeconds());
			if ("setUpClass".equals(which)) {
				instance.setUpClass();
			} else {
				instance.tearDownClass();
			}
		} catch (Throwable t) {
			problem = unwrap(t);
		} finally {
			game.stopClock();
			Thread.interrupted();
		}
		if (problem == null) {
			result.outcome = Outcome.OK;
		} else if (problem instanceof TasTestCase.Skip) {
			result.outcome = Outcome.SKIP;
			result.detail = problem.getMessage();
		} else if (timedOut(problem)) {
			result.outcome = Outcome.NO_RESULT;
			result.detail = noResult(problem);
			result.stuck |= stuck(problem);
		} else {
			result.outcome = Outcome.ERROR;
			result.detail = problem instanceof AssertionError
				? "AssertionError: " + problem.getMessage() + where(problem, testClass) : stackTrace(problem);
			result.stuck |= stuck(problem);
			result.screenshot = screenshot(result);
			if (result.noScreenshot != null) {
				result.detail += "\n(no screenshot: " + result.noScreenshot + ")";
			}
		}
		result.seconds = (System.currentTimeMillis() - start) / 1000.0;
		result.chat = game.chatSince(chatMark);
		for (Throwable warning : game.takeWarnings()) {
			String line = warning.getMessage() + where(warning, testClass);
			if (!result.warnings.contains(line)) {
				result.warnings.add(line);
			}
		}
		game.testEnds();
		return result;
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
		if (problem != null && timedOut(problem)) {
			// before any other reading of it: a stuck game, the test's time limit, the watcher's stop. An expected
			// failure that couldn't run to its verdict has no result either
			result.outcome = Outcome.NO_RESULT;
			result.detail = noResult(problem);
			result.stuck |= stuck(problem);
		} else if (problem == null && expected != null) {
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
	/** What a no result says: that there is none, and why (the stall's own words), with where it stopped. */
	private static String noResult(Throwable problem) {
		Throwable timeout = problem;
		while (timeout != null && !(timeout instanceof TasGame.Timeout)) {
			timeout = timeout.getCause();
		}
		return "no test result could be obtained: " + (timeout == null ? problem : timeout.getMessage()) + "\n"
			+ stackTrace(problem);
	}

	/**
	 * Whether the test ended without a verdict (SPEC.md 9.8): a TasGame.Timeout among its causes, which is a game that
	 * stopped ticking, the test's own wall-clock limit, or the watcher's stop. Only a stuck one stops the run.
	 */
	private static boolean timedOut(Throwable problem) {
		for (Throwable t = problem; t != null; t = t.getCause()) {
			if (t instanceof TasGame.Timeout) {
				return true;
			}
		}
		return false;
	}

	private static boolean stuck(Throwable problem) {
		for (Throwable t = problem; t != null; t = t.getCause()) {
			if (t instanceof TasGame.Timeout && ((TasGame.Timeout) t).stuck) {
				return true;
			}
		}
		return false;
	}

	private static String where(Throwable problem, Test test) {
		return where(problem, test.testClass);
	}

	/** "\n  at FooTests.testBar(FooTests.java:42)": the first frame in the test's own classes, or "" if none is. */
	private static String where(Throwable problem, Class<?> testClass) {
		Set<String> own = new HashSet<>();
		for (Class<?> type = testClass; type != null && type != TasTestCase.class; type = type.getSuperclass()) {
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
					record(Result.problem("unitTAS.aborted", problem));
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
		notRunStuck += left;
		String problem = why + " after " + result.name + "; the run stops here, " + left + " test" + (left == 1 ? "" : "s")
			+ " not run (threads in " + dump + ")";
		record(Result.problem("unitTAS.stopped", problem));
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
		record(Result.problem("unitTAS.aborted", problem));
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
			Reset.client(Minecraft.getMinecraft());
			return null;
		});
		// a test that left the player in another dimension: back to the overworld as the End's exit does
		boolean respawned = game.server(() -> Reset.respawnIfAway(TasGame.serverPlayer()));
		for (int tick = 0; respawned && tick < 200; tick++) {
			if (game.client(() -> {
				Minecraft mc = Minecraft.getMinecraft();
				return mc.thePlayer != null && mc.thePlayer.dimension == 0 && !(mc.currentScreen instanceof GuiDownloadTerrain);
			})) {
				break;
			}
			game.clientTicks(1);
		}
		// the server's part in one step, as the probe's batch does it: the player, every dimension, the mods' own part
		game.server(() -> {
			EntityPlayerMP player = TasGame.serverPlayer();
			Reset.player(player, startX, startY, startZ, 0.0F, 0.0F);
			Reset.world();
			TasPlugins.resetPlayer(player);
			return null;
		});
		game.client(() -> {
			Reset.clientWeather(Minecraft.getMinecraft());
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
		int noResults = 0;
		String firstNoResult = null;
		for (Result result : results) {
			if (result.outcome == Outcome.NO_RESULT && firstNoResult == null) {
				firstNoResult = result.name + ": " + result.detail.split("\n")[0];
			}
		}
		StringBuilder report = new StringBuilder();
		report.append("unitTAS report, ").append(new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.ROOT).format(new Date()))
			.append(", suites: ").append(String.join(", ", request.suites));
		if (request.filter != null) {
			report.append(", only '").append(request.filter).append("'");
		}
		if (firstNoResult != null) {
			// said first, before any line: these tests have no verdict at all (SPEC.md 9.8)
			int none = notRunStuck;
			for (Result result : results) {
				none += result.outcome == Outcome.NO_RESULT ? 1 : 0;
			}
			report.append("\nNO TEST RESULT could be obtained for ").append(none).append(none == 1 ? " test: " : " tests: ")
				.append(firstNoResult);
		}
		report.append("\n\n");
		for (Result result : results) {
			if (result.worldNote != null) {
				report.append(result.worldNote).append('\n');
			}
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
				case NO_RESULT:
					noResults++;
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
		String[] names = {"failures", "errors", "skipped", "expected failures", "unexpected successes", "no results",
			"problems"};
		int[] numbers = {failures, errors, skipped, expectedFailures, unexpectedSuccesses, noResults, problems};
		for (int i = 0; i < names.length; i++) {
			if (numbers[i] > 0) {
				counts.add(names[i] + "=" + numbers[i]);
			}
		}
		boolean ok = failures + errors + unexpectedSuccesses + noResults + problems == 0;
		Map<String, Integer> summary = new LinkedHashMap<>();
		summary.put("ran", tests);
		summary.put("failures", failures);
		summary.put("errors", errors);
		summary.put("skipped", skipped);
		summary.put("expected_failures", expectedFailures);
		summary.put("unexpected_successes", unexpectedSuccesses);
		summary.put("no_results", noResults);
		summary.put("problems", problems);
		String within = counts.isEmpty() ? "" : " (" + String.join(", ", counts) + ")";
		report.append(ok ? "OK" + within : "FAILED" + within).append('\n');
		File folder = request.results;
		if (!folder.isDirectory() && !folder.mkdirs()) {
			UnitTas.LOG.error("Can't make {}", folder);
		}
		File written = new File(folder, "report.txt");
		try (Writer out = new OutputStreamWriter(new FileOutputStream(written), StandardCharsets.UTF_8)) {
			out.write(report.toString());
			game.reported(written, ok, summary);
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

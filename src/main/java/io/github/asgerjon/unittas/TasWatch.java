package io.github.asgerjon.unittas;

import net.minecraft.client.Minecraft;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.locks.ReentrantLock;
import java.util.function.BooleanSupplier;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Eyes on a run, for whoever watches it, most likely an LLM (README.md, "Hangs, and watching a run").
 * <p>
 * Always: every few seconds a picture of the window (screenshots/watch-live.png, and the one before it,
 * watch-previous.png) and a few lines on what the run is doing (watch.txt).
 * <p>
 * In a watched run (watched=true in the request), where unitTAS would otherwise go by a fixed limit (a test past its
 * time, a world that doesn't load, a game that stopped answering), it raises an alarm instead: alarm.txt says what it
 * sees, with two pictures a few seconds apart, and the watcher answers in decision.txt: wait longer, fail the test,
 * or abort the run. Without an answer in time, unitTAS does what it does unwatched. Only whether something is stuck
 * is the watcher's call; whether a test passed never is.
 */
final class TasWatch implements Runnable {

	enum Action {WAIT, FAIL, ABORT, CLEARED, NO_ANSWER}

	/** The answer to an alarm: the watcher's, or CLEARED (the situation passed by itself), or NO_ANSWER in time. */
	static final class Decision {
		final int alarm;
		final Action action;
		final int seconds;
		final String why;

		Decision(int alarm, Action action, int seconds, String why) {
			this.alarm = alarm;
			this.action = action;
			this.seconds = seconds;
			this.why = why;
		}

		@Override
		public String toString() {
			return action == Action.WAIT ? "wait " + seconds + " s" : action.name().toLowerCase(Locale.ROOT) + (why.isEmpty() ? "" : ": " + why);
		}
	}

	/** How long the test world may load before a watched run asks (an unwatched one gives up then). */
	static final int LOAD_SECONDS = 60;
	private static final int STATUS_SECONDS = 5;
	private static final int PICTURE_GAP_MILLIS = 3000;
	private static final int REMIND_SECONDS = 60;
	private static final Pattern DECISION = Pattern.compile("^\\s*#?(\\d+)?\\s*(wait|fail|abort)\\b\\s*(.*)$", Pattern.CASE_INSENSITIVE);

	private final TasGame game;
	private final UnitTas.Request request;
	/** One alarm at a time. The watch thread only tries it: it never waits on another thread's alarm. */
	private final ReentrantLock alarmLock = new ReentrantLock();
	private Thread thread;
	private int alarms;
	private volatile int openAlarm;
	private volatile String lastPicture = "none yet";
	private long nextPicture;
	private long nextStatus;
	private long loadAlarmAfter;
	/** The watch gave up on a world the client can't leave: it wrote the report itself and is done. */
	private boolean gaveUp;

	TasWatch(TasGame game) {
		this.game = game;
		this.request = game.request();
	}

	void start() {
		thread = new Thread(this, "unitTAS watch");
		thread.setDaemon(true);
		thread.start();
	}

	@Override
	public void run() {
		nextPicture = System.currentTimeMillis() + request.watchPictures * 1000L;
		while (!game.done() && !gaveUp) {
			try {
				housekeeping();
				if (request.watched) {
					checkAlarms();
				}
			} catch (RuntimeException e) {
				UnitTas.LOG.error("unitTAS's watch failed a round", e);
			}
			if (!sleep(1000)) {
				return;
			}
		}
	}

	// ---------------------------------------------------------------- always: the live picture and watch.txt

	private void housekeeping() {
		long now = System.currentTimeMillis();
		if (request.watchPictures > 0 && now >= nextPicture) {
			nextPicture = now + request.watchPictures * 1000L;
			livePicture();
		}
		if (now >= nextStatus) {
			nextStatus = now + STATUS_SECONDS * 1000L;
			writeStatus();
		}
	}

	/** watch-live.png, the one before it kept as watch-previous.png; the new one appears whole (moved in). */
	private void livePicture() {
		if (!game.clientTickedWithin(3)) {
			lastPicture = "none at " + clock(System.currentTimeMillis()) + ": the client isn't ticking";
			return;
		}
		File shots = new File(request.results, "screenshots");
		File fresh = new File(shots, "watch-new.png");
		File live = new File(shots, "watch-live.png");
		File previous = new File(shots, "watch-previous.png");
		try {
			Files.deleteIfExists(fresh.toPath());
			game.client(() -> TasHang.picture(Minecraft.getMinecraft(), request.results, fresh.getName()));
			if (!fresh.isFile()) {
				lastPicture = "none at " + clock(System.currentTimeMillis()) + ": the screenshot failed (the game's log says why)";
				return;
			}
			if (live.isFile()) {
				Files.move(live.toPath(), previous.toPath(), StandardCopyOption.REPLACE_EXISTING);
			}
			Files.move(fresh.toPath(), live.toPath(), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
			lastPicture = live.getAbsolutePath() + ", taken " + clock(System.currentTimeMillis());
		} catch (IOException | RuntimeException e) {
			lastPicture = "none at " + clock(System.currentTimeMillis()) + ": " + e;
		}
	}

	private void writeStatus() {
		long now = System.currentTimeMillis();
		int open = openAlarm;
		String status = "unitTAS watch, " + clock(now) + "\n"
			+ "run: " + situation() + "\n"
			+ "client: " + ticking(game.clientTickedAt(), now) + "\n"
			+ "server: " + (game.serverExpected() ? ticking(game.serverTickedAt(), now) : "none running") + "\n"
			+ "picture: " + lastPicture + " (the one before it: screenshots/watch-previous.png)\n"
			+ "alarm: " + (open == 0 ? "none open" : open + " open: " + new File(request.results, "alarm.txt").getAbsolutePath()) + "\n";
		writeWhole(new File(request.results, "watch.txt"), status);
	}

	/** "test 12/40 FooTests.testBar, 34 s in (its limit 60 s); doing: waiting for 'x' (tick 3 of 200)". */
	String situation() {
		StringBuilder out = new StringBuilder(game.activity());
		if (game.inTest()) {
			out.append(", ").append(secondsSince(game.testStartedAt())).append(" s in (its limit ").append(game.testLimitSeconds()).append(" s)");
		}
		String doing = game.doing();
		if (doing != null) {
			out.append("; doing: ").append(doing);
		}
		return out.toString();
	}

	private static String ticking(long at, long now) {
		if (at == 0) {
			return "hasn't ticked yet";
		}
		long ago = (now - at) / 1000;
		return ago < 2 ? "ticking" : "last ticked " + ago + " s ago";
	}

	// ---------------------------------------------------------------- watched: the alarms the watch raises itself

	private void checkAlarms() {
		long now = System.currentTimeMillis();
		if (game.stage() == TasGame.Stage.LOADING) {
			if (now - game.loadingSince() > LOAD_SECONDS * 1000L && now >= loadAlarmAfter) {
				loadingAlarm();
			}
		} else if (game.inTest() && game.testOverTime()) {
			testTimeAlarm();
		}
	}

	private void testTimeAlarm() {
		int test = game.testNumber();
		int limit = game.testLimitSeconds();
		Decision decision = ask("the test has run past its time limit (" + limit + " s)", false,
			() -> game.inTest() && game.testNumber() == test && game.testOverTime(),
			"stop this test as an error, with your reason, and go on with the next",
			"the test is stopped as having run out of time");
		switch (decision.action) {
			case WAIT:
				game.extendClock(test, decision.seconds);
				break;
			case FAIL:
				game.stopTest(test, "stopped by the watcher (alarm " + decision.alarm + "): " + decision.why);
				break;
			case ABORT:
				game.abort("the watcher aborted the run (alarm " + decision.alarm + "): " + decision.why);
				break;
			case NO_ANSWER:
				game.stopTest(test, "the test ran out of time (" + limit + " s, and no answer to alarm " + decision.alarm + ")");
				break;
			default:
				break;
		}
	}

	private void loadingAlarm() {
		Decision decision = ask("the test world hasn't loaded in " + secondsSince(game.loadingSince()) + " s", true,
			() -> game.stage() == TasGame.Stage.LOADING,
			"give up on the world (as abort)",
			"unitTAS gives up on the world: the run ends with the threads and the loading trace");
		switch (decision.action) {
			case WAIT:
				loadAlarmAfter = System.currentTimeMillis() + decision.seconds * 1000L;
				break;
			case CLEARED:
				break;
			default:
				giveUpLoading(decision.action == Action.NO_ANSWER
					? "the test world didn't load (no answer to alarm " + decision.alarm + ")"
					: "the watcher gave up on the test world (alarm " + decision.alarm + "): " + decision.why);
				break;
		}
	}

	/** The client ends the run at its next tick; a client that doesn't tick (stuck starting the server) can't. */
	private void giveUpLoading(String reason) {
		game.giveUpLoading(reason);
		long until = System.currentTimeMillis() + 10_000L;
		while (!game.done() && System.currentTimeMillis() < until) {
			if (!sleep(500)) {
				return;
			}
		}
		if (!game.done()) {
			TasTrace.write(request.results, "loading-trace.txt");
			String dump = TasHang.dump(Minecraft.getMinecraft(), request.results);
			String problem = reason + "; the client is stuck too (threads and connection in " + dump + ")";
			request.progress(problem);
			TasRunner.reportUnstarted(game, "TasGame.loadTestWorld", problem);
			// the game itself stays stuck: ./unittas.sh stops it once the report is there
			gaveUp = true;
		}
	}

	// ---------------------------------------------------------------- an alarm and its answer

	/**
	 * Raises an alarm and waits for its answer: the watcher's decision, CLEARED when the situation passes by itself
	 * (or the run ends), NO_ANSWER after the run's decision time. One alarm at a time; any thread may ask.
	 *
	 * @param threads   whether to dump the threads with it (for a game that stopped answering)
	 * @param stillSo   whether the situation still holds, asked each second while the alarm is open
	 * @param failMeans what "fail" does here, in words for the watcher
	 * @param fallback  what unitTAS does without an answer, in words for the watcher
	 */
	Decision ask(String what, boolean threads, BooleanSupplier stillSo, String failMeans, String fallback) {
		if (Thread.currentThread() == thread) {
			if (!alarmLock.tryLock()) {
				// the runner's alarm is open: this one waits for the next round
				return new Decision(0, Action.CLEARED, 0, "");
			}
		} else {
			alarmLock.lock();
		}
		try {
			if (game.done() || !stillSo.getAsBoolean()) {
				return new Decision(0, Action.CLEARED, 0, "");
			}
			int number = ++alarms;
			File alarmFile = new File(request.results, "alarm.txt");
			File decisionFile = new File(request.results, "decision.txt");
			delete(decisionFile);
			// a client that doesn't tick can't take pictures: then its threads are the evidence, whatever was asked
			boolean dumpThreads = threads || !game.clientTickedWithin(3);
			String pictures = alarmPictures(number);
			String dump = null;
			if (dumpThreads) {
				try {
					dump = new File(request.results, TasHang.dump(Minecraft.getMinecraft(), request.results)).getAbsolutePath();
				} catch (RuntimeException e) {
					dump = "none (" + e + ")";
				}
			}
			long answerBy = System.currentTimeMillis() + request.watchDecide * 1000L;
			writeWhole(alarmFile, alarmText(number, what, pictures, dump, failMeans, fallback, answerBy));
			openAlarm = number;
			log("alarm " + number + " opened: " + what);
			request.progress("ALARM " + number + ": " + what + "; look, then answer in decision.txt (" + alarmFile.getAbsolutePath() + ")");
			long remind = System.currentTimeMillis() + REMIND_SECONDS * 1000L;
			try {
				while (true) {
					if (Thread.currentThread() == thread) {
						housekeeping();
					}
					Decision decision = readDecision(decisionFile, number, alarmFile);
					if (decision != null) {
						log("alarm " + number + " answered: " + decision);
						request.progress("alarm " + number + " answered: " + decision);
						return decision;
					}
					if (game.done()) {
						log("alarm " + number + " closed: the run ended");
						return new Decision(number, Action.CLEARED, 0, "");
					}
					if (!stillSo.getAsBoolean()) {
						log("alarm " + number + " cleared by itself");
						request.progress("alarm " + number + " cleared by itself");
						return new Decision(number, Action.CLEARED, 0, "");
					}
					long now = System.currentTimeMillis();
					if (now >= answerBy) {
						log("alarm " + number + ": no answer in " + request.watchDecide + " s, so " + fallback);
						request.progress("alarm " + number + ": no answer in " + request.watchDecide + " s, so " + fallback);
						return new Decision(number, Action.NO_ANSWER, 0, "");
					}
					if (now >= remind) {
						remind += REMIND_SECONDS * 1000L;
						request.progress("ALARM " + number + " still open (" + (answerBy - now) / 1000 + " s left before: " + fallback + ")");
					}
					if (!sleep(1000)) {
						return new Decision(number, Action.CLEARED, 0, "");
					}
				}
			} finally {
				openAlarm = 0;
				delete(alarmFile);
			}
		} finally {
			alarmLock.unlock();
		}
	}

	private String alarmPictures(int number) {
		if (!game.clientTickedWithin(3)) {
			return "none: the client isn't ticking, so no picture can be taken (the threads show where it is)";
		}
		String first = picture("alarm-" + number + "-a.png");
		sleep(PICTURE_GAP_MILLIS);
		String second = picture("alarm-" + number + "-b.png");
		return first + "\n  and " + PICTURE_GAP_MILLIS / 1000 + " s later: " + second;
	}

	private String picture(String name) {
		try {
			String taken = game.client(() -> TasHang.picture(Minecraft.getMinecraft(), request.results, name));
			return new File(request.results, taken).getAbsolutePath();
		} catch (RuntimeException e) {
			return "none (" + e.getMessage() + ")";
		}
	}

	private String alarmText(int number, String what, String pictures, String dump, String failMeans, String fallback, long answerBy) {
		long now = System.currentTimeMillis();
		File decision = new File(request.results, "decision.txt");
		return "unitTAS alarm " + number + ", " + clock(now) + "\n"
			+ "what: " + what + "\n"
			+ "run: " + situation() + "\n"
			+ "client: " + ticking(game.clientTickedAt(), now) + "; server: " + (game.serverExpected() ? ticking(game.serverTickedAt(), now) : "none running") + "\n"
			+ "pictures: " + pictures + "\n"
			+ (request.watchPictures > 0
				? "  (the live picture, every " + request.watchPictures + " s: " + new File(request.results, "screenshots/watch-live.png").getAbsolutePath() + ")\n"
				: "  (no live pictures in this run)\n")
			+ (dump == null ? "" : "threads: " + dump + "\n")
			+ "the run so far: " + new File(request.results, "progress.txt").getAbsolutePath() + "\n"
			+ "\n"
			+ "Look at the pictures, decide whether the game is working or stuck, and write one line to\n"
			+ decision.getAbsolutePath() + ":\n"
			+ "  " + number + " wait <seconds>   it is working: give it that long (a new alarm comes if it is still at it then)\n"
			+ "  " + number + " fail <why>       " + failMeans + "\n"
			+ "  " + number + " abort <why>      stop the whole run, with your reason\n"
			+ "No answer by " + clock(answerBy) + " (" + request.watchDecide + " s): " + fallback + ".\n";
	}

	/** The decision for this alarm in decision.txt, or null while there is none (one for another alarm is dropped). */
	private Decision readDecision(File file, int number, File alarmFile) {
		if (!file.isFile()) {
			return null;
		}
		String text;
		try {
			text = new String(Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8).trim();
		} catch (IOException e) {
			return null;
		}
		if (text.isEmpty()) {
			return null;
		}
		String line = text.split("\n", 2)[0].trim();
		Matcher matcher = DECISION.matcher(line);
		if (!matcher.matches()) {
			// a moment for a decision still being written, then it's taken as said
			if (System.currentTimeMillis() - file.lastModified() < 2000) {
				return null;
			}
			delete(file);
			log("alarm " + number + ": decision.txt said '" + line + "', which is none of wait, fail, abort");
			append(alarmFile, "\ndecision.txt said '" + line + "': that's none of the three; write it again.\n");
			return null;
		}
		delete(file);
		if (matcher.group(1) != null && Integer.parseInt(matcher.group(1)) != number) {
			log("a decision for alarm " + matcher.group(1) + " came while alarm " + number + " is open: dropped");
			return null;
		}
		Action action = Action.valueOf(matcher.group(2).toUpperCase(Locale.ROOT));
		String rest = matcher.group(3).trim();
		if (action == Action.WAIT) {
			int seconds = 60;
			try {
				seconds = Integer.parseInt(rest.split("\\s+")[0]);
			} catch (NumberFormatException e) {
				// "wait" alone, or words after it: a minute
			}
			return new Decision(number, action, Math.max(1, Math.min(seconds, 24 * 3600)), "");
		}
		return new Decision(number, action, 0, rest.isEmpty() ? "no reason given" : rest);
	}

	// ---------------------------------------------------------------- files and time

	private void log(String line) {
		append(new File(request.results, "alarms.txt"), clock(System.currentTimeMillis()) + "  " + line + "\n");
	}

	/** The file whole or not at all (a reader never sees half of it). */
	private static void writeWhole(File file, String text) {
		File temporary = new File(file.getPath() + ".tmp");
		try {
			Files.write(temporary.toPath(), text.getBytes(StandardCharsets.UTF_8));
			Files.move(temporary.toPath(), file.toPath(), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
		} catch (IOException e) {
			UnitTas.LOG.warn("Can't write " + file, e);
		}
	}

	private static void append(File file, String text) {
		try {
			Files.write(file.toPath(), text.getBytes(StandardCharsets.UTF_8), StandardOpenOption.CREATE, StandardOpenOption.APPEND);
		} catch (IOException e) {
			UnitTas.LOG.warn("Can't write " + file, e);
		}
	}

	private static void delete(File file) {
		try {
			Files.deleteIfExists(file.toPath());
		} catch (IOException e) {
			UnitTas.LOG.warn("Can't remove " + file, e);
		}
	}

	private static long secondsSince(long millis) {
		return (System.currentTimeMillis() - millis) / 1000;
	}

	private static String clock(long millis) {
		return new SimpleDateFormat("HH:mm:ss", Locale.ROOT).format(new Date(millis));
	}

	/** False when interrupted (the interrupt is kept). */
	private static boolean sleep(long millis) {
		try {
			Thread.sleep(millis);
			return true;
		} catch (InterruptedException e) {
			Thread.currentThread().interrupt();
			return false;
		}
	}
}

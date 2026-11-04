package io.github.asgerjon.unittas;

import cpw.mods.fml.relauncher.FMLRelaunchLog;
import org.apache.logging.log4j.Level;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.core.LogEvent;
import org.apache.logging.log4j.core.Logger;
import org.apache.logging.log4j.core.appender.AbstractAppender;

import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * The errors and warnings logged while something loads (a chunk, a save): FML catches an entity's or
 * tile entity's exception during loading and only logs it, so a test that counts what came back can pass over one.
 * Listens to FML's own logger and to the root logger of Minecraft's and the mods' logging context: log4j keeps one
 * context per class loader, FML's logger lives in the app class loader's, and a logger looked up by FML's name from
 * here is another context's (it hears nothing). {@link #listen} first logs a probe through each, which it must hear.
 */
public final class TasLogErrors extends AbstractAppender {

	private static final String PROBE = "unitTAS probe: listening for errors";

	/** Errors (and worse), as "[logger] message (exception)". */
	public final List<String> errors = Collections.synchronizedList(new ArrayList<>());
	/** Warnings, the same way: not failures by themselves, but worth reading. */
	public final List<String> warnings = Collections.synchronizedList(new ArrayList<>());
	private volatile int probesHeard;

	public TasLogErrors() {
		super("unitTAS log errors", null, null, true);
	}

	@Override
	public void append(LogEvent event) {
		String message = event.getMessage() == null ? "" : event.getMessage().getFormattedMessage();
		if (message.startsWith(PROBE)) {
			probesHeard++;
			return;
		}
		int level = event.getLevel() == null ? Level.INFO.intLevel() : event.getLevel().intLevel();
		if (level > Level.WARN.intLevel()) {
			return;
		}
		Throwable thrown = event.getThrown();
		String line = "[" + event.getLoggerName() + "] " + (message.length() > 200 ? message.substring(0, 200) + "..." : message)
			+ (thrown == null ? "" : " (" + thrown + ")");
		(level <= Level.ERROR.intLevel() ? errors : warnings).add(line);
	}

	/** Starts listening; throws if a probe through either logger isn't heard. */
	public void listen() {
		start();
		fml().addAppender(this);
		root().addAppender(this);
		probesHeard = 0;
		cpw.mods.fml.common.FMLLog.info(PROBE + " (FML)");
		LogManager.getLogger("unitTAS").info(PROBE + " (root)");
		if (probesHeard < 2) {
			quiet();
			throw new AssertionError("the log listener hears " + probesHeard + " of its 2 probes (FML's logger and the root)");
		}
	}

	public void quiet() {
		fml().removeAppender(this);
		root().removeAppender(this);
	}

	private static Logger root() {
		return (Logger) LogManager.getRootLogger();
	}

	private static Logger fml() {
		try {
			Field field = FMLRelaunchLog.class.getDeclaredField("myLog");
			field.setAccessible(true);
			return (Logger) field.get(FMLRelaunchLog.log);
		} catch (ReflectiveOperationException e) {
			throw new AssertionError("no FML logger: " + e);
		}
	}
}

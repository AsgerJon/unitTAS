package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonObject;
import cpw.mods.fml.relauncher.FMLRelaunchLog;
import io.github.asgerjon.unittas.probe.link.Json;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.core.LogEvent;
import org.apache.logging.log4j.core.Logger;
import org.apache.logging.log4j.core.appender.AbstractAppender;

import java.lang.reflect.Field;

/**
 * The game's log as "log" events (PROTOCOL.md 7), from the level events.set asks for (warn by default). It listens to
 * FML's own logger and to the root logger of Minecraft's and the mods' logging context, as TasLogErrors does: log4j
 * keeps one context per class loader, and FML's logger lives in another than the mods'. Attached from the coremod, so
 * a mod that fails while it loads is heard; it checks it hears both by logging a line through each.
 */
final class ProbeLog extends AbstractAppender {

	private static final String CHECK = "unitTAS probe: listening to the log";
	private static final int MESSAGE_CHARS = 2000;

	private final Probe probe;
	private volatile int heard;

	private ProbeLog(Probe probe) {
		super("unitTAS probe log", null, null, true);
		this.probe = probe;
	}

	static void attach(Probe probe) {
		ProbeLog appender = new ProbeLog(probe);
		appender.start();
		Logger fml = fml();
		if (fml != null) {
			fml.addAppender(appender);
		}
		((Logger) LogManager.getRootLogger()).addAppender(appender);
		FMLRelaunchLog.info(CHECK + " (FML)");
		LogManager.getLogger("unitTAS").info(CHECK + " (root)");
		if (appender.heard < 2) {
			Probe.LOG.warn("unitTAS probe: the log is heard through {} of its 2 loggers (FML's and the root): some log events will be missing",
				appender.heard);
		}
	}

	@Override
	public void append(LogEvent event) {
		String message = event.getMessage() == null ? "" : event.getMessage().getFormattedMessage();
		if (message.startsWith(CHECK)) {
			heard++;
			return;
		}
		int level = event.getLevel() == null ? 400 : event.getLevel().intLevel();
		if (level > probe.events.logThreshold()) {
			return;
		}
		Throwable thrown = event.getThrown();
		JsonObject fields = Json.object(
			"level", event.getLevel() == null ? "INFO" : event.getLevel().name(),
			"logger", event.getLoggerName(),
			"thread", Thread.currentThread().getName(),
			"message", message.length() > MESSAGE_CHARS ? message.substring(0, MESSAGE_CHARS) + "..." : message,
			"thrown", thrown == null ? null : thrown.toString());
		probe.event("log", fields);
	}

	/** FML's own log4j logger, or null if it can't be reached. */
	private static Logger fml() {
		try {
			Field field = FMLRelaunchLog.class.getDeclaredField("myLog");
			field.setAccessible(true);
			Object logger = field.get(FMLRelaunchLog.log);
			return logger instanceof Logger ? (Logger) logger : null;
		} catch (ReflectiveOperationException | RuntimeException e) {
			return null;
		}
	}
}

package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.core.LogEvent;
import org.apache.logging.log4j.core.Logger;
import org.apache.logging.log4j.core.appender.AbstractAppender;
import org.apache.logging.log4j.core.config.Property;

/**
 * The game's log in 26.3 (PROTOCOL.md 7; SPEC.md 19.7 step 2), as 1.7.10's ProbeLog: an appender on Log4j's root
 * logger, every line at the threshold events.set asks for or above sent as a log event. 26.3 has one logger context
 * (Fabric's loader logs through the same Log4j), so the root is all of it.
 */
final class ModernLog extends AbstractAppender {

	private static final int MESSAGE_CHARS = 2000;

	private final Probe probe;

	private ModernLog(Probe probe) {
		super("unitTAS probe log", null, null, true, Property.EMPTY_ARRAY);
		this.probe = probe;
	}

	static void attach(Probe probe) {
		ModernLog appender = new ModernLog(probe);
		appender.start();
		((Logger) LogManager.getRootLogger()).addAppender(appender);
	}

	@Override
	public void append(LogEvent event) {
		int level = event.getLevel() == null ? 400 : event.getLevel().intLevel();
		if (level > probe.events.logThreshold()) {
			return;
		}
		String message = event.getMessage() == null ? "" : event.getMessage().getFormattedMessage();
		Throwable thrown = event.getThrown();
		JsonObject fields = Json.object(
			"level", event.getLevel() == null ? "INFO" : event.getLevel().name(),
			"logger", event.getLoggerName(),
			"thread", Thread.currentThread().getName(),
			"message", message.length() > MESSAGE_CHARS ? message.substring(0, MESSAGE_CHARS) + "..." : message,
			"thrown", thrown == null ? null : thrown.toString());
		probe.event("log", fields);
	}
}

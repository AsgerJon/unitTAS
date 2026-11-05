package io.github.asgerjon.unittas.probe;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/** Which events the orchestrator wants (PROTOCOL.md 7, events.set): chat, sounds and screens on, the log from warn. */
final class Events {

	/** The events this probe sends so far (phase 2 adds the others step by step: chat, sound, screen, world, tick ...). */
	static final List<String> KINDS = Collections.unmodifiableList(Arrays.asList("ready", "log", "quit", "dropped", "world", "chat", "sound", "screen"));
	static final List<String> LOG_LEVELS = Collections.unmodifiableList(Arrays.asList("off", "error", "warn", "info", "debug"));

	volatile boolean chat = true;
	volatile boolean sound = true;
	volatile boolean screen = true;
	volatile String log = "warn";

	/** The highest log4j level number that is sent (FATAL 100, ERROR 200, WARN 300, INFO 400, DEBUG 500), -1 for none. */
	int logThreshold() {
		switch (log) {
			case "error":
				return 200;
			case "warn":
				return 300;
			case "info":
				return 400;
			case "debug":
				return 500;
			default:
				return -1;
		}
	}
}

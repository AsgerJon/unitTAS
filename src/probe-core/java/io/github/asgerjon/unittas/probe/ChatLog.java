package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;

import java.util.ArrayList;
import java.util.List;

/**
 * The chat lines the client received (PROTOCOL.md 5.7), each with its formatting codes and without, as a log with
 * marks: command.run takes a mark before its command and reads what came after. The last {@link #KEPT} lines are kept;
 * a mark from before them reads from the oldest kept. No Minecraft class here: ClientHooks fills it.
 */
final class ChatLog {

	static final int KEPT = 10000;

	private final List<JsonObject> lines = new ArrayList<>();
	/** How many lines came before the oldest kept. */
	private long dropped;

	synchronized void add(String plain, String formatted, String json) {
		lines.add(Json.object("plain", plain, "formatted", formatted, "json", json));
		if (lines.size() > KEPT) {
			lines.remove(0);
			dropped++;
		}
	}

	/** Where the chat stands now. */
	synchronized long mark() {
		return dropped + lines.size();
	}

	/** The lines after the mark, oldest first. */
	synchronized List<JsonObject> since(long mark) {
		int from = (int) Math.max(0, mark - dropped);
		return new ArrayList<>(lines.subList(Math.min(from, lines.size()), lines.size()));
	}
}

package io.github.asgerjon.unittas.probe.link;

import com.google.gson.JsonElement;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * The probe's end of the connection (PROTOCOL.md 2 and 3). It dials the orchestrator at 127.0.0.1 (the game never
 * listens), sends the hello, and takes the welcome; then one thread reads the requests and hands them to the handler,
 * and another writes the answers and events, in the order they were made. A game thread never waits on the socket: it
 * hands its line over and goes on. Events beyond {@link #EVENTS_HELD} waiting are dropped, never answers, and a
 * "dropped" event says how many once there is room. Only JDK classes and Gson: it is made at the coremod's time, and
 * its threads start once Minecraft is launched (Probe.launched).
 */
public final class Link {

	/** The longest line either side sends or takes, newline included. */
	public static final int MAX_LINE = 16 * 1024 * 1024;
	/** From the link's start, to dial and to be welcomed. */
	public static final int START_SECONDS = 30;
	private static final int EVENTS_HELD = 10000;

	/** What the link hands on. Called on the link's own threads: hand work on, don't wait there. */
	public interface Handler {
		void request(Link link, JsonElement id, String op, JsonElement side, JsonObject args);

		/** The link is over: never welcomed, refused, or the orchestrator gone. Once. */
		void ended(Link link, String why);

		/** Each side's ticks now, for every answer's and event's "at". */
		JsonObject at();
	}

	private static final class Line {
		final byte[] bytes;
		final boolean event;

		Line(byte[] bytes, boolean event) {
			this.bytes = bytes;
			this.event = event;
		}
	}

	private static final class TooLong extends IOException {
		TooLong() {
			super("a line over 16 MiB");
		}
	}

	private final StartFile start;
	private final JsonObject hello;
	private final Handler handler;
	private volatile long startedAt;
	private final LinkedBlockingQueue<Line> out = new LinkedBlockingQueue<>();
	private final AtomicInteger eventsWaiting = new AtomicInteger();
	private final AtomicInteger dropped = new AtomicInteger();
	private final AtomicBoolean ended = new AtomicBoolean();
	private volatile boolean writing;
	private volatile boolean welcomed;
	private volatile int protocol;
	private volatile Socket socket;

	public Link(StartFile start, JsonObject hello, Handler handler) {
		this.start = start;
		this.hello = hello;
		this.handler = handler;
	}

	public void start() {
		startedAt = System.currentTimeMillis();
		Thread reader = new Thread(this::run, "unitTAS link");
		reader.setDaemon(true);
		reader.start();
	}

	public boolean welcomed() {
		return welcomed;
	}

	/** The protocol the welcome named; 0 before it. */
	public int protocol() {
		return protocol;
	}

	public boolean ended() {
		return ended.get();
	}

	// ---------------------------------------------------------------- sending

	public void answer(JsonElement id, JsonElement value) {
		answer(id, value, null);
	}

	/** An answer, with its warnings when there are any (PROTOCOL.md 3.2). */
	public void answer(JsonElement id, JsonElement value, java.util.List<String> warnings) {
		JsonObject message = new JsonObject();
		message.add("id", id == null ? JsonNull.INSTANCE : id);
		message.addProperty("ok", true);
		message.add("value", value == null ? JsonNull.INSTANCE : value);
		message.add("at", handler.at());
		if (warnings != null && !warnings.isEmpty()) {
			message.add("warnings", Json.of(new java.util.ArrayList<>(warnings)));
		}
		send(message, false);
	}

	public void error(JsonElement id, String type, String text, JsonObject fields) {
		JsonObject error = new JsonObject();
		error.addProperty("type", type);
		error.addProperty("message", text);
		if (fields != null) {
			for (java.util.Map.Entry<String, JsonElement> field : fields.entrySet()) {
				error.add(field.getKey(), field.getValue());
			}
		}
		JsonObject message = new JsonObject();
		message.add("id", id == null ? JsonNull.INSTANCE : id);
		message.addProperty("ok", false);
		message.add("error", error);
		message.add("at", handler.at());
		send(message, false);
	}

	/** An event, kept until the welcome if it comes before; dropped when too many are waiting already. */
	public void event(String kind, JsonObject fields) {
		if (ended.get()) {
			return;
		}
		if (eventsWaiting.get() >= EVENTS_HELD) {
			dropped.incrementAndGet();
			return;
		}
		JsonObject message = new JsonObject();
		message.addProperty("event", kind);
		message.add("at", handler.at());
		if (fields != null) {
			for (java.util.Map.Entry<String, JsonElement> field : fields.entrySet()) {
				message.add(field.getKey(), field.getValue());
			}
		}
		send(message, true);
	}

	private void send(JsonObject message, boolean event) {
		if (ended.get()) {
			return;
		}
		byte[] line = Json.line(message);
		if (line.length > MAX_LINE) {
			// never sent whole: an answer says why instead, an event is dropped
			if (event) {
				dropped.incrementAndGet();
				return;
			}
			JsonObject error = Json.object("type", "ProbeError", "message", "the answer was " + line.length
				+ " bytes, over the protocol's 16 MiB a line");
			line = Json.line(Json.object("id", message.get("id"), "ok", false, "error", error, "at", handler.at()));
		}
		if (event) {
			eventsWaiting.incrementAndGet();
		}
		out.add(new Line(line, event));
	}

	/** Waits until everything handed over so far is written, or the time is up. */
	public void flush(long millis) {
		long until = System.currentTimeMillis() + millis;
		while ((!out.isEmpty() || writing) && System.currentTimeMillis() < until && !ended.get()) {
			try {
				Thread.sleep(10);
			} catch (InterruptedException e) {
				Thread.currentThread().interrupt();
				return;
			}
		}
	}

	// ---------------------------------------------------------------- the connection

	private void run() {
		Socket dialled = dial();
		if (dialled == null) {
			end("no orchestrator listening at " + StartFile.LOOPBACK + ":" + start.port + " within " + START_SECONDS + " s");
			return;
		}
		socket = dialled;
		InputStream in;
		try {
			dialled.setTcpNoDelay(true);
			in = new BufferedInputStream(dialled.getInputStream());
			OutputStream raw = dialled.getOutputStream();
			raw.write(Json.line(Json.object("hello", hello)));
			raw.flush();
			long left = startedAt + START_SECONDS * 1000L - System.currentTimeMillis();
			dialled.setSoTimeout((int) Math.max(1000, left));
			byte[] first = readLine(in);
			if (first == null) {
				end("the orchestrator hung up before it welcomed the probe");
				return;
			}
			JsonObject reply = Json.parse(new String(first, StandardCharsets.UTF_8));
			if (reply.has("refused")) {
				JsonObject refused = reply.get("refused").isJsonObject() ? reply.getAsJsonObject("refused") : null;
				String reason = Json.string(refused, "reason");
				end("the orchestrator refused the probe: " + (reason == null ? "no reason given" : reason));
				return;
			}
			if (!reply.has("welcome") || !reply.get("welcome").isJsonObject()) {
				end("the orchestrator's first line is neither a welcome nor a refusal");
				return;
			}
			JsonElement version = reply.getAsJsonObject("welcome").get("protocol");
			protocol = version != null && version.isJsonPrimitive() ? version.getAsInt() : 0;
			dialled.setSoTimeout(0);
		} catch (SocketTimeoutException e) {
			end("no welcome within " + START_SECONDS + " s of dialling");
			return;
		} catch (IOException | RuntimeException e) {
			end("the connection failed before the welcome: " + e);
			return;
		}
		welcomed = true;
		Thread writer = new Thread(this::write, "unitTAS link writer");
		writer.setDaemon(true);
		writer.start();
		read(in);
	}

	/** Dials until it connects, or the start's time is up; null then. */
	private Socket dial() {
		while (System.currentTimeMillis() < startedAt + START_SECONDS * 1000L) {
			Socket attempt = new Socket();
			try {
				attempt.connect(new InetSocketAddress(StartFile.LOOPBACK, start.port), 2000);
				return attempt;
			} catch (IOException e) {
				try {
					attempt.close();
				} catch (IOException ignored) {
					// it never opened
				}
				try {
					Thread.sleep(1000);
				} catch (InterruptedException interrupted) {
					Thread.currentThread().interrupt();
					return null;
				}
			}
		}
		return null;
	}

	private void read(InputStream in) {
		while (!ended.get()) {
			byte[] bytes;
			try {
				bytes = readLine(in);
			} catch (TooLong e) {
				error(null, "BadRequest", "a request over the protocol's 16 MiB a line", Json.object("field", "line"));
				continue;
			} catch (IOException e) {
				end("orchestrator gone: " + e);
				return;
			}
			if (bytes == null) {
				end("orchestrator gone");
				return;
			}
			JsonObject request;
			try {
				request = Json.parse(new String(bytes, StandardCharsets.UTF_8));
			} catch (IllegalArgumentException e) {
				error(null, "BadRequest", "a line that isn't a JSON object: " + e.getMessage(), null);
				continue;
			}
			JsonElement id = request.get("id");
			if (id == null || !id.isJsonPrimitive() || !id.getAsJsonPrimitive().isNumber()) {
				error(id, "BadRequest", "a request needs an id, a positive whole number", Json.object("field", "id"));
				continue;
			}
			String op = Json.string(request, "op");
			if (op == null) {
				error(id, "BadRequest", "a request needs an op, a string", Json.object("field", "op"));
				continue;
			}
			JsonElement args = request.get("args");
			if (args != null && !args.isJsonNull() && !args.isJsonObject()) {
				error(id, "BadRequest", op + "'s args must be an object", Json.object("field", "args"));
				continue;
			}
			JsonElement side = request.get("side");
			try {
				handler.request(this, id, op, side == null || side.isJsonNull() ? null : side,
					args == null || args.isJsonNull() ? new JsonObject() : args.getAsJsonObject());
			} catch (RuntimeException e) {
				error(id, "ProbeError", "the probe failed to take " + op + ": " + e, null);
			}
		}
	}

	private void write() {
		try {
			OutputStream stream = socket.getOutputStream();
			while (!ended.get()) {
				Line line = out.poll(200, TimeUnit.MILLISECONDS);
				if (line == null) {
					continue;
				}
				writing = true;
				try {
					stream.write(line.bytes);
					if (out.isEmpty()) {
						stream.flush();
					}
				} finally {
					writing = false;
				}
				if (line.event) {
					eventsWaiting.decrementAndGet();
				}
				int lost = dropped.get();
				if (lost > 0 && eventsWaiting.get() < EVENTS_HELD / 2 && dropped.compareAndSet(lost, 0)) {
					event("dropped", Json.object("count", lost));
				}
			}
		} catch (IOException e) {
			end("orchestrator gone: " + e);
		} catch (InterruptedException e) {
			Thread.currentThread().interrupt();
		}
	}

	/** One line without its newline; null at the end of the stream; TooLong for a line over the limit (skipped). */
	private static byte[] readLine(InputStream in) throws IOException {
		ByteArrayOutputStream line = new ByteArrayOutputStream();
		boolean tooLong = false;
		int b;
		while ((b = in.read()) != -1) {
			if (b == '\n') {
				if (tooLong) {
					throw new TooLong();
				}
				return line.toByteArray();
			}
			if (!tooLong) {
				if (line.size() >= MAX_LINE - 1) {
					tooLong = true;
					line = new ByteArrayOutputStream();
				} else {
					line.write(b);
				}
			}
		}
		return null;
	}

	private void end(String why) {
		if (!ended.compareAndSet(false, true)) {
			return;
		}
		Socket open = socket;
		if (open != null) {
			try {
				open.close();
			} catch (IOException ignored) {
				// closed either way
			}
		}
		handler.ended(this, why);
	}
}

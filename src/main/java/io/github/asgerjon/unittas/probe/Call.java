package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;

/**
 * One request as an operation sees it: its arguments, the side it runs on (null on the probe's own thread), and its
 * place among the requests running, for cancel. The argument getters say what's wrong with an argument as a
 * BadRequest that names it.
 */
final class Call {

	final Probe probe;
	final JsonObject args;
	final Side side;
	final Running running;
	/** Inside a batch (or wait.until's check): instant only, no settle phase after. */
	final boolean inBatch;
	/** The answer's warnings (PROTOCOL.md 3.2): a ref used on the other side, say. Shared with the inner calls. */
	final java.util.List<String> warnings;
	/** What the step leaves for the settle phase (the chat's mark before a command, a teleport's dimension). */
	volatile long mark;
	volatile String note;

	Call(Probe probe, JsonObject args, Side side, Running running) {
		this(probe, args, side, running, false, java.util.Collections.synchronizedList(new java.util.ArrayList<>()));
	}

	private Call(Probe probe, JsonObject args, Side side, Running running, boolean inBatch, java.util.List<String> warnings) {
		this.probe = probe;
		this.args = args == null ? new JsonObject() : args;
		this.side = side;
		this.running = running;
		this.inBatch = inBatch;
		this.warnings = warnings;
	}

	/** The same request's place, for another operation's arguments (a batch's or wait.until's inner one). */
	Call with(JsonObject innerArgs, Side innerSide) {
		return new Call(probe, innerArgs, innerSide, running, true, warnings);
	}

	void warn(String warning) {
		if (!warnings.contains(warning)) {
			warnings.add(warning);
		}
	}

	boolean has(String key) {
		JsonElement value = args.get(key);
		return value != null && !value.isJsonNull();
	}

	long number(String key, long otherwise, long least, long most) throws ProbeException {
		if (!has(key)) {
			return otherwise;
		}
		JsonElement value = args.get(key);
		if (!value.isJsonPrimitive() || !value.getAsJsonPrimitive().isNumber()) {
			throw ProbeException.badRequest(key, key + " is a whole number, not " + value);
		}
		double number = value.getAsDouble();
		if (number != Math.floor(number) || number < least || number > most) {
			throw ProbeException.badRequest(key, key + " is a whole number from " + least + " to " + most + ", not " + value);
		}
		return (long) number;
	}

	boolean flag(String key, boolean otherwise) throws ProbeException {
		if (!has(key)) {
			return otherwise;
		}
		JsonElement value = args.get(key);
		if (!value.isJsonPrimitive() || !value.getAsJsonPrimitive().isBoolean()) {
			throw ProbeException.badRequest(key, key + " is true or false, not " + value);
		}
		return value.getAsBoolean();
	}

	String string(String key, String otherwise) throws ProbeException {
		if (!has(key)) {
			return otherwise;
		}
		String value = Json.string(args, key);
		if (value == null) {
			throw ProbeException.badRequest(key, key + " is a string, not " + args.get(key));
		}
		return value;
	}

	JsonObject object(String key) throws ProbeException {
		if (!has(key)) {
			return null;
		}
		JsonElement value = args.get(key);
		if (!value.isJsonObject()) {
			throw ProbeException.badRequest(key, key + " is an object, not " + value);
		}
		return value.getAsJsonObject();
	}

	/** The side an argument names ("side": "client"), the default when it is left out. */
	Side sideArg(String key, Side otherwise) throws ProbeException {
		String name = string(key, otherwise.wire);
		Side named = Side.of(name);
		if (named == null) {
			throw ProbeException.badRequest(key, key + " is client or server, not " + name);
		}
		return named;
	}
}

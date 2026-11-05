package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;

/**
 * One operation of the protocol (PROTOCOL.md 8), declared when the probe starts (so the hello can list it) and given
 * its body then, or at preInit for one that needs Minecraft's classes. Where it runs: on the probe's own thread
 * ({@link #sides} null), or on a side's thread at that side's next tick (the sides it allows, the first one its
 * default, unless {@link #choose} picks one from the arguments). Instant: done within one tick of its side, so it can
 * go in a batch; reads: changes nothing, so wait.until can check it. An operation that waits after its step (for
 * chat lines, for the client to arrive) does that in {@link #settle}, on the probe's thread; in a batch it doesn't.
 */
final class Op {

	/** What an operation does, given its call. */
	interface Body {
		JsonElement run(Call call) throws ProbeException, InterruptedException;
	}

	/** After the side's step, on the probe's thread: what the operation waits for, and its value then. */
	interface Settle {
		JsonElement run(Call call, JsonElement value) throws ProbeException, InterruptedException;
	}

	/** The side the arguments call for, when the request names none. */
	interface Chooser {
		Side choose(JsonObject args);
	}

	/** After the answer is handed over (quit: the answer goes first, then the game). */
	interface After {
		void run(Probe probe);
	}

	final String name;
	/** Null: the probe's own thread. Otherwise the sides it may run on, the first the default unless sideRequired. */
	final Side[] sides;
	private volatile boolean sideRequired;
	private volatile boolean reads;
	private volatile boolean beforeReady;
	private volatile boolean duringJava;
	private volatile Body body;
	private volatile Settle settle;
	private volatile Chooser chooser;
	private volatile After after;

	private Op(String name, Side[] sides) {
		this.name = name;
		this.sides = sides;
	}

	/** An operation of the probe's own thread (status, ticks.wait, the world operations ...). */
	static Op probe(String name) {
		return new Op(name, null);
	}

	/** An operation on a side's thread; the first side is its default. */
	static Op onSide(String name, Side... sides) {
		return new Op(name, sides);
	}

	Op reading() {
		reads = true;
		return this;
	}

	Op whileLoading() {
		beforeReady = true;
		return this;
	}

	/** It answers while a java.run goes: it doesn't touch the game (PROTOCOL.md 8.14). */
	Op alongsideJava() {
		duringJava = true;
		return this;
	}

	Op needingASide() {
		sideRequired = true;
		return this;
	}

	Op does(Body what) {
		body = what;
		return this;
	}

	Op settles(Settle how) {
		settle = how;
		return this;
	}

	Op choosing(Chooser how) {
		chooser = how;
		return this;
	}

	Op then(After what) {
		after = what;
		return this;
	}

	boolean reads() {
		return reads;
	}

	boolean beforeReady() {
		return beforeReady;
	}

	boolean duringJava() {
		return duringJava;
	}

	boolean sideRequired() {
		return sideRequired;
	}

	/** On a side, done within one of its ticks (whatever it waits for after, in settle, a batch goes without). */
	boolean instant() {
		return sides != null;
	}

	boolean allows(Side side) {
		if (sides == null) {
			return false;
		}
		for (Side each : sides) {
			if (each == side) {
				return true;
			}
		}
		return false;
	}

	/** The side for a request that names none. */
	Side defaultSide(JsonObject args) {
		Chooser how = chooser;
		Side chosen = how == null ? null : how.choose(args);
		return chosen != null ? chosen : sides[0];
	}

	JsonElement run(Call call) throws ProbeException, InterruptedException {
		Body now = body;
		if (now == null) {
			throw new ProbeException("ProbeError", name + " has no body yet (it is given one at preInit)", null);
		}
		return now.run(call);
	}

	/** The settle phase, if there is one and the call isn't in a batch. */
	JsonElement settle(Call call, JsonElement value) throws ProbeException, InterruptedException {
		Settle how = settle;
		return how == null || call.inBatch ? value : how.run(call, value);
	}

	void after(Probe probe) {
		After now = after;
		if (now != null) {
			now.run(probe);
		}
	}
}

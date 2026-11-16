package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;

import java.io.File;
import java.util.List;
import java.util.Map;

/**
 * The game's own calls behind the world operations (PROTOCOL.md 8.3), which one version gives the core's WorldOps
 * through its port (SPEC.md 12, D5). The core checks the arguments, watches a world open or close, and says how far
 * it is; these do what the game's screens and commands do, each on the thread it says. Names are the protocol's:
 * the world types default, flat, large_biomes and amplified; the game modes survival, creative and adventure; the
 * difficulties peaceful, easy, normal and hard; a dimension as the protocol names it.
 */
public interface GameWorlds {

	// ---------------------------------------------------------------- the client thread

	/**
	 * The superflat test world's generator options, in this version's own form: bedrock, two dirt, grass, from the
	 * bottom of the world up, no structures. A flat world asked for without its own options gets these.
	 */
	String testLayers();

	/**
	 * Refuses (BadRequest, field generator) generator options this game wouldn't read as asked, before anything is
	 * made; on the probe's thread. A version that reads anything refuses nothing.
	 */
	void checkGenerator(String type, String generator) throws ProbeException;

	/**
	 * A flat world's generator options in this version's own form, from its layers (bottom up, blocks by this
	 * version's own ids) and its biome by this version's own id (SPEC.md 17.4); on the probe's thread. A block this
	 * game hasn't is NotFound; a biome it can't read, BadRequest. A version that doesn't write them yet refuses.
	 */
	default String flatLayers(java.util.List<FlatLayer> layers, String biome) throws ProbeException {
		throw new ProbeException("Unsupported", "this version's probe takes a flat world's layers as generator text only",
			io.github.asgerjon.unittas.probe.link.Json.object("what", "layers"));
	}

	/**
	 * Makes and opens a world, as the Create New World screen does. It returns once the game has started making it;
	 * the player joins at the ticks after. 'generator' is the type's own options ("" for the type's default). A
	 * ProbeException it throws is the operation's answer, as it is.
	 */
	void create(String folder, String name, long seed, String type, String generator, String gameMode, boolean cheats,
		boolean structures) throws Exception;

	/** Opens a save, as the world list's Play does. */
	void open(String folder) throws Exception;

	/** Saves and leaves the open world for the title screen, as the pause menu's Save and Quit does. */
	void close() throws Exception;

	/** What the window shows now, as a PNG, to exactly that file. */
	void picture(File file) throws Exception;

	/** The game's own trace of a world loading (debug.trace, the port's trace()) starts, as a world is made or opened. */
	void traceStart();

	/** The trace stops: the player is in. */
	void traceStop();

	/** The client's own difficulty option, as the game's difficulty button sets it beside the world's. */
	void clientDifficulty(String difficulty);

	// ---------------------------------------------------------------- the server thread

	/** world.get's value: the overworld's settings and state (PROTOCOL.md 8.3). */
	JsonObject describe();

	/** The rules the game lacks, of those named; none means all can be set. */
	List<String> unknownRules(Iterable<String> names);

	/**
	 * Sets the game rules, each to its value's text ("false", "3"), in every dimension that keeps its own; a value the
	 * rule can't take is BadRequest (field rules), and then none is set.
	 */
	void setRules(Map<String, String> values) throws ProbeException;

	/** Whether this names one of the game's dimensions: the protocol's name, or a version's own form of it. */
	boolean knowsDimension(JsonElement dimension);

	/** The day's time in the dimension named, or in every one (the dimension JsonNull). */
	void setTime(long time, JsonElement dimension);

	/**
	 * The weather in every dimension. Held: it doesn't turn by itself mid-run, and the sky is as asked from the next
	 * frame.
	 */
	void setWeather(boolean raining, boolean thundering, boolean hold);

	/** The world's difficulty, and the spawns it allows. */
	void setDifficulty(String difficulty);

	/**
	 * The steady world a test world is given (both runners, world.prepare): no daylight cycle, mob spawning, fire tick
	 * or mob griefing, by this version's rules' names; the time noon (6000); clear weather.
	 */
	void prepare();
}

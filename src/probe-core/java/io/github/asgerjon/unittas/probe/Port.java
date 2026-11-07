package io.github.asgerjon.unittas.probe;

import java.util.List;

/**
 * What one Minecraft version and loader give the probe's version-free core (SPEC.md 12, D5): the facts its hello
 * says, the moments around its waking, the game's own trace, and the game's operations. The core (this folder) is
 * compiled into every probe; a port (the 1.7.10 Forge one in the root's src/main, the 26.3 Fabric one in fabric/)
 * implements this, and nothing else in the core names a version.
 */
public interface Port {

	/** The port's name as the hello says it: "1.7.10-forge", "26.3-fabric". */
	String name();

	/** The game's Minecraft version: "1.7.10", "26.3". */
	String minecraft();

	/** The loader's name: "forge", "fabric". */
	String loaderName();

	/** The loader's version as the game runs it. */
	String loaderVersion();

	/** How the running game names Minecraft's members, for reflection (PROTOCOL.md 2): "srg", "mcp", "mojang". */
	String names();

	/** Whether this is a development run (a mod's own runClient), not a real client. */
	boolean development();

	/** The probe's own version: the mod's. */
	String probeVersion();

	/** Just before the probe wakes, the start file read: the window's behaviours on (PROTOCOL.md 2.5). */
	void beforeWake();

	/** Just after the probe is made: the log listened to, and the like. */
	void woken(Probe probe);

	/** debug.trace's lines: the game's own trace of a world loading, empty where the port keeps none. */
	List<String> trace();

	/**
	 * The game's operations, declared as the probe starts so the hello lists them all (their bodies come at the
	 * port's preInit or its like). The probe's own (status, quit, ticks.wait and the rest) the core declares itself.
	 */
	void declare(Probe probe);
}

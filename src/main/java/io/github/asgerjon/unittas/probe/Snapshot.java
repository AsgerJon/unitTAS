package io.github.asgerjon.unittas.probe;

/**
 * What the game was like at its last client tick, for the probe's own thread to read (status, at): written only by
 * ClientHooks on the client thread, read anywhere. No Minecraft class here, so status answers while the game loads.
 * The tick counts are {@link Sides}'.
 */
final class Snapshot {

	/** loading, menu, world, changing, quitting (PROTOCOL.md 8.1). */
	volatile String state = "loading";
	/** The first client tick has come and ready was sent. */
	volatile boolean ready;
	volatile String screen;
	volatile boolean paused;
	/** An integrated server is up and has ticked: the server side has a thread (the ticks themselves are Sides'). */
	volatile boolean serverRunning;
	/** No integrated server, or the last one has stopped (its saves are on disk then). */
	volatile boolean serverStopped = true;
	/** The player is in a world on both sides, past the terrain screen. */
	volatile boolean inWorld;
	/** The title screen shows. */
	volatile boolean menu;
	/** A world operation is making, opening or closing a world (status says "changing"). */
	volatile boolean changing;
	/** The open world's folder, and the player's dimension, or null. */
	volatile String worldFolder;
	volatile String dimension;
	volatile String windowTitle;
	volatile int width;
	volatile int height;
	volatile boolean pointerGrabbed;
	/** The server this client has joined ("127.0.0.1:port"), or null (SPEC.md 11.3, step 3). */
	volatile String joined;
	/** In a server's world: its player and world there, past the terrain screen, no world of its own. */
	volatile boolean remote;
	/** What the disconnected screen said, when it last showed (a refused join, a kick), or null. */
	volatile String disconnected;
	/** The client's own player's name, from its session (the name it was launched as): there before any world is. */
	volatile String player;
}

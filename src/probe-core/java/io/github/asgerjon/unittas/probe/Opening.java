package io.github.asgerjon.unittas.probe;

import java.util.concurrent.atomic.AtomicInteger;

/**
 * The opening guard (SPEC.md, after step 9; Asger, 2026-11-05: "EVERY TIME the game instance open, I want some
 * screenshots or something to be used to confirm that the game is not just hanging"). The one way a world's opening
 * never ends, told by what the game shows: the client stands at the title screen while its own integrated server runs
 * with nobody in it. 1.7.10's integrated server can drop its own local connection before Netty has set its channel
 * (NetworkSystem.networkTick drops a connection whose channel isn't open; 1.8 skips one with no channel yet), and the
 * client then waits at the login for ever, every number still saying fine. A login takes a few ticks, so
 * {@link #DROPPED_TICKS} of each side with nobody coming is no slowness: decided by ticks, never by the clock
 * (SPEC.md 9.8). Both runners ask it: the probe's world.create and world.open, and TasGame's test world.
 */
public final class Opening {

	/** Ticks of each side the title screen may stand, its server running and nobody in it, before the opening is dropped. */
	public static final int DROPPED_TICKS = 100;
	/** How often a dropped opening is opened again before it is given up. */
	public static final int RETRIES = 1;
	/** What a dropped opening is said as. */
	public static final String DROPPED = "the integrated server dropped the client's own connection before it joined"
		+ " (1.7.10's login race): the client stood at the title screen, its server running and nobody in it, for "
		+ DROPPED_TICKS + " ticks of each side";
	/** debug.drop_login: how many of the server's next local connections to drop as the race does (for the tests). */
	public static final AtomicInteger DROP_LOGINS = new AtomicInteger();

	private long clientFrom = -1;
	private long serverFrom = -1;

	/** A look at the opening, each client tick or so: whether it is dropped by now. */
	public boolean dropped(boolean titleScreen, boolean serverRunning, boolean playerIn, long clientTicks, long serverTicks) {
		if (!titleScreen || !serverRunning || playerIn) {
			clientFrom = -1;
			return false;
		}
		if (clientFrom < 0) {
			clientFrom = clientTicks;
			serverFrom = serverTicks;
		}
		return clientTicks - clientFrom >= DROPPED_TICKS && serverTicks - serverFrom >= DROPPED_TICKS;
	}

	/** For the opening that follows: what was seen of the last goes. */
	public void reset() {
		clientFrom = -1;
		serverFrom = -1;
	}

	/** One of the server's local connections is dropped now, as the race does, if debug.drop_login asked for it. */
	public static boolean dropNextLogin() {
		while (true) {
			int left = DROP_LOGINS.get();
			if (left <= 0) {
				return false;
			}
			if (DROP_LOGINS.compareAndSet(left, left - 1)) {
				return true;
			}
		}
	}
}

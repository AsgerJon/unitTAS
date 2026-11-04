package io.github.asgerjon.unittas.self;

import cpw.mods.fml.common.FMLCommonHandler;
import cpw.mods.fml.common.eventhandler.SubscribeEvent;
import cpw.mods.fml.common.gameevent.TickEvent;
import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;

/**
 * Waiting for ticks on a game that is slow but still ticking: the wait gives up only when no tick has come for a while,
 * not at a time worked out from 20 ticks a second (a heavy test, a dragon fight or terrain generation, runs at 10).
 */
@TasSuite("self")
public class SlowGameTests extends TasTestCase {

	private static final int TICK_MILLIS = 1000;
	private static final int TICKS = 25;

	/** Holds up every server tick (on the server thread, which ticks it): the server runs at 1 tick a second. */
	public static final class SlowServer {
		@SubscribeEvent
		public void onTick(TickEvent.ServerTickEvent event) {
			if (event.phase == TickEvent.Phase.END) {
				try {
					Thread.sleep(TICK_MILLIS);
				} catch (InterruptedException e) {
					Thread.currentThread().interrupt();
				}
			}
		}
	}

	@Override
	protected int timeoutSeconds() {
		return 90;
	}

	public void testServerTicksOnASlowServer() {
		SlowServer slow = new SlowServer();
		// registered and taken off on the server thread, the only one that posts the server's tick event
		onServer(() -> FMLCommonHandler.instance().bus().register(slow));
		try {
			long start = System.currentTimeMillis();
			serverTicks(TICKS);
			long took = System.currentTimeMillis() - start;
			// the old limit, TICKS × 50 ms + 15 s, is 16.25 s: the wait must have outlasted it
			assertGreater(took, TICKS * 50 + 15000 + 2000, "the server wasn't slow enough to show it");
		} finally {
			onServer(() -> FMLCommonHandler.instance().bus().unregister(slow));
		}
	}
}

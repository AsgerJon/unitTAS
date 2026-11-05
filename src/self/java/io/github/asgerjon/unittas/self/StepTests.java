package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;
import io.github.asgerjon.unittas.probe.Side;
import io.github.asgerjon.unittas.probe.Sides;

/**
 * A step takes a tick: a step queued while a side runs its tick's steps waits for that side's next tick. A test
 * thread woken by one step can queue its next before the tick's queue is done; that one ran in the same tick, so a
 * test sampling once a step sometimes saw one tick twice (EFR's observer trace, 2026-11-05). Here the next step is
 * queued for certain while the first still runs: the first holds its side's thread until it is.
 */
@TasSuite("self")
public class StepTests extends TasTestCase {

	/** How long the first step holds its side's thread: the other thread's step is queued well within it. */
	private static final long HOLD_MILLIS = 200;

	public void testAServerStepQueuedDuringATickRunsInTheNext() throws Exception {
		long[] at = nextStepTicks(Side.SERVER);
		assertEqual(at[0] + 1, at[1], "the server step queued during a tick ran in that tick");
	}

	public void testAClientStepQueuedDuringATickRunsInTheNext() throws Exception {
		long[] at = nextStepTicks(Side.CLIENT);
		assertEqual(at[0] + 1, at[1], "the client step queued during a tick ran in that tick");
	}

	/** The side's tick count in a step, and in the step another thread queued while that one ran. */
	private long[] nextStepTicks(Side side) throws Exception {
		long[] at = {-1, -1};
		Thread[] queuing = new Thread[1];
		step(side, () -> {
			at[0] = Sides.get().ticks(side);
			queuing[0] = new Thread(() -> step(side, () -> {
				at[1] = Sides.get().ticks(side);
				return null;
			}), "unitTAS self: the next step");
			queuing[0].start();
			Thread.sleep(HOLD_MILLIS);
			return null;
		});
		queuing[0].join(10000);
		assertFalse(queuing[0].isAlive(), "the next step never ran");
		return at;
	}

	private <T> T step(Side side, java.util.concurrent.Callable<T> step) {
		return side == Side.SERVER ? onServer(step) : onClient(step);
	}
}

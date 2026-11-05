package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;

/**
 * A game that stops ticking gives no test result (SPEC.md 9.8): its own suite, run on purpose only
 * (./unittas.sh self-stuck). The first test holds the client 20 s, past the stall rule's 15: its line is NO RESULT,
 * and the report says first that no test result could be obtained. Once the client ticks again the run goes on, so
 * the second test has a result of its own.
 */
@TasSuite("self-stuck")
public class StuckTests extends TasTestCase {

	public void testA_theClientStopsTicking() {
		onClient(() -> {
			try {
				Thread.sleep(20000);
			} catch (InterruptedException e) {
				Thread.currentThread().interrupt();
			}
		});
		// a step after it: it waits for a client that doesn't tick
		ticks(1);
	}

	public void testB_theRunGoesOnOnceItTicksAgain() {
		ticks(2);
	}
}

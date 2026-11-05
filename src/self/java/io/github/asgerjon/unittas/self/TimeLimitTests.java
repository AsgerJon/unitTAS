package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;

/**
 * A test stopped by its own time limit has no verdict (SPEC.md 9.8): the limit is wall-clock time, so a slow machine
 * could reach it in a test that would pass. In the self-stuck suite, run on purpose only. Its line is NO RESULT, and
 * the run goes on: the game still ticks.
 */
@TasSuite("self-stuck")
public class TimeLimitTests extends TasTestCase {

	@Override
	protected int timeoutSeconds() {
		return 3;
	}

	public void testA_runsPastItsTime() {
		// 200 ticks are 10 s at 20 a second: past the 3 s limit
		ticks(200);
	}

	public void testB_theNextRunsAsEver() {
		ticks(2);
	}
}

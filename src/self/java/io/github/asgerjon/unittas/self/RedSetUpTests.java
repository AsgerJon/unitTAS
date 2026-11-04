package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.ExpectedFailure;
import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;

/**
 * The self-red suite (see {@link RedTests}): @ExpectedFailure covers the test method only, so a setUp that throws is
 * still an error, as in unittest.
 */
@TasSuite("self-red")
public class RedSetUpTests extends TasTestCase {

	@Override
	protected void setUp() {
		throw new IllegalStateException("setUp fails on purpose");
	}

	@ExpectedFailure("never reached: setUp fails first")
	public void testNeverRuns() {
		fail("setUp should have stopped this test");
	}
}

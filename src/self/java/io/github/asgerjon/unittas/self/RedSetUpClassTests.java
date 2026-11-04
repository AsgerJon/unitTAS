package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;

/** The self-red suite (see {@link RedTests}): a setUpClass that fails is one error, and the class's tests don't run. */
@TasSuite("self-red")
public class RedSetUpClassTests extends TasTestCase {

	@Override
	protected void setUpClass() {
		throw new IllegalStateException("setUpClass fails on purpose");
	}

	public void testNeverRuns() {
		fail("setUpClass failed: this test should not have run");
	}
}

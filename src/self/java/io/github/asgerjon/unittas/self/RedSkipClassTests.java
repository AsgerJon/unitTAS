package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;

/** The self-red suite (see {@link RedTests}): skipTest in setUpClass skips every test of the class, with its reason. */
@TasSuite("self-red")
public class RedSkipClassTests extends TasTestCase {

	@Override
	protected void setUpClass() {
		skipTest("the whole class is skipped");
	}

	public void testA_skipped() {
		fail("setUpClass skipped the class: this test should not have run");
	}

	public void testB_skippedToo() {
		fail("setUpClass skipped the class: this test should not have run");
	}
}

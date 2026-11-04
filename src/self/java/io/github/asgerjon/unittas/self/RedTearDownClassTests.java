package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;

/**
 * The self-red suite (see {@link RedTests}): tearDownClass runs once, after the class's last test, and a failure there
 * is an error line of its own. It fails with its own message only if the tests ran first.
 */
@TasSuite("self-red")
public class RedTearDownClassTests extends TasTestCase {

	private static int testsRun;

	@Override
	protected void tearDownClass() {
		assertEqual(2, testsRun, "tearDownClass came before the class's tests were done");
		throw new IllegalStateException("tearDownClass fails on purpose, after both tests");
	}

	public void testA_runs() {
		testsRun++;
	}

	public void testB_runsToo() {
		testsRun++;
	}
}

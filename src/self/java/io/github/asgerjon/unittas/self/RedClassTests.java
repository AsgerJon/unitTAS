package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.ExpectedFailure;
import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;

/** The self-red suite (see {@link RedTests}): @ExpectedFailure on a class marks each of its tests. */
@TasSuite("self-red")
@ExpectedFailure("the whole class is marked")
public class RedClassTests extends TasTestCase {

	public void testFailsUnderAClassMark() {
		fail("on purpose");
	}
}

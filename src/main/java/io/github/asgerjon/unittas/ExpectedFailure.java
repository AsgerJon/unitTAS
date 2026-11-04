package io.github.asgerjon.unittas;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * A test known to fail for now, as Python's unittest.expectedFailure: a failed assert or an exception from the test
 * method itself is reported as "expected failure", and the run can still end OK. A test that passes is reported as
 * "unexpected success", which fails the run: the mark has done its work and should go.
 *
 * On a class: every test in it. What happens in setUp or tearDown, and unitTAS's own stops (a test out of time, a game
 * that stopped answering, the watcher's fail), stay what they are.
 */
@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
public @interface ExpectedFailure {

	/** Why it fails for now, shown in the report ("the torch light isn't ported yet"). */
	String value();
}

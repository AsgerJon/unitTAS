package io.github.asgerjon.unittas;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Puts a test class (a {@link TasTestCase}) in the named suite, the name `./unittas.sh <suite>` asks for. Found at
 * start-up through Forge's annotation table, so nothing has to list it. A suite's classes run in the order of their
 * names, and each class's tests in the order of theirs.
 */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface TasSuite {

	/** The suite's name, as "commands" or "end". */
	String value();
}

package io.github.asgerjon.unittas;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Marks a mod's {@link TasHooks}, its own part of a run. Found at start-up as {@link TasSuite} is; the class needs a
 * public constructor without arguments. Several are called in the order of their class names.
 */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface TasPlugin {
}

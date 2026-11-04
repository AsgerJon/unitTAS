package io.github.asgerjon.unittas;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * The fast way, opted into: the class runs in the world as the class before it left it, instead of a fresh world of
 * its own (making one takes about 10 s). Its tests then see whatever the earlier classes left in that world: blocks,
 * the time, the weather's timers, game rules, the End and what lives there (a shulker in a chunk that isn't loaded
 * outlives the reset), a mod's world data. Take the precautions that need. A run whose classes are all marked shares
 * one world, as unitTAS did before 0.1.0-dev3.
 */
@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface SharedWorld {
}

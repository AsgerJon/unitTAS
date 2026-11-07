package io.github.asgerjon.unittas;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * A world of the class's own, for the tests that need real terrain (a map, a cartography table, a structure): made
 * fresh for the class with these settings, in a save folder of its own (saves/unittas-class), so the run's superflat
 * test world, which most tests are fine in, is never touched. The reset then puts the player where the game put it
 * when the world was made (a safe spot at its spawn), not on the superflat grass. The class after it, unannotated,
 * gets the run's superflat world back. With {@link SharedWorld} as well, the class runs on in the world the class
 * before it left, if that class asked for the same world; otherwise its own is made.
 */
@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface TasWorld {

	/** The world type: default, flat, large_biomes or amplified. */
	String type() default "default";

	/** The seed: the run's own by default, so a run's terrain is the same every time. */
	long seed() default 20261029L;

	/** The generator's options (a flat world's layers); empty: the type's own. */
	String generator() default "";

	/** Whether structures are made (villages, strongholds, a mod's). */
	boolean structures() default true;
}

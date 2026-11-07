package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;
import net.minecraft.world.WorldType;

/**
 * The class after one with a world of its own (WorldTerrainTests) gets the run's superflat world back, and the reset
 * puts the player on its grass again.
 */
@TasSuite("self")
public class WorldTerrainThenFlatTests extends TasTestCase {

	public void testTheSuperflatWorldAgain() {
		assertEqual(WorldType.FLAT, onServer(() -> world().getWorldInfo().getTerrainType()), "not the run's superflat world");
		assertEqual(4.0, onServer(() -> player().posY), "the reset didn't put the player on the superflat grass");
		assertEqual(worldNumber(), SelfPlugin.worldsSetUp, "setUpWorld didn't run for every world");
	}
}

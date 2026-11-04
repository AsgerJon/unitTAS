package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;
import net.minecraft.init.Blocks;

/**
 * A fresh world for every class (the default): the block WorldFreshATests left is gone, this world is the next one,
 * and the plugin's world hooks ran for every world made and every world closed. Alone it passes too: then this is the
 * run's first world.
 */
@TasSuite("self")
public class WorldFreshBTests extends TasTestCase {

	public void testFindsAFreshWorld() {
		assertEqual(Blocks.air, onServer(() -> world().getBlock(WorldFreshATests.X, WorldFreshATests.Y, WorldFreshATests.Z)),
			"the block WorldFreshATests left is still there");
		assertEqual(WorldFreshATests.world + 1, worldNumber(), "not the world after WorldFreshATests's");
		assertEqual(worldNumber(), SelfPlugin.worldsSetUp, "setUpWorld didn't run for every world");
		assertEqual(worldNumber() - 1, SelfPlugin.worldsTornDown, "tearDownWorld didn't run for every closed world");
	}
}

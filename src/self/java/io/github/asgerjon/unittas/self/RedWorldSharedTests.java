package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.SharedWorld;
import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;
import net.minecraft.init.Blocks;

/**
 * The self-red suite (see {@link RedTests}): @SharedWorld runs in the world as RedWorldLeavesTests left it, its block
 * and all. Alone it fails, as a shared world's tests may: that's what the mark says.
 */
@TasSuite("self-red")
@SharedWorld
public class RedWorldSharedTests extends TasTestCase {

	public void testFindsWhatTheClassBeforeLeft() {
		assertEqual(RedWorldLeavesTests.world, worldNumber(), "not the world RedWorldLeavesTests ran in");
		assertEqual(Blocks.stone, onServer(() -> world().getBlock(RedWorldLeavesTests.X, RedWorldLeavesTests.Y, RedWorldLeavesTests.Z)),
			"the block RedWorldLeavesTests left is gone");
	}
}

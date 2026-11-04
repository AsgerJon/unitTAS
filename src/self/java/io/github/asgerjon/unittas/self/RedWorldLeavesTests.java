package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;
import net.minecraft.init.Blocks;

/** The self-red suite (see {@link RedTests}): leaves a block in its world, for RedWorldSharedTests to find. */
@TasSuite("self-red")
public class RedWorldLeavesTests extends TasTestCase {

	static final int X = 70;
	static final int Y = 4;
	static final int Z = 70;

	static volatile int world;

	public void testLeavesABlock() {
		world = worldNumber();
		onServer(() -> {
			world().setBlock(X, Y, Z, Blocks.stone);
		});
	}
}

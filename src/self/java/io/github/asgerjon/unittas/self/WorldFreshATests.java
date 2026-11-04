package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;
import net.minecraft.init.Blocks;

/** Leaves a block behind in its world, for WorldFreshBTests to find gone: the next class gets a fresh world. */
@TasSuite("self")
public class WorldFreshATests extends TasTestCase {

	/** Away from the spawn point and the other tests' ground. */
	static final int X = 60;
	static final int Y = 4;
	static final int Z = 60;

	/** The world this class ran in, 0 until it has. */
	static volatile int world;

	public void testLeavesABlock() {
		world = worldNumber();
		onServer(() -> {
			world().setBlock(X, Y, Z, Blocks.stone);
		});
		assertEqual(Blocks.stone, onServer(() -> world().getBlock(X, Y, Z)));
	}
}

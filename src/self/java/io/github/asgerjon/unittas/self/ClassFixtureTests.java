package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;
import net.minecraft.init.Blocks;

/**
 * setUpClass, as unittest's: once before the class's first test, on an instance of its own, so what it makes is kept
 * in static fields; and what it builds survives the reset each test still gets. tearDownClass takes it down again
 * (that it runs, and when, is the self-red suite's RedTearDownClassTests).
 */
@TasSuite("self")
public class ClassFixtureTests extends TasTestCase {

	/** Where setUpClass builds: away from the spawn point and the other tests' ground. */
	static final int X = 40;
	static final int Y = 4;
	static final int Z = 40;

	private static int setUps;

	@Override
	protected void setUpClass() {
		setUps++;
		onServer(() -> {
			world().setBlock(X, Y, Z, Blocks.gold_block);
		});
	}

	@Override
	protected void tearDownClass() {
		onServer(() -> {
			world().setBlockToAir(X, Y, Z);
		});
	}

	public void testA_setUpClassRanBeforeTheFirstTest() {
		assertEqual(1, setUps);
		assertEqual(Blocks.gold_block, onServer(() -> world().getBlock(X, Y, Z)), "what setUpClass built is gone");
	}

	public void testB_andNotAgainBeforeTheNext() {
		assertEqual(1, setUps);
		assertEqual(Blocks.gold_block, onServer(() -> world().getBlock(X, Y, Z)), "the reset took what setUpClass built");
	}
}

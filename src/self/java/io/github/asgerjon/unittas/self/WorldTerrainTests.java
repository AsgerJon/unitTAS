package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;
import io.github.asgerjon.unittas.TasWorld;
import net.minecraft.init.Blocks;
import net.minecraft.util.MathHelper;
import net.minecraft.world.WorldType;

/**
 * A class that needs real terrain asks for a world of its own (@TasWorld): it gets that world, made fresh with its
 * settings, and the reset puts the player where the game put it there (on its ground at the spawn), not at y 4 on
 * the superflat grass. The world hooks ran for it as for any fresh world.
 */
@TasSuite("self")
@TasWorld(type = "default", seed = 1234L)
public class WorldTerrainTests extends TasTestCase {

	public void testItsOwnWorld() {
		assertEqual(WorldType.DEFAULT, onServer(() -> world().getWorldInfo().getTerrainType()), "not the world it asked for");
		assertEqual(1234L, onServer(() -> world().getSeed()), "not its seed");
		assertEqual(worldNumber(), SelfPlugin.worldsSetUp, "setUpWorld didn't run for its world");
	}

	public void testTheResetPutsThePlayerOnItsGround() {
		double y = onServer(() -> player().posY);
		assertTrue(y > 5.0, "the reset put the player at y " + y + ", as on the superflat grass, not on this world's ground");
		Object under = onServer(() -> world().getBlock(MathHelper.floor_double(player().posX),
			MathHelper.floor_double(player().posY) - 1, MathHelper.floor_double(player().posZ)));
		assertNotEqual(Blocks.air, under, "the player stands on air");
	}
}

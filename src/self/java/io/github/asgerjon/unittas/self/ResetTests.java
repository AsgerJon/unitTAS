package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;

/**
 * The reset between tests: what one test leaves of the player, the next one doesn't find. These two go together, in
 * name order: the first leaves the player flying with experience, the second checks it starts grounded and with none,
 * on both sides (addExperienceLevel below 0 clears it all and sends it).
 */
@TasSuite("self")
public class ResetTests extends TasTestCase {

	public void testA_leavesThePlayerFlyingWithExperience() {
		onServer(() -> {
			// in the air: a player standing on the ground stops flying at once (1.7.10's own rule, on the client)
			player().playerNetServerHandler.setPlayerLocation(0.5, 8.0, 0.5, 0.0F, 0.0F);
			player().capabilities.isFlying = true;
			player().sendPlayerAbilities();
			player().addExperienceLevel(5);
		});
		waitUntilOnClient("the client to show level 5", () -> mc().thePlayer.experienceLevel == 5, 40);
		waitUntilOnClient("the client to fly", () -> mc().thePlayer.capabilities.isFlying, 40);
	}

	public void testB_startsGroundedWithNoExperience() {
		assertFalse(onServer(() -> player().capabilities.isFlying), "still flying on the server");
		assertEqual(0, onServer(() -> player().experienceLevel));
		waitUntilOnClient("the client to be grounded at level 0",
			() -> !mc().thePlayer.capabilities.isFlying && mc().thePlayer.experienceLevel == 0, 40);
	}
}

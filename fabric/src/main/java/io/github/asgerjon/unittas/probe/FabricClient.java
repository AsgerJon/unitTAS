package io.github.asgerjon.unittas.probe;

import net.fabricmc.api.ClientModInitializer;
import net.minecraft.client.Minecraft;

/**
 * The 26.3 Fabric probe's client entrypoint (SPEC.md 12.3, step 1). The probe wakes and dials from
 * MixinMinecraft, at the end of Minecraft's constructor, as the 1.7.10 probe does; this is where the client's own
 * hooks register once mods initialize.
 */
public final class FabricClient implements ClientModInitializer {

	@Override
	public void onInitializeClient() {
	}

	/**
	 * Minecraft is made (MixinMinecraft): the probe is given the game's own way out (Minecraft.stop, which the Quit
	 * button calls: the game loop ends, and the game closes as a player's would), then it dials, as the 1.7.10 probe
	 * does from its MixinMinecraft. A quit asked for before there is a game to quit happens as soon as there is.
	 */
	public static void launched(Minecraft minecraft) {
		Probe probe = Probe.get();
		if (probe != null) {
			probe.leaveBy(minecraft::stop);
		}
		Probe.launched(null);
	}
}

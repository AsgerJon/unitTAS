package io.github.asgerjon.unittas.probe;

import net.fabricmc.loader.api.FabricLoader;
import net.fabricmc.loader.api.entrypoint.PreLaunchEntrypoint;

/**
 * The probe wakes here, before Minecraft's classes load, if an orchestrator left its start file in the game's folder
 * (PROTOCOL.md 2.1), as the 1.7.10 probe does from its coremod. It dials later, from MixinMinecraft.
 */
public final class FabricPreLaunch implements PreLaunchEntrypoint {

	@Override
	public void onPreLaunch() {
		Probe.early(FabricLoader.getInstance().getGameDir().toFile(), new FabricPort());
	}
}

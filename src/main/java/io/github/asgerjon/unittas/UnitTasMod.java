package io.github.asgerjon.unittas;

import cpw.mods.fml.common.Mod;
import cpw.mods.fml.common.event.FMLPreInitializationEvent;
import io.github.asgerjon.unittas.probe.ClientHooks;
import io.github.asgerjon.unittas.probe.Probe;
import io.github.asgerjon.unittas.probe.ServerHooks;

/**
 * unitTAS as a mod (README.md): asleep in an ordinary game. On the client, when ./unittas.sh has left a request in the
 * game's folder, it finds the test suites and the mods' hooks and starts the run.
 */
@Mod(modid = UnitTasMod.MODID, name = "unitTAS", version = UnitTasMod.VERSION, acceptableRemoteVersions = "*")
public final class UnitTasMod {

	public static final String MODID = "unittas";
	public static final String VERSION = "0.1.0-dev10";

	@Mod.EventHandler
	public void preInit(FMLPreInitializationEvent event) {
		// a dedicated server has no Java run to start; an orchestrator's server gets its probe's server side (ServerHooks,
		// which names no client class: none of ClientHooks' is loaded there)
		if (event.getSide().isServer()) {
			if (Probe.active()) {
				ServerHooks.register(Probe.get(), event.getAsmData());
			}
			return;
		}
		if (event.getSide().isClient()) {
			// an orchestrator's game (PROTOCOL.md): the probe has dialled it from the coremod, and gets the client's tick here
			if (Probe.active()) {
				ClientHooks.register(Probe.get(), event.getAsmData());
			}
			UnitTas.preInit(event.getAsmData());
		}
	}
}

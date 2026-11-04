package io.github.asgerjon.unittas;

import cpw.mods.fml.common.Mod;
import cpw.mods.fml.common.event.FMLPreInitializationEvent;

/**
 * unitTAS as a mod (README.md): asleep in an ordinary game. On the client, when ./unittas.sh has left a request in the
 * game's folder, it finds the test suites and the mods' hooks and starts the run.
 */
@Mod(modid = UnitTasMod.MODID, name = "unitTAS", version = UnitTasMod.VERSION, acceptableRemoteVersions = "*")
public final class UnitTasMod {

	public static final String MODID = "unittas";
	public static final String VERSION = "0.1.0-dev4";

	@Mod.EventHandler
	public void preInit(FMLPreInitializationEvent event) {
		// a dedicated server has no run to start (multiplayer runs come later)
		if (event.getSide().isClient()) {
			UnitTas.preInit(event.getAsmData());
		}
	}
}

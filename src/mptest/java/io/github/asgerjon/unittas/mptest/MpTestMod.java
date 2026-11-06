package io.github.asgerjon.unittas.mptest;

import cpw.mods.fml.common.Mod;

/**
 * unitTAS's multiplayer test mod (SPEC.md 11.3, step 6), in no release: a mod FML requires on both sides. It gives no
 * acceptableRemoteVersions, so a client without it is refused by a server that has it. Its code is {@link Red}'s.
 */
@Mod(modid = MpTestMod.MODID, name = "unitTAS multiplayer test", version = "1")
public final class MpTestMod {

	public static final String MODID = "unittas_mptest";
}

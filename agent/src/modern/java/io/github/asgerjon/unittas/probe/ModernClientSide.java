package io.github.asgerjon.unittas.probe;

import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;

/**
 * The client's own side, as the operations' shared bodies ask it (ModernThings, ModernValues; SPEC.md 19.7 step 10b):
 * a client gives it (ModernClientLookup, from ModernHooks.register), a dedicated server has none. Through it the shared
 * bodies name no client class, so a dedicated server's probe runs them too.
 */
interface ModernClientSide {

	/** The client's game itself (Minecraft), as reflection reaches it. */
	Object minecraft();

	/** The client's own player; NotReady while it has none (no world open). */
	Player player() throws ProbeException;

	/** The client's level's registries; NotReady while it has no world. */
	Object registries() throws ProbeException;

	/** The entities the client's level has, as it renders them: the level is the client's own. */
	Iterable<Entity> entities(Level level);

	/** The client's camera: 0 first person, 1 from behind, 2 from the front. */
	int camera();

	/** The client's own view of its game mode; "" while it has none. */
	String gameMode();
}

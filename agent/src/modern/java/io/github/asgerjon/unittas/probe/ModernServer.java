package io.github.asgerjon.unittas.probe;

import java.util.function.Supplier;
import net.minecraft.server.MinecraftServer;

/**
 * The server the probe's server-side operations act on (SPEC.md 19.7 step 10b): a client's integrated server while a
 * world is open, or the dedicated server the probe is in. Each side's hooks say where it is found
 * (ModernHooks.register, ModernServerHooks.starting), so the operations' bodies name no client class and are the same
 * in both.
 */
final class ModernServer {

	private static volatile Supplier<MinecraftServer> running = () -> null;

	private ModernServer() {
	}

	/** Where the running server is found, from now on. */
	static void foundBy(Supplier<MinecraftServer> where) {
		running = where;
	}

	/** The running server; null while none is (a client with no world open). */
	static MinecraftServer orNull() {
		return running.get();
	}

	/** The running server; NotReady while none is. */
	static MinecraftServer get() throws ProbeException {
		MinecraftServer server = running.get();
		if (server == null) {
			throw new ProbeException("NotReady", "no world is open", null);
		}
		return server;
	}
}

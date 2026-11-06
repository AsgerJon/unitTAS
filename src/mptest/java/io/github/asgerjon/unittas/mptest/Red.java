package io.github.asgerjon.unittas.mptest;

/**
 * Common code that reaches a client-only class, as a mod's bug does: harmless in a client, where the class is, and a
 * NoClassDefFoundError on a dedicated server, where it isn't. The red test calls it on the server (unitTAS's
 * reflection) and expects that error: the failure only a dedicated server shows.
 */
public final class Red {

	private Red() {
	}

	/** The client's game: there is none on a dedicated server. */
	public static String reachClient() {
		return String.valueOf(net.minecraft.client.Minecraft.getMinecraft());
	}
}

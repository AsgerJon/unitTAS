package io.github.asgerjon.unittas.probe;

import net.minecraft.SharedConstants;

/**
 * This version's own name and its port's, with no client class (SPEC.md 19.7 step 10b): a dedicated server's probe
 * says them as a client's does (Version.port and Version.minecraft are these).
 */
final class VersionName {

	private VersionName() {
	}

	/** The port this probe is for: the version it is built for. */
	static String port() {
		return "1.20.1";
	}

	/** The game's own version, as it says it. */
	static String minecraft() {
		return SharedConstants.getCurrentVersion().getName();
	}
}

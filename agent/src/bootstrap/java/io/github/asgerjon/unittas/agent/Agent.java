package io.github.asgerjon.unittas.agent;

import java.io.File;
import java.lang.instrument.Instrumentation;

/**
 * unitTAS's probe as a Java agent (SPEC.md 19.7 step 5): no loader, no library, only the JDK. Given the game's folder
 * (-javaagent:unittas-probe.jar=GAME), it wakes only if an orchestrator left its start file there (PROTOCOL.md 2.1):
 * then it rewrites the game's few hooked methods as their classes load (Hooks, Rewriter), and the probe itself, packed
 * inside this jar, is loaded under the game's own class loader at the first hook (Bridge). Without a start file it
 * does nothing at all: an ordinary game runs as it would without it.
 */
public final class Agent {

	/** The start file, as the probe core's StartFile names it (that class is the probe's, not this bootstrap's). */
	static final String START_FILE = "unittas/probe.properties";

	private Agent() {
	}

	public static void premain(String gameFolder, Instrumentation instrumentation) {
		if (gameFolder == null || gameFolder.isEmpty()) {
			System.err.println("[unitTAS] the probe was given no game folder (-javaagent:unittas-probe.jar=GAME): it"
				+ " sleeps");
			return;
		}
		File game = new File(gameFolder);
		if (!new File(game, START_FILE).isFile()) {
			return;
		}
		Bridge.prepare(game);
		instrumentation.addTransformer(new Rewriter(Hooks.TABLE));
		System.err.println("[unitTAS] the probe wakes: " + Hooks.TABLE.size() + " hooks to put into the game's classes");
	}
}

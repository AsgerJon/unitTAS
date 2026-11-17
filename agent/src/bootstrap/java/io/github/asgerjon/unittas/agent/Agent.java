package io.github.asgerjon.unittas.agent;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.lang.instrument.Instrumentation;
import java.nio.file.Path;
import java.util.List;

/**
 * unitTAS's probe as a Java agent (SPEC.md 19.7 step 5): no loader, no library, only the JDK. Given the game's folder
 * (-javaagent:unittas-probe.jar=GAME), it wakes only if an orchestrator left its start file there (PROTOCOL.md 2.1):
 * then it rewrites the game's few hooked methods as their classes load (Hooks, Rewriter), and the probe itself, packed
 * inside this jar, is loaded under the game's own class loader at the first hook (Bridge). The game's code reaches
 * the bridge through JDK types only, so a loader that hides the agent's jar from the game (Fabric's) doesn't matter.
 * Where the game runs under other names than Mojang's (before 26.1: SPEC.md 19.7 step 6b) the launcher names the
 * version's table of them (-Dunittas.names=TABLE): the hooks are renamed by it, and the probe as it loads. Without a
 * start file it does nothing at all: an ordinary game runs as it would without it.
 */
public final class Agent {

	/** The start file, as the probe core's StartFile names it (that class is the probe's, not this bootstrap's). */
	static final String START_FILE = "unittas/probe.properties";
	/** The system property naming the table of the names the game runs under, where they aren't Mojang's. */
	static final String NAMES = "unittas.names";
	/** This agent's version's hooks (Hooks.read), beside the bootstrap in its jar. */
	static final String HOOKS_FILE = "/unittas-probe-hooks.txt";

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
		Hooks.Table table;
		try (InputStream in = Agent.class.getResourceAsStream(HOOKS_FILE)) {
			if (in == null) {
				System.err.println("[unitTAS] the probe sleeps: its jar holds no " + HOOKS_FILE);
				return;
			}
			table = Hooks.read(in, "the agent");
		} catch (IOException | IllegalArgumentException e) {
			System.err.println("[unitTAS] the probe sleeps: its hooks can't be read: " + e);
			return;
		}
		List<Hooks.Hook> hooks = table.hooks();
		Names names = null;
		String named = System.getProperty(NAMES);
		if (named != null) {
			try {
				names = Names.read(Path.of(named));
				hooks = Hooks.renamed(hooks, names);
			} catch (IOException | IllegalArgumentException e) {
				// never woken by names that would hook the wrong methods: the orchestrator, never greeted, says so
				System.err.println("[unitTAS] the probe sleeps: the names in " + named + " can't be used: " + e);
				return;
			}
		}
		Bridge.install(game, table.entry(), hooks, names);
		instrumentation.addTransformer(new Rewriter(hooks));
		System.err.println("[unitTAS] the probe wakes: " + hooks.size() + " hooks to put into the game's classes"
			+ (names == null ? "" : ", by " + names.kind + " names (" + names.minecraft + ")"));
	}
}

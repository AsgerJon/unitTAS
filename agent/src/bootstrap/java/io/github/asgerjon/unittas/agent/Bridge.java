package io.github.asgerjon.unittas.agent;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.Collections;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.BiFunction;

/**
 * Where the game's hooked methods call (Rewriter), and the probe they reach. The hooks know the bridge only as a JDK
 * BiFunction in the JVM's system properties (HOOKS), and the pass mark beside it (PASS): a loader may keep the game
 * from seeing the agent's jar (Fabric's Knot does), so nothing of unitTAS's is named in the game's code. The probe
 * itself is a jar packed inside the agent's (unittas-probe-inner.jar): at the first hook it is written into the
 * game's folder and loaded by a class loader of its own whose parent is the game's own (the hooked class's: vanilla's
 * application loader, or Knot), so it sees exactly the game's classes. It too is given JDK types only (its start: the
 * game's folder, the pass mark, the hooked classes and those rewritten so far) and answers with its own BiFunction,
 * which every hook then goes to. A probe that can't be loaded is said on the error stream, once, and every hook then
 * passes: the game runs on, and the orchestrator, never greeted, says so.
 */
final class Bridge implements BiFunction<String, Object[], Object> {

	/** The system properties the hooks find the bridge and the pass mark by. */
	static final String HOOKS = "unittas.probe.hooks";
	static final String PASS = "unittas.probe.pass";

	private static final String INNER = "/unittas-probe-inner.jar";
	private static final String ENTRY = "io.github.asgerjon.unittas.probe.V26Entry";
	private static final Set<String> REWRITTEN = ConcurrentHashMap.newKeySet();

	private final File game;
	/** A BEFORE hook's value for "go on with the method". */
	private final Object pass = new Object();
	private volatile BiFunction<String, Object[], Object> probe;
	private volatile boolean broken;

	private Bridge(File game) {
		this.game = game;
	}

	/** The bridge for the game in this folder, where the hooks will look for it. */
	static void install(File game) {
		Bridge bridge = new Bridge(game);
		System.getProperties().put(PASS, bridge.pass);
		System.getProperties().put(HOOKS, bridge);
	}

	static void rewritten(String className) {
		REWRITTEN.add(className);
	}

	/** Every class the probe hooks, by its internal name (net/minecraft/client/Minecraft). */
	static Set<String> hookedClasses() {
		Set<String> owners = new TreeSet<>();
		for (Hooks.Hook hook : Hooks.TABLE) {
			owners.add(hook.owner());
		}
		return Collections.unmodifiableSet(owners);
	}

	/** A hook: its name, and [the hooked class, the instance or null, the method's arguments]. */
	@Override
	public Object apply(String hook, Object[] call) {
		BiFunction<String, Object[], Object> found = probe((Class<?>) call[0]);
		return found == null ? pass : found.apply(hook, call);
	}

	private BiFunction<String, Object[], Object> probe(Class<?> owner) {
		BiFunction<String, Object[], Object> found = probe;
		if (found != null || broken) {
			return found;
		}
		synchronized (this) {
			if (probe == null && !broken) {
				try {
					probe = load(owner.getClassLoader());
				} catch (Throwable e) {
					broken = true;
					System.err.println("[unitTAS] the probe couldn't be loaded: " + e);
					e.printStackTrace();
				}
			}
			return probe;
		}
	}

	/** The probe's jar, out of the agent's into the game's folder, loaded under the game's class loader. */
	@SuppressWarnings("unchecked")
	private BiFunction<String, Object[], Object> load(ClassLoader gameLoader) throws IOException,
		ReflectiveOperationException {
		File folder = new File(game, "unittas");
		File jar = new File(folder, "probe-inner.jar");
		try (InputStream in = Bridge.class.getResourceAsStream(INNER)) {
			if (in == null) {
				throw new IOException("the agent's jar holds no " + INNER);
			}
			Files.createDirectories(folder.toPath());
			Files.copy(in, jar.toPath(), StandardCopyOption.REPLACE_EXISTING);
		}
		URLClassLoader loader = new URLClassLoader("unittas-probe", new URL[] {jar.toURI().toURL()}, gameLoader);
		Class<?> entry = Class.forName(ENTRY, true, loader);
		return (BiFunction<String, Object[], Object>) entry.getMethod("start", File.class, Object.class, Set.class,
			Set.class).invoke(null, game, pass, hookedClasses(), Collections.unmodifiableSet(REWRITTEN));
	}
}

package io.github.asgerjon.unittas.agent;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.BiFunction;
import java.util.function.Function;

/**
 * Where the game's hooked methods call (Rewriter), and the probe they reach. The hooks know the bridge only as a JDK
 * BiFunction in the JVM's system properties (HOOKS), and the pass mark beside it (PASS): a loader may keep the game
 * from seeing the agent's jar (Fabric's Knot does), so nothing of unitTAS's is named in the game's code. The probe
 * itself is a jar packed inside the agent's (unittas-probe-inner.jar): at the first hook it is written into the
 * game's folder and loaded by a class loader of its own whose parent is the game's own (the hooked class's: vanilla's
 * application loader, or Knot), so it sees exactly the game's classes. It too is given JDK types only (its start: the
 * game's folder, the pass mark, the hooked classes and those rewritten so far) and answers with its own BiFunction,
 * which every hook then goes to. A probe that can't be loaded ends the game (Asger, 2026-11-17: "if unittas opens a
 * game, unittas closes it", "it must never hang"): unitTAS opened it for a run, and a game no probe drives is no test,
 * so the agent says why on the error stream and halts the JVM by its own exit code (NO_PROBE), at once, rather than
 * leave the orchestrator waiting for a hello that never comes.
 */
final class Bridge implements BiFunction<String, Object[], Object> {

	/** The system properties the hooks find the bridge and the pass mark by. */
	static final String HOOKS = "unittas.probe.hooks";
	static final String PASS = "unittas.probe.pass";

	/** The game's exit code when its probe can't be loaded. */
	static final int NO_PROBE = 70;

	private static final String INNER = "/unittas-probe-inner.jar";
	private static final Set<String> REWRITTEN = ConcurrentHashMap.newKeySet();

	private final File game;
	/** The probe's entry class (its version's hooks file names it): start(), then a hook's every call. */
	private final String entry;
	private final List<Hooks.Hook> hooks;
	/** The names the game runs under, where they aren't Mojang's: the probe is renamed as it loads (null: not). */
	private final Names names;
	/** A BEFORE hook's value for "go on with the method". */
	private final Object pass = new Object();
	private volatile BiFunction<String, Object[], Object> probe;
	private volatile boolean broken;

	private Bridge(File game, String entry, List<Hooks.Hook> hooks, Names names) {
		this.game = game;
		this.entry = entry;
		this.hooks = hooks;
		this.names = names;
	}

	/**
	 * The bridge for the game in this folder, where the hooks will look for it: its hooks by the names the game runs
	 * under, and those names where they aren't Mojang's (null where they are).
	 */
	static void install(File game, String entry, List<Hooks.Hook> hooks, Names names) {
		Bridge bridge = new Bridge(game, entry, hooks, names);
		System.getProperties().put(PASS, bridge.pass);
		System.getProperties().put(HOOKS, bridge);
	}

	static void rewritten(String className) {
		REWRITTEN.add(className);
	}

	/** Every class the hooks name, by its internal name (net/minecraft/client/Minecraft) as the game runs it. */
	static Set<String> hookedClasses(List<Hooks.Hook> hooks) {
		Set<String> owners = new TreeSet<>();
		for (Hooks.Hook hook : hooks) {
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
		Throwable failed = null;
		synchronized (this) {
			if (probe == null && !broken) {
				try {
					probe = load(owner.getClassLoader());
				} catch (Throwable e) {
					broken = true;
					failed = e;
				}
			}
			found = probe;
		}
		if (failed != null) {
			// outside the lock: nothing the game does as it goes may wait on it
			endTheGame(failed);
		}
		return found;
	}

	/**
	 * The game ended, its probe not loaded: why, on the error stream, and the JVM halted (no shutdown hook of the
	 * game's runs: there is nothing of a run's to keep, and one could wait on what this hook holds).
	 */
	private static void endTheGame(Throwable cause) {
		System.err.println("[unitTAS] the probe couldn't be loaded, so the game ends: " + cause);
		cause.printStackTrace();
		System.err.flush();
		Runtime.getRuntime().halt(NO_PROBE);
	}

	/**
	 * The probe's jar, out of the agent's into the game's folder, loaded under the game's class loader: as it is where
	 * the game runs under Mojang's names, renamed as it loads where it doesn't (RenamingLoader).
	 */
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
		URLClassLoader loader = names == null
			? new URLClassLoader(new URL[] {jar.toURI().toURL()}, gameLoader)
			: RenamingLoader.of(jar, gameLoader, names);
		Class<?> started = Class.forName(entry, true, loader);
		Function<String, String> lookup = names == null ? null : names::lookup;
		return (BiFunction<String, Object[], Object>) started.getMethod("start", File.class, Object.class, Set.class,
			Set.class, Function.class).invoke(null, game, pass, hookedClasses(hooks), Collections.unmodifiableSet(REWRITTEN),
			lookup);
	}
}

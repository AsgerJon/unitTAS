package io.github.asgerjon.unittas.agent;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Where the game's hooked methods call (Rewriter), and the probe they reach. The probe itself is a jar packed inside
 * the agent's (unittas-probe-inner.jar): at the first hook it is written into the game's folder and loaded by a class
 * loader of its own whose parent is the game's own (the hooked class's: vanilla's application loader, or Fabric's
 * Knot), so it sees exactly the game's classes; its entry (V26Entry) is the Handler every hook then goes to. A probe
 * that can't be loaded is said on the error stream, once, and every hook then passes: the game runs on, and the
 * orchestrator, never greeted, says so.
 */
public final class Bridge {

	/** A BEFORE hook's value for "go on with the method". */
	public static final Object PASS = new Object();

	/** The probe, as the hooks reach it. */
	public interface Handler {
		/** A BEFORE hook: PASS, or the method's value (anything for a void one), ending it there. */
		Object before(String hook, Object self, Object[] arguments);

		/** An AFTER hook. */
		void after(String hook, Object self, Object[] arguments);
	}

	private static final String INNER = "/unittas-probe-inner.jar";
	private static final String ENTRY = "io.github.asgerjon.unittas.probe.V26Entry";
	private static final Set<String> REWRITTEN = ConcurrentHashMap.newKeySet();

	private static volatile File game;
	private static volatile Handler handler;
	private static volatile boolean broken;

	private Bridge() {
	}

	static void prepare(File gameFolder) {
		game = gameFolder;
	}

	static void rewritten(String className) {
		REWRITTEN.add(className);
	}

	/** The hooked classes rewritten so far, by their internal names. */
	public static Set<String> rewrittenClasses() {
		return Set.copyOf(REWRITTEN);
	}

	/** Every class the probe hooks, by its internal name (net/minecraft/client/Minecraft). */
	public static Set<String> hookedClasses() {
		Set<String> owners = new java.util.TreeSet<>();
		for (Hooks.Hook hook : Hooks.TABLE) {
			owners.add(hook.owner());
		}
		return owners;
	}

	public static Object before(String hook, Class<?> owner, Object self, Object[] arguments) {
		Handler found = handler(owner);
		return found == null ? PASS : found.before(hook, self, arguments);
	}

	public static void after(String hook, Class<?> owner, Object self, Object[] arguments) {
		Handler found = handler(owner);
		if (found != null) {
			found.after(hook, self, arguments);
		}
	}

	private static Handler handler(Class<?> owner) {
		Handler found = handler;
		if (found != null || broken) {
			return found;
		}
		synchronized (Bridge.class) {
			if (handler == null && !broken) {
				try {
					handler = load(owner.getClassLoader());
				} catch (Throwable e) {
					broken = true;
					System.err.println("[unitTAS] the probe couldn't be loaded: " + e);
					e.printStackTrace();
				}
			}
			return handler;
		}
	}

	/** The probe's jar, out of the agent's into the game's folder, loaded under the game's class loader. */
	private static Handler load(ClassLoader gameLoader) throws IOException, ReflectiveOperationException {
		File folder = new File(game, "unittas");
		File jar = new File(folder, "probe-inner.jar");
		try (InputStream in = Bridge.class.getResourceAsStream(INNER)) {
			if (in == null) {
				throw new IOException("the agent's jar holds no " + INNER);
			}
			Files.createDirectories(folder.toPath());
			Files.copy(in, jar.toPath(), StandardCopyOption.REPLACE_EXISTING);
		}
		URLClassLoader probe = new URLClassLoader("unittas-probe", new URL[] {jar.toURI().toURL()}, gameLoader);
		Class<?> entry = Class.forName(ENTRY, true, probe);
		return (Handler) entry.getMethod("start", File.class).invoke(null, game);
	}
}

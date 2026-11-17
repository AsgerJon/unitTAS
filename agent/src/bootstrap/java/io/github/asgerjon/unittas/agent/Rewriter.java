package io.github.asgerjon.unittas.agent;

import java.io.IOException;
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;

/**
 * Puts the hooks into the game's classes as they load (SPEC.md 19.7 step 6a), by wrapping: each hooked method is
 * renamed (tick to tick$unittas) and made private, and a wrapper takes its name (Wrapper): it calls the BEFORE hooks,
 * which may end the method at once with their value, then the original, then the AFTER hooks. The game's own code is
 * never edited, and nothing but the JDK is used (ClassBytes reads and writes the class file), so it runs on every Java
 * the agent runs on (17 on). The code put in names JDK classes only, never one of unitTAS's: a loader may keep the
 * game from seeing the agent's jar (Fabric's Knot does), so the hooks reach the bridge as a
 * java.util.function.BiFunction kept in the JVM's system properties (Bridge.HOOKS), the pass mark beside it
 * (Bridge.PASS). A class the game loads under Fabric is seen after Mixin has made it. A class whose hooks can't all be
 * put in (a method not there, a constructor, a method with no code, an interface) is said on the error stream and
 * left exactly as it was; the probe then reports it missing.
 */
final class Rewriter implements ClassFileTransformer {

	/** What a hooked method's original is renamed to: its name and this. */
	static final String RENAMED = "$unittas";

	private final Map<String, List<Hooks.Hook>> byOwner = new HashMap<>();

	Rewriter(List<Hooks.Hook> hooks) {
		for (Hooks.Hook hook : hooks) {
			byOwner.computeIfAbsent(hook.owner(), owner -> new ArrayList<>()).add(hook);
		}
	}

	@Override
	public byte[] transform(ClassLoader loader, String name, Class<?> redefined, ProtectionDomain domain, byte[] bytes) {
		List<Hooks.Hook> hooks = byOwner.get(name);
		if (hooks == null) {
			return null;
		}
		try {
			byte[] rewritten = rewrite(bytes, hooks);
			Bridge.rewritten(name);
			return rewritten;
		} catch (Throwable e) {
			System.err.println("[unitTAS] couldn't put the probe's hooks into " + name + ": " + e);
			e.printStackTrace();
			return null;
		}
	}

	/** The class with every hook of its put in, or IllegalArgumentException saying which can't be. */
	static byte[] rewrite(byte[] bytes, List<Hooks.Hook> hooks) throws IOException {
		ClassBytes file = new ClassBytes(bytes);
		if ((file.access & ClassBytes.INTERFACE) != 0) {
			throw new IllegalArgumentException(file.name() + " is an interface: the probe hooks classes only");
		}
		Map<ClassBytes.Method, List<Hooks.Hook>> byMethod = new IdentityHashMap<>();
		List<ClassBytes.Method> hooked = new ArrayList<>();
		for (Hooks.Hook hook : hooks) {
			if (hook.method().startsWith("<")) {
				throw new IllegalArgumentException(hook.method() + " can't be wrapped: " + hook);
			}
			boolean found = false;
			for (ClassBytes.Method method : file.methods) {
				if (file.utf8(method.name).equals(hook.method())
					&& (hook.descriptor() == null || file.utf8(method.descriptor).equals(hook.descriptor()))) {
					found = true;
					if (!byMethod.containsKey(method)) {
						byMethod.put(method, new ArrayList<>());
						hooked.add(method);
					}
					byMethod.get(method).add(hook);
				}
			}
			if (!found) {
				throw new IllegalArgumentException("no method " + hook.method()
					+ (hook.descriptor() == null ? "" : hook.descriptor()) + " in " + file.name() + ": " + hook);
			}
		}
		List<ClassBytes.Method> wrappers = new ArrayList<>();
		for (ClassBytes.Method method : hooked) {
			String name = file.utf8(method.name);
			String descriptor = file.utf8(method.descriptor);
			if ((method.access & (ClassBytes.ABSTRACT | ClassBytes.NATIVE)) != 0) {
				throw new IllegalArgumentException(name + descriptor + " in " + file.name() + " has no code to wrap");
			}
			String renamed = name + RENAMED;
			for (ClassBytes.Method other : file.methods) {
				if (file.utf8(other.name).equals(renamed) && file.utf8(other.descriptor).equals(descriptor)) {
					throw new IllegalArgumentException(file.name() + " has a " + renamed + descriptor + " already");
				}
			}
			List<Hooks.Hook> before = new ArrayList<>();
			List<Hooks.Hook> after = new ArrayList<>();
			for (Hooks.Hook hook : byMethod.get(method)) {
				(hook.when() == Hooks.When.BEFORE ? before : after).add(hook);
			}
			wrappers.add(Wrapper.wrap(file, method, renamed, before, after));
		}
		file.methods.addAll(wrappers);
		return file.bytes();
	}
}

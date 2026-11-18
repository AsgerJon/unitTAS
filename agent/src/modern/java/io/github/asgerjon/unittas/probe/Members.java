package io.github.asgerjon.unittas.probe;

import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.function.Function;

/**
 * The game's members the probe reaches that aren't public (SPEC.md 19.7 steps 5 and 6c), by their Mojang names: what
 * the Fabric probe's accessors and invokers did, by plain reflection. Where the game runs under other names (before
 * 26.1), each name is the running one the bridge's lookup gives (its Names.lookup, handed to the probe as a JDK
 * function), and a class the probe names to the orchestrator is named by its Mojang name (className). Each member is
 * found once, where it is declared; one the version hasn't, or the lookup can't name, is an IllegalStateException
 * naming it, at once.
 */
final class Members {

	/** The bridge's lookup of the names the game runs under (Names.lookup), or null where they are Mojang's. */
	static volatile Function<String, String> names;

	private Members() {
	}

	/** A field declared by the class, readable. */
	static Field field(Class<?> owner, String name) {
		String running = running("f\t" + mojang(owner) + "\t" + name, name, owner, "field");
		try {
			Field field = owner.getDeclaredField(running);
			field.setAccessible(true);
			return field;
		} catch (NoSuchFieldException e) {
			throw new IllegalStateException(VersionName.port() + "'s " + className(owner) + " has no field " + name
				+ (running.equals(name) ? "" : " (" + running + ")") + ": the probe needs it", e);
		}
	}

	/** A method declared by the class, callable. */
	static Method method(Class<?> owner, String name, Class<?>... parameters) {
		StringBuilder descriptor = new StringBuilder("(");
		for (Class<?> parameter : parameters) {
			descriptor.append(descriptor(parameter));
		}
		descriptor.append(')');
		String running = running("m\t" + mojang(owner) + "\t" + name + "\t" + descriptor, name, owner, "method");
		try {
			Method method = owner.getDeclaredMethod(running, parameters);
			method.setAccessible(true);
			return method;
		} catch (NoSuchMethodException e) {
			throw new IllegalStateException(VersionName.port() + "'s " + className(owner) + " has no method " + name
				+ descriptor + (running.equals(name) ? "" : " (" + running + ")") + ": the probe needs it", e);
		}
	}

	/** What the game's names run under, as the hello says it: mojang, or the lookup's (obfuscated, intermediary). */
	static String namesKind() {
		Function<String, String> lookup = names;
		return lookup == null ? "mojang" : lookup.apply("kind");
	}

	/** A class's Mojang internal name (net/minecraft/client/Minecraft); a class not the game's, its own. */
	static String mojang(Class<?> type) {
		return mojang(type.getName().replace('.', '/'));
	}

	/** A running class's Mojang internal name, by its running internal name. */
	static String mojang(String internalName) {
		Function<String, String> lookup = names;
		String found = lookup == null ? null : lookup.apply("c\t" + internalName);
		return found == null ? internalName : found;
	}

	/** A class as the orchestrator reads it: its Mojang binary name (net.minecraft.client.gui.screens.TitleScreen). */
	static String className(Class<?> type) {
		return mojang(type).replace('/', '.');
	}

	/** A running class's Mojang binary name, by its running binary name (a stack frame's). */
	static String className(String binaryName) {
		return mojang(binaryName.replace('.', '/')).replace('/', '.');
	}

	/** A class's running binary name by its Mojang binary name; a class not the game's, its own. */
	static String runningClass(String binaryName) {
		Function<String, String> lookup = names;
		String found = lookup == null ? null : lookup.apply("C\t" + binaryName.replace('.', '/'));
		return found == null ? binaryName : found.replace('/', '.');
	}

	/**
	 * Whether a class is the game's: one the lookup has a Mojang name for. Its name may be its running one (beside
	 * Forge 1.20.1 the classes keep Mojang's names, their members SRG's), so it is the lookup that says.
	 */
	private static boolean isGame(Class<?> type) {
		Function<String, String> lookup = names;
		return lookup != null && lookup.apply("c\t" + type.getName().replace('.', '/')) != null;
	}

	/**
	 * The running name of the field by that Mojang name the class declares (reflection's, class by class): for a class
	 * of the game's, its own field's by the lookup, or null where it declares none; for another (the JDK's, a mod's),
	 * the name itself.
	 */
	static String runningField(Class<?> declaring, String name) {
		if (!isGame(declaring)) {
			return name;
		}
		return names.apply("f\t" + mojang(declaring) + "\t" + name);
	}

	/** Whether the method, its declaring class's own, is the one by that Mojang name (by the lookup, for the game's). */
	static boolean isMethod(Method method, String name) {
		Class<?> declaring = method.getDeclaringClass();
		if (!isGame(declaring)) {
			return method.getName().equals(name);
		}
		StringBuilder parameters = new StringBuilder("(");
		for (Class<?> parameter : method.getParameterTypes()) {
			parameters.append(descriptor(parameter));
		}
		parameters.append(')');
		String running = names.apply("m\t" + mojang(declaring) + "\t" + name + "\t" + parameters);
		return method.getName().equals(running);
	}

	private static String running(String key, String name, Class<?> owner, String what) {
		Function<String, String> lookup = names;
		if (lookup == null) {
			return name;
		}
		String found = lookup.apply(key);
		if (found == null) {
			throw new IllegalStateException("no " + lookup.apply("kind") + " name for " + className(owner) + "'s " + what
				+ " " + name + ": the probe needs it");
		}
		return found;
	}

	/** A parameter's descriptor, in Mojang's names. */
	private static String descriptor(Class<?> type) {
		if (type.isArray()) {
			return "[" + descriptor(type.getComponentType());
		}
		if (type.isPrimitive()) {
			return String.valueOf(type == void.class ? 'V' : type == boolean.class ? 'Z' : type == byte.class ? 'B'
				: type == char.class ? 'C' : type == short.class ? 'S' : type == int.class ? 'I' : type == long.class ? 'J'
				: type == float.class ? 'F' : 'D');
		}
		return "L" + mojang(type) + ";";
	}

	/** The field's value on the object. */
	@SuppressWarnings("unchecked")
	static <T> T get(Field field, Object from) {
		try {
			return (T) field.get(from);
		} catch (IllegalAccessException e) {
			throw new IllegalStateException("can't read " + field + ": " + e, e);
		}
	}

	/** The method called on the object; what it throws, thrown on. */
	@SuppressWarnings("unchecked")
	static <T> T call(Method method, Object on, Object... arguments) {
		try {
			return (T) method.invoke(on, arguments);
		} catch (InvocationTargetException e) {
			Throwable cause = e.getCause();
			if (cause instanceof RuntimeException) {
				throw (RuntimeException) cause;
			}
			if (cause instanceof Error) {
				throw (Error) cause;
			}
			throw new IllegalStateException(method + " threw " + cause, cause);
		} catch (IllegalAccessException e) {
			throw new IllegalStateException("can't call " + method + ": " + e, e);
		}
	}
}

package io.github.asgerjon.unittas.probe;

import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

/**
 * The game's members the probe reaches that aren't public (SPEC.md 19.7 step 5), by their Mojang names (26.x is
 * unobfuscated): what the Fabric probe's accessors and invokers did, by plain reflection. Each is found once, where
 * it is declared; one 26.3 hasn't is an IllegalStateException naming it, at once.
 */
final class Members {

	private Members() {
	}

	/** A field declared by the class, readable. */
	static Field field(Class<?> owner, String name) {
		try {
			Field field = owner.getDeclaredField(name);
			field.setAccessible(true);
			return field;
		} catch (NoSuchFieldException e) {
			throw new IllegalStateException("26.3's " + owner.getName() + " has no field " + name + ": the probe needs it",
				e);
		}
	}

	/** A method declared by the class, callable. */
	static Method method(Class<?> owner, String name, Class<?>... parameters) {
		try {
			Method method = owner.getDeclaredMethod(name, parameters);
			method.setAccessible(true);
			return method;
		} catch (NoSuchMethodException e) {
			throw new IllegalStateException("26.3's " + owner.getName() + " has no method " + name + ": the probe needs it",
				e);
		}
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

package io.github.asgerjon.unittas.probe;

import java.lang.reflect.Method;
import java.util.Collection;
import java.util.Optional;

/**
 * The loader beside the probe, as that loader says itself (SPEC.md 19.7 steps 5, 7, 8 and 10): Fabric Loader, or
 * NeoForge's or Forge's FML, read by reflection (the probe depends on no loader's API); none in vanilla. JDK only and
 * no game class, so a client's port and a dedicated server's (ModernPort, ModernServerPort) both say theirs by it.
 */
final class ModernLoaders {

	private static final String FABRIC = "net.fabricmc.loader.api.FabricLoader";
	/**
	 * The FML loaders the probe knows (SPEC.md 19.7 steps 7 and 8): each one's name, its FMLLoader, its ModList, and the
	 * version info's method that says its version.
	 */
	private static final String[][] FMLS = {
		{"neoforge", "net.neoforged.fml.loading.FMLLoader", "net.neoforged.fml.ModList", "neoForgeVersion"},
		{"forge", "net.minecraftforge.fml.loading.FMLLoader", "net.minecraftforge.fml.ModList", "forgeVersion"},
	};

	private ModernLoaders() {
	}

	/** Fabric Loader's own instance, when the mod under test brought it; empty in vanilla. */
	static Optional<Object> fabric() {
		try {
			Class<?> loader = Class.forName(FABRIC, true, ModernLoaders.class.getClassLoader());
			return Optional.of(loader.getMethod("getInstance").invoke(null));
		} catch (ClassNotFoundException e) {
			return Optional.empty();
		} catch (ReflectiveOperationException e) {
			throw new IllegalStateException("Fabric Loader is here but doesn't say itself: " + e, e);
		}
	}

	/** A mod's version as Fabric Loader says it; "" in vanilla, or for a mod it hasn't. */
	static String fabricVersion(String mod) {
		Optional<Object> loader = fabric();
		if (loader.isEmpty()) {
			return "";
		}
		try {
			Optional<?> container = (Optional<?>) loader.get().getClass().getMethod("getModContainer", String.class)
				.invoke(loader.get(), mod);
			return container.isPresent() ? versionOf(container.get()) : "";
		} catch (ReflectiveOperationException e) {
			throw new IllegalStateException("Fabric Loader doesn't say " + mod + "'s version: " + e, e);
		}
	}

	/** The FML loader beside the probe (its FMLS entry), when the mod under test brought NeoForge or Forge. */
	static Optional<String[]> fml() {
		for (String[] each : FMLS) {
			try {
				Class.forName(each[1], false, ModernLoaders.class.getClassLoader());
				return Optional.of(each);
			} catch (ClassNotFoundException e) {
				// not this one
			}
		}
		return Optional.empty();
	}

	/** An FML loader's version as it says it (its version info). */
	static String fmlVersion(String[] fml) {
		try {
			Object info = versionInfo(Class.forName(fml[1], true, ModernLoaders.class.getClassLoader()));
			return (String) info.getClass().getMethod(fml[3]).invoke(info);
		} catch (ReflectiveOperationException e) {
			throw new IllegalStateException(fml[0] + " is here but doesn't say its version: " + e, e);
		}
	}

	/**
	 * FML's version info, as each FML has it: FML 4's (NeoForge for 1.21.x) and Forge 47's a static versionInfo(); from
	 * FML 10 on (NeoForge for 26.x) the running loader's (FMLLoader.getCurrent()) getVersionInfo().
	 */
	private static Object versionInfo(Class<?> loader) throws ReflectiveOperationException {
		for (Method each : loader.getMethods()) {
			if (each.getName().equals("versionInfo") && java.lang.reflect.Modifier.isStatic(each.getModifiers())
				&& each.getParameterCount() == 0) {
				return each.invoke(null);
			}
		}
		Object current = loader.getMethod("getCurrent").invoke(null);
		return loader.getMethod("getVersionInfo").invoke(current);
	}

	/** Each mod the loader beside the probe has, (id, name, version): Fabric Loader's or FML's; none in vanilla. */
	static java.util.List<String[]> mods() {
		if (fabric().isPresent()) {
			return fabricMods();
		}
		return fml().map(ModernLoaders::fmlMods).orElseGet(java.util.ArrayList::new);
	}

	/** Each mod an FML loader has (its ModList, as IModInfo says each), (id, name, version). */
	static java.util.List<String[]> fmlMods(String[] fml) {
		java.util.List<String[]> out = new java.util.ArrayList<>();
		try {
			Class<?> list = Class.forName(fml[2], true, ModernLoaders.class.getClassLoader());
			Object mods = list.getMethod("get").invoke(null);
			for (Object mod : (Collection<?>) list.getMethod("getMods").invoke(mods)) {
				out.add(new String[] {(String) method(mod, "getModId").invoke(mod),
					(String) method(mod, "getDisplayName").invoke(mod), String.valueOf(method(mod, "getVersion").invoke(mod))});
			}
			return out;
		} catch (ReflectiveOperationException e) {
			throw new IllegalStateException(fml[0] + " doesn't list its mods: " + e, e);
		}
	}

	/** Each mod Fabric Loader has, (id, name, version); none in vanilla. */
	static java.util.List<String[]> fabricMods() {
		java.util.List<String[]> out = new java.util.ArrayList<>();
		Optional<Object> loader = fabric();
		if (loader.isEmpty()) {
			return out;
		}
		try {
			Collection<?> mods = (Collection<?>) loader.get().getClass().getMethod("getAllMods").invoke(loader.get());
			for (Object mod : mods) {
				Object metadata = method(mod, "getMetadata").invoke(mod);
				out.add(new String[] {(String) method(metadata, "getId").invoke(metadata),
					(String) method(metadata, "getName").invoke(metadata), versionOf(mod)});
			}
			return out;
		} catch (ReflectiveOperationException e) {
			throw new IllegalStateException("Fabric Loader doesn't list its mods: " + e, e);
		}
	}

	private static String versionOf(Object container) throws ReflectiveOperationException {
		Object metadata = method(container, "getMetadata").invoke(container);
		Object version = method(metadata, "getVersion").invoke(metadata);
		return (String) method(version, "getFriendlyString").invoke(version);
	}

	/** A public method by name, through the object's public interfaces (the loaders' implementations are internal). */
	private static Method method(Object on, String name) throws NoSuchMethodException {
		for (Class<?> type : on.getClass().getInterfaces()) {
			try {
				return type.getMethod(name);
			} catch (NoSuchMethodException e) {
				// another interface
			}
		}
		return on.getClass().getMethod(name);
	}
}

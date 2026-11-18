package io.github.asgerjon.unittas.probe;


import java.lang.reflect.Method;
import java.util.Collection;
import java.util.List;
import java.util.Optional;

/**
 * The 26.3 port (SPEC.md 12, 19.7 step 5): what this version gives the probe's version-free core. The probe is a Java
 * agent, needing no loader: its facts come from the game itself (its own version), and the loader beside it, if the
 * mod under test brought one, is said as that loader says itself (Fabric Loader, or NeoForge's or Forge's FML, read by
 * reflection: the probe depends on no loader's API). Its game operations are declared here and given their bodies by
 * the hooks (ModernHooks); one not declared is Unsupported.
 */
public final class ModernPort implements Port {

	private static final String FABRIC = "net.fabricmc.loader.api.FabricLoader";
	/**
	 * The FML loaders the probe knows (SPEC.md 19.7 steps 7 and 8): each one's name, its FMLLoader, its ModList, and the
	 * version info's method that says its version.
	 */
	private static final String[][] FMLS = {
		{"neoforge", "net.neoforged.fml.loading.FMLLoader", "net.neoforged.fml.ModList", "neoForgeVersion"},
		{"forge", "net.minecraftforge.fml.loading.FMLLoader", "net.minecraftforge.fml.ModList", "forgeVersion"},
	};

	@Override
	public String name() {
		return Version.port();
	}

	@Override
	public String minecraft() {
		return Version.minecraft();
	}

	@Override
	public String loaderName() {
		if (fabric().isPresent()) {
			return "fabric";
		}
		return fml().map(each -> each[0]).orElse("");
	}

	@Override
	public String loaderVersion() {
		if (fabric().isPresent()) {
			return fabricVersion("fabricloader");
		}
		return fml().map(ModernPort::fmlVersion).orElse("");
	}

	@Override
	public String names() {
		// mojang in 26.x (unobfuscated); else what the bridge's table of names says the game runs under
		return Members.namesKind();
	}

	@Override
	public boolean development() {
		return false;
	}

	@Override
	public String probeVersion() {
		// the probe's own jar's manifest, as the agent's build writes it
		String version = ModernPort.class.getPackage().getImplementationVersion();
		return version == null ? "" : version;
	}

	@Override
	public void beforeWake() {
	}

	@Override
	public void woken(Probe probe) {
		// the game's log as log events (PROTOCOL.md 7), as 1.7.10's ProbeLog
		ModernLog.attach(probe);
	}

	@Override
	public List<String> trace() {
		return ModernTrace.lines();
	}

	@Override
	public GameWorlds worlds() {
		return Version.worlds();
	}

	@Override
	public void declare(Probe probe) {
		// the client's own (step 3), given its body when Minecraft is made (ModernHooks.register)
		probe.register(Op.onSide("screen.get", Side.CLIENT).reading());
		// worlds (step 4; PROTOCOL.md 8.3), the core's bodies (WorldOps) on 26.3's calls (V26Worlds), bound there too
		probe.register(Op.probe("world.create"));
		probe.register(Op.probe("world.open"));
		probe.register(Op.probe("world.close"));
		probe.register(Op.onSide("world.get", Side.SERVER).reading());
		probe.register(Op.onSide("world.rules.set", Side.SERVER));
		probe.register(Op.onSide("world.time.set", Side.SERVER));
		probe.register(Op.onSide("world.weather.set", Side.SERVER));
		probe.register(Op.onSide("world.difficulty.set", Side.SERVER));
		probe.register(Op.onSide("world.prepare", Side.SERVER));
		// the game's things and the reset (step 5; PROTOCOL.md 8.4 to 8.9), 26.3's bodies (ModernThings, ModernReset)
		probe.register(Op.onSide("command.run", Side.SERVER));
		probe.register(Op.onSide("player.get", Side.SERVER, Side.CLIENT).reading());
		probe.register(Op.onSide("player.teleport", Side.SERVER));
		probe.register(Op.onSide("inventory.get", Side.SERVER, Side.CLIENT).reading());
		probe.register(Op.onSide("inventory.set", Side.SERVER));
		probe.register(Op.onSide("container.get", Side.CLIENT, Side.SERVER).reading());
		probe.register(Op.onSide("block.get", Side.SERVER, Side.CLIENT).reading());
		probe.register(Op.onSide("block.set", Side.SERVER));
		probe.register(Op.onSide("entity.list", Side.SERVER, Side.CLIENT).reading());
		probe.register(Op.onSide("entity.spawn", Side.SERVER));
		probe.register(Op.onSide("entity.get", Side.SERVER, Side.CLIENT).reading());
		probe.register(Op.onSide("entity.remove", Side.SERVER));
		probe.register(Op.onSide("screen.open", Side.CLIENT));
		probe.register(Op.onSide("screen.close", Side.CLIENT));
		probe.register(Op.onSide("hooks.run", Side.SERVER, Side.CLIENT).choosing(args -> {
			String hook = io.github.asgerjon.unittas.probe.link.Json.string(args, "hook");
			return "beforeRun".equals(hook) || "afterRun".equals(hook) ? Side.CLIENT : Side.SERVER;
		}));
		// input (SPEC.md 19.7 step 2; PROTOCOL.md 8.9), ModernInput's bodies
		probe.register(Op.onSide("player.look", Side.CLIENT));
		probe.register(Op.onSide("key.down", Side.CLIENT));
		probe.register(Op.onSide("key.up", Side.CLIENT));
		probe.register(Op.onSide("key.tap", Side.CLIENT));
		probe.register(Op.onSide("camera.set", Side.CLIENT));
		probe.register(Op.onSide("screen.type", Side.CLIENT));
		probe.register(Op.onSide("screen.key", Side.CLIENT));
		// the chat, sounds and pictures (19.7 step 2; PROTOCOL.md 8.6, 8.10, 8.11): ModernChat's, ModernSounds', ModernPictures'
		probe.register(Op.onSide("chat.read", Side.CLIENT).reading());
		probe.register(Op.onSide("chat.send", Side.CLIENT));
		probe.register(Op.onSide("sound.play", Side.CLIENT));
		probe.register(Op.onSide("screenshot", Side.CLIENT));
		// the agent's (19.7 step 3; PROTOCOL.md 8.4): ModernPerceive's
		probe.register(Op.onSide("player.perceive", Side.CLIENT).reading());
		probe.register(Op.onSide("block.ground", Side.SERVER, Side.CLIENT).reading());
		// the agent's verbs' parts (19.7 step 3b; PROTOCOL.md 8.5, 8.7): ModernVerbs'
		probe.register(Op.onSide("container.click", Side.CLIENT));
		probe.register(Op.onSide("block.items", Side.SERVER, Side.CLIENT).reading());
		// reflection (19.7 step 4; PROTOCOL.md 5.9): the core's Reflect with ModernReflect
		probe.register(Op.onSide("reflect.get", Side.SERVER, Side.CLIENT).reading().needingASide());
		probe.register(Op.onSide("reflect.set", Side.SERVER, Side.CLIENT).needingASide());
		// observing (19.7 step 3c; PROTOCOL.md 8.10): V26View's and V26Looks'
		probe.register(Op.onSide("view.block", Side.CLIENT));
		probe.register(Op.onSide("block.faces", Side.CLIENT).reading());
		probe.register(Op.onSide("texture.get", Side.CLIENT).reading());
		probe.register(Op.onSide("client.reset", Side.CLIENT));
		probe.register(Op.onSide("player.reset", Side.SERVER));
		probe.register(Op.onSide("world.reset", Side.SERVER));
	}

	/** Fabric Loader's own instance, when the mod under test brought it; empty in vanilla. */
	static Optional<Object> fabric() {
		try {
			Class<?> loader = Class.forName(FABRIC, true, ModernPort.class.getClassLoader());
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
				Class.forName(each[1], false, ModernPort.class.getClassLoader());
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
			Object info = versionInfo(Class.forName(fml[1], true, ModernPort.class.getClassLoader()));
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
		return fml().map(ModernPort::fmlMods).orElseGet(java.util.ArrayList::new);
	}

	/** Each mod an FML loader has (its ModList, as IModInfo says each), (id, name, version). */
	static java.util.List<String[]> fmlMods(String[] fml) {
		java.util.List<String[]> out = new java.util.ArrayList<>();
		try {
			Class<?> list = Class.forName(fml[2], true, ModernPort.class.getClassLoader());
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

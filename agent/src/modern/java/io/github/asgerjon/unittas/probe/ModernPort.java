package io.github.asgerjon.unittas.probe;


import java.util.List;

/**
 * The 26.3 port (SPEC.md 12, 19.7 step 5): what this version gives the probe's version-free core. The probe is a Java
 * agent, needing no loader: its facts come from the game itself (its own version), and the loader beside it, if the
 * mod under test brought one, is said as that loader says itself (Fabric Loader, or NeoForge's or Forge's FML, read by
 * reflection: the probe depends on no loader's API). Its game operations are declared here and given their bodies by
 * the hooks (ModernHooks); one not declared is Unsupported.
 */
public final class ModernPort implements Port {

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
		if (ModernLoaders.fabric().isPresent()) {
			return "fabric";
		}
		return ModernLoaders.fml().map(each -> each[0]).orElse("");
	}

	@Override
	public String loaderVersion() {
		if (ModernLoaders.fabric().isPresent()) {
			return ModernLoaders.fabricVersion("fabricloader");
		}
		return ModernLoaders.fml().map(ModernLoaders::fmlVersion).orElse("");
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
		// a dedicated server joined and left (PROTOCOL.md 9.3; SPEC.md 19.7 step 10c), ModernJoin's bodies
		probe.register(Op.probe("server.join"));
		probe.register(Op.probe("server.leave"));
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
}

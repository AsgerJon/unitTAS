package io.github.asgerjon.unittas.probe;

import net.fabricmc.loader.api.FabricLoader;
import net.fabricmc.loader.api.ModContainer;

import java.util.Collections;
import java.util.List;

/**
 * The 26.3 Fabric port (SPEC.md 12, D5): what this version and loader give the probe's version-free core. Its facts
 * come from Fabric Loader's own mod containers (Minecraft's, the loader's, the probe's), not from constants, so the
 * hello says what really runs. Its game operations come with phase 4's steps, each declared here and given its body
 * by the hooks (FabricHooks); one not declared yet is Unsupported.
 */
public final class FabricPort implements Port {

	@Override
	public String name() {
		return "26.3-fabric";
	}

	@Override
	public String minecraft() {
		return version("minecraft");
	}

	@Override
	public String loaderName() {
		return "fabric";
	}

	@Override
	public String loaderVersion() {
		return version("fabricloader");
	}

	@Override
	public String names() {
		// 26.x is unobfuscated: the game names its members as Mojang does
		return "mojang";
	}

	@Override
	public boolean development() {
		return FabricLoader.getInstance().isDevelopmentEnvironment();
	}

	@Override
	public String probeVersion() {
		return version("unittas");
	}

	@Override
	public void beforeWake() {
	}

	@Override
	public void woken(Probe probe) {
		// the game's log as log events (PROTOCOL.md 7), as 1.7.10's ProbeLog
		FabricLog.attach(probe);
	}

	@Override
	public List<String> trace() {
		return Collections.emptyList();
	}

	@Override
	public GameWorlds worlds() {
		return new FabricWorlds();
	}

	@Override
	public void declare(Probe probe) {
		// the client's own (step 3), given its body when Minecraft is made (FabricHooks.register)
		probe.register(Op.onSide("screen.get", Side.CLIENT).reading());
		// worlds (step 4; PROTOCOL.md 8.3), the core's bodies (WorldOps) on 26.3's calls (FabricWorlds), bound there too
		probe.register(Op.probe("world.create"));
		probe.register(Op.probe("world.open"));
		probe.register(Op.probe("world.close"));
		probe.register(Op.onSide("world.get", Side.SERVER).reading());
		probe.register(Op.onSide("world.rules.set", Side.SERVER));
		probe.register(Op.onSide("world.time.set", Side.SERVER));
		probe.register(Op.onSide("world.weather.set", Side.SERVER));
		probe.register(Op.onSide("world.difficulty.set", Side.SERVER));
		probe.register(Op.onSide("world.prepare", Side.SERVER));
		// the game's things and the reset (step 5; PROTOCOL.md 8.4 to 8.9), 26.3's bodies (FabricThings, FabricReset)
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
		// input (SPEC.md 19.7 step 2; PROTOCOL.md 8.9), FabricInput's bodies
		probe.register(Op.onSide("player.look", Side.CLIENT));
		probe.register(Op.onSide("key.down", Side.CLIENT));
		probe.register(Op.onSide("key.up", Side.CLIENT));
		probe.register(Op.onSide("key.tap", Side.CLIENT));
		probe.register(Op.onSide("camera.set", Side.CLIENT));
		probe.register(Op.onSide("screen.type", Side.CLIENT));
		probe.register(Op.onSide("screen.key", Side.CLIENT));
		// the chat, sounds and pictures (19.7 step 2; PROTOCOL.md 8.6, 8.10, 8.11): FabricChat's, FabricSounds', FabricPictures'
		probe.register(Op.onSide("chat.read", Side.CLIENT).reading());
		probe.register(Op.onSide("chat.send", Side.CLIENT));
		probe.register(Op.onSide("sound.play", Side.CLIENT));
		probe.register(Op.onSide("screenshot", Side.CLIENT));
		probe.register(Op.onSide("client.reset", Side.CLIENT));
		probe.register(Op.onSide("player.reset", Side.SERVER));
		probe.register(Op.onSide("world.reset", Side.SERVER));
	}

	/** A mod's version as Fabric Loader has it, or "" for one it hasn't. */
	private static String version(String mod) {
		return FabricLoader.getInstance().getModContainer(mod).map(ModContainer::getMetadata)
			.map(metadata -> metadata.getVersion().getFriendlyString()).orElse("");
	}
}

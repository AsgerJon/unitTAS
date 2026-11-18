package io.github.asgerjon.unittas.probe;

import java.util.Collections;
import java.util.List;

/**
 * A modern dedicated server's port (SPEC.md 19.7 step 10b): what this version gives the probe's version-free core
 * when the probe wakes in a dedicated server (its start file's role, server). No client class anywhere it reaches:
 * the server has none. Its facts as a client's port says them (VersionName, ModernLoaders); its operations the core's
 * and the server's own (declare).
 */
public final class ModernServerPort implements Port {

	@Override
	public String name() {
		return VersionName.port();
	}

	@Override
	public String minecraft() {
		return VersionName.minecraft();
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
		return Members.namesKind();
	}

	@Override
	public boolean development() {
		return false;
	}

	@Override
	public String probeVersion() {
		String version = ModernServerPort.class.getPackage().getImplementationVersion();
		return version == null ? "" : version;
	}

	@Override
	public void beforeWake() {
	}

	@Override
	public void woken(Probe probe) {
		// the server's log as log events (PROTOCOL.md 7), as a client's
		ModernLog.attach(probe);
	}

	@Override
	public List<String> trace() {
		return Collections.emptyList();
	}

	/** A dedicated server makes no world and opens none: its world is its folder's (server.properties). */
	@Override
	public GameWorlds worlds() {
		throw new IllegalStateException("a dedicated server makes and opens no world: its own is its folder's");
	}

	/**
	 * A dedicated server's operations (SPEC.md 19.7 step 10b), as 1.7.10's dedicated server has them, given their
	 * bodies as the server starts (ModernServerHooks.starting), the same bodies as a client's integrated server's: the
	 * world's server half (no world made, opened or closed; no difficulty, which a client's option shares: the server's
	 * is its server.properties'), console commands, the players by name, the reset's server parts, the server's hooks,
	 * reflection. No hooks.things: no modern probe has plugins yet, and its absence declares nothing (PROTOCOL.md 8.13).
	 */
	@Override
	public void declare(Probe probe) {
		probe.register(Op.onSide("world.get", Side.SERVER).reading());
		probe.register(Op.onSide("world.rules.set", Side.SERVER));
		probe.register(Op.onSide("world.time.set", Side.SERVER));
		probe.register(Op.onSide("world.weather.set", Side.SERVER));
		probe.register(Op.onSide("world.prepare", Side.SERVER));
		probe.register(Op.onSide("command.run", Side.SERVER));
		probe.register(Op.onSide("players.list", Side.SERVER).reading());
		probe.register(Op.onSide("player.get", Side.SERVER).reading());
		probe.register(Op.onSide("player.kick", Side.SERVER));
		probe.register(Op.onSide("player.reset", Side.SERVER));
		probe.register(Op.onSide("world.reset", Side.SERVER));
		probe.register(Op.onSide("hooks.run", Side.SERVER));
		probe.register(Op.onSide("reflect.get", Side.SERVER).reading().needingASide());
		probe.register(Op.onSide("reflect.set", Side.SERVER).needingASide());
	}
}

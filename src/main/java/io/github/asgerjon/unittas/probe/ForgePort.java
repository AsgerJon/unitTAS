package io.github.asgerjon.unittas.probe;

import io.github.asgerjon.unittas.TasTrace;
import io.github.asgerjon.unittas.UnitTasMod;
import io.github.asgerjon.unittas.UnitTasMode;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraftforge.common.ForgeVersion;

import java.util.List;

/**
 * The 1.7.10 Forge port (SPEC.md 12, D5): what this version and loader give the probe's version-free core. Its
 * operations are declared here and given their bodies at preInit (ClientOps, ServerOps and the rest); its hooks are
 * ClientHooks and ServerHooks.
 */
public final class ForgePort implements Port {

	private final boolean obfuscated;

	/** 'obfuscated': a real client (Searge names), not a development run (MCP names), as FML's coremod data says. */
	public ForgePort(boolean obfuscated) {
		this.obfuscated = obfuscated;
	}

	@Override
	public String name() {
		return "1.7.10-forge";
	}

	@Override
	public String minecraft() {
		return "1.7.10";
	}

	@Override
	public String loaderName() {
		return "forge";
	}

	@Override
	public String loaderVersion() {
		return ForgeVersion.majorVersion + "." + ForgeVersion.minorVersion + "." + ForgeVersion.revisionVersion + "."
			+ ForgeVersion.buildVersion;
	}

	@Override
	public String names() {
		// a real 1.7.10 client names Minecraft's members by Searge; a development run by MCP
		return obfuscated ? "srg" : "mcp";
	}

	@Override
	public boolean development() {
		return !obfuscated;
	}

	@Override
	public String probeVersion() {
		return UnitTasMod.VERSION;
	}

	@Override
	public void beforeWake() {
		UnitTasMode.running = true;
	}

	@Override
	public void woken(Probe probe) {
		ProbeLog.attach(probe);
	}

	@Override
	public List<String> trace() {
		return TasTrace.lines();
	}

	@Override
	public void declare(Probe probe) {
		// the server drops its next connections as 1.7.10's login race does: the opening guard's tests on a client (its
		// integrated server's), the join guard's on a dedicated server (MixinNetworkSystemDrop)
		probe.register(Op.probe("debug.drop_login").does(call -> {
			long logins = call.number("logins", 1, 0, 10);
			Opening.DROP_LOGINS.set((int) logins);
			return Json.object("logins", logins);
		}));
		if (probe.dedicated()) {
			// a dedicated server's, given their bodies at its preInit (ServerOps)
			probe.register(Op.onSide("world.get", Side.SERVER).reading());
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
			return;
		}
		// a dedicated server joined and left (9.3), given their bodies at preInit (JoinOps)
		probe.register(Op.probe("server.join"));
		probe.register(Op.probe("server.leave"));
		// today's Java runner (8.14), given its body at preInit (JavaOps)
		probe.register(Op.probe("java.run"));
		// worlds (8.3), given their bodies at preInit (WorldOps)
		probe.register(Op.probe("world.create"));
		probe.register(Op.probe("world.open"));
		probe.register(Op.probe("world.close"));
		probe.register(Op.onSide("world.get", Side.SERVER).reading());
		probe.register(Op.onSide("world.rules.set", Side.SERVER));
		probe.register(Op.onSide("world.time.set", Side.SERVER));
		probe.register(Op.onSide("world.weather.set", Side.SERVER));
		probe.register(Op.onSide("world.difficulty.set", Side.SERVER));
		probe.register(Op.onSide("world.prepare", Side.SERVER));
		// the player, the inventory, containers, commands, entities, screens, the mods' hooks (8.1, 8.4 to 8.9), given
		// their bodies at preInit (GameOps)
		probe.register(Op.onSide("command.run", Side.SERVER));
		probe.register(Op.onSide("player.get", Side.SERVER, Side.CLIENT).reading());
		probe.register(Op.onSide("player.teleport", Side.SERVER));
		probe.register(Op.onSide("inventory.get", Side.SERVER, Side.CLIENT).reading());
		probe.register(Op.onSide("container.get", Side.CLIENT, Side.SERVER).reading());
		probe.register(Op.onSide("entity.list", Side.SERVER, Side.CLIENT).reading());
		probe.register(Op.onSide("screen.open", Side.CLIENT));
		probe.register(Op.onSide("screen.close", Side.CLIENT));
		probe.register(Op.onSide("hooks.run", Side.SERVER, Side.CLIENT).choosing(args -> {
			String hook = Json.string(args, "hook");
			return "beforeRun".equals(hook) || "afterRun".equals(hook) ? Side.CLIENT : Side.SERVER;
		}));
		// the reset (8.4, 9.5), given its bodies at preInit (ResetOps)
		probe.register(Op.onSide("client.reset", Side.CLIENT));
		probe.register(Op.onSide("player.reset", Side.SERVER));
		probe.register(Op.onSide("world.reset", Side.SERVER));
		// the game's things (8.4 to 8.10), given their bodies at preInit (ThingOps)
		probe.register(Op.onSide("player.look", Side.CLIENT));
		probe.register(Op.onSide("inventory.set", Side.SERVER));
		probe.register(Op.onSide("block.get", Side.SERVER, Side.CLIENT).reading());
		probe.register(Op.onSide("block.set", Side.SERVER));
		probe.register(Op.onSide("entity.spawn", Side.SERVER));
		probe.register(Op.onSide("entity.get", Side.SERVER, Side.CLIENT).reading());
		probe.register(Op.onSide("entity.remove", Side.SERVER));
		probe.register(Op.onSide("key.down", Side.CLIENT));
		probe.register(Op.onSide("key.up", Side.CLIENT));
		probe.register(Op.onSide("key.tap", Side.CLIENT));
		probe.register(Op.onSide("screen.type", Side.CLIENT));
		probe.register(Op.onSide("screen.key", Side.CLIENT));
		probe.register(Op.onSide("chat.read", Side.CLIENT).reading());
		probe.register(Op.onSide("chat.send", Side.CLIENT));
		probe.register(Op.onSide("camera.set", Side.CLIENT));
		probe.register(Op.onSide("sound.play", Side.CLIENT));
		probe.register(Op.onSide("screenshot", Side.CLIENT));
		// reflection (8.11), given its bodies at preInit (ThingOps); the refs are the probe's own (declareRefs)
		probe.register(Op.onSide("reflect.get", Side.SERVER, Side.CLIENT).reading().needingASide());
		probe.register(Op.onSide("reflect.set", Side.SERVER, Side.CLIENT).needingASide());
		// the client's own, given their bodies at preInit (ClientOps)
		probe.register(Op.onSide("screen.get", Side.CLIENT).reading());
	}
}

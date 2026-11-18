package io.github.asgerjon.unittas.probe;

import java.io.File;
import java.util.Set;
import java.util.function.BiFunction;
import java.util.function.Function;
import net.minecraft.CrashReport;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;

/**
 * The probe as the agent's server hooks reach it (SPEC.md 19.7 step 10b): in a modern dedicated server, its start
 * file's role server, the agent reading the version's server hooks file. As ModernEntry is a client's, but with no
 * client class: a dedicated server has none. start() is given the server's folder, the pass mark, the hooked classes
 * and those rewritten so far, and the names' lookup, and answers with this BiFunction, which each hook calls with its
 * name and [the hooked class, the instance, the arguments].
 */
public final class ModernServerEntry implements BiFunction<String, Object[], Object> {

	private static volatile Object pass;
	private static volatile Set<String> hooked = Set.of();
	private static volatile Set<String> rewritten = Set.of();

	private ModernServerEntry() {
	}

	/** Called by the agent's bridge, once, in the server's own class loader's child. */
	public static BiFunction<String, Object[], Object> start(File game, Object passMark, Set<String> hookedClasses,
		Set<String> rewrittenClasses, Function<String, String> names) throws ClassNotFoundException {
		pass = passMark;
		Members.names = names;
		hooked = hookedClasses;
		rewritten = rewrittenClasses;
		Probe.early(game, new ModernServerPort());
		ClassLoader gameLoader = MinecraftServer.class.getClassLoader();
		for (String each : hookedClasses) {
			Class.forName(each.replace('/', '.'), false, gameLoader);
		}
		return new ModernServerEntry();
	}

	/** The classes the agent hooks, by their internal names. */
	static Set<String> hooked() {
		return hooked;
	}

	/** The hooked classes the agent has rewritten so far. */
	static Set<String> rewritten() {
		return rewritten;
	}

	/** A hook: its name, and [the hooked class, the instance or null, the method's arguments]. */
	@Override
	public Object apply(String hook, Object[] call) {
		Object self = call[1];
		switch (hook) {
			case "server.starting":
				ModernServerHooks.starting((MinecraftServer) self);
				return pass;
			case "server.tick.start":
				ModernServerHooks.tickStart();
				return pass;
			case "server.tick.end":
				ModernServerHooks.tickEnd((MinecraftServer) self);
				return pass;
			case "crash.saved":
				ModernCrash.saved((CrashReport) self);
				return pass;
			case "command.heard":
				// a player's or the console's system message: a line of command.run's, if it runs for that source
				ModernThings.heard(self, (Component) call[2], call.length > 3 && (Boolean) call[3]);
				return pass;
			case "player.joined":
				// placeNewPlayer(connection, player, ...): the player its second argument
				ModernServerHooks.joined((ServerPlayer) call[3]);
				return pass;
			case "player.left":
				ModernServerHooks.left((ServerPlayer) call[2]);
				return pass;
			default:
				throw new IllegalStateException("a dedicated server's probe has no hook " + hook);
		}
	}
}

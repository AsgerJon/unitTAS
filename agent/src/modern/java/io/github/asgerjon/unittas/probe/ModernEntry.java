package io.github.asgerjon.unittas.probe;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.resources.sounds.SoundInstance;
import net.minecraft.client.sounds.SoundManager;
import net.minecraft.network.chat.Component;

import java.io.File;
import java.util.Set;
import java.util.function.BiFunction;
import java.util.function.Function;

/**
 * The probe as the agent's hooks reach it (SPEC.md 19.7 steps 5 and 6c), for every version from 1.20.1 on: each hook by
 * its name (the version's hooks file), as the 26.3 Fabric probe's mixins were; where a hook's arguments differ by
 * version, Version reads them. The agent and the probe speak in JDK types only (the agent's jar may be hidden from
 * the game's loader, and so from the probe's): start() is given the game's folder, the pass mark (a BEFORE hook's
 * "go on"), the hooked classes and those rewritten so far, and answers with this BiFunction, which each hook calls
 * with its name and [the hooked class, the instance, the arguments]. start() wakes the probe at the game's first hook
 * (its start file read, as the 1.7.10 probe's coremod and the Fabric probe's preLaunch did), and loads every hooked
 * class at once, so the agent rewrites them all before the probe says it is ready.
 */
public final class ModernEntry implements BiFunction<String, Object[], Object> {

	private static volatile Object pass;
	private static volatile Set<String> hooked = Set.of();
	private static volatile Set<String> rewritten = Set.of();

	private ModernEntry() {
	}

	/** Called by the agent's bridge, once, in the game's own class loader's child. */
	public static BiFunction<String, Object[], Object> start(File game, Object passMark, Set<String> hookedClasses,
		Set<String> rewrittenClasses, Function<String, String> names) throws ClassNotFoundException {
		pass = passMark;
		// the names' lookup where the game runs under other names than Mojang's (before 26.1); none where it doesn't
		Members.names = names;
		hooked = hookedClasses;
		rewritten = rewrittenClasses;
		Probe.early(game, new ModernPort());
		ClassLoader gameLoader = Minecraft.class.getClassLoader();
		for (String each : hookedClasses) {
			Class.forName(each.replace('/', '.'), false, gameLoader);
		}
		return new ModernEntry();
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
		Object[] arguments = java.util.Arrays.copyOfRange(call, 2, call.length);
		switch (hook) {
			// before a method: the pass mark goes on with it; anything else ends it, as its value
			case "minecraft.made":
				launched((Minecraft) self);
				return pass;
			case "client.tick.start":
				ModernHooks.clientTickStart();
				return pass;
			case "window.title": {
				String title = ModernHooks.title();
				return title == null ? pass : title;
			}
			case "screen.set":
				// the screen before the change is the one the game shows: on Gui in 26.3, on Minecraft before it
				ModernHooks.screen(Version.screen(), (Screen) arguments[0]);
				return pass;
			case "server.tick.start":
				ModernHooks.serverTickStart();
				return pass;
			case "chat.line":
				ModernChat.heard((Component) arguments[0], Version.chatKind(arguments));
				return pass;
			case "command.heard":
				// a player's or the server's system message: a line of command.run's, if it runs for that source
				ModernThings.heard(self, (Component) arguments[0], arguments.length > 1 && (Boolean) arguments[1]);
				return pass;
			case "sound.play":
				ModernSounds.heard((SoundManager) self, (SoundInstance) arguments[0]);
				return pass;
			case "real.input":
				// the real keyboard and mouse dropped, the pointer never grabbed, while the probe is awake (PROTOCOL.md 2.5)
				return ModernHooks.awake() ? Boolean.TRUE : pass;
			case "mouse.grabbed": {
				// the mouse counted as grabbed while a world is open and no screen is: holding attack to mine needs it
				Minecraft mc = Minecraft.getInstance();
				return ModernHooks.awake() && mc.level != null && Version.screen() == null ? Boolean.TRUE : pass;
			}
			// after a method: its value is dropped
			case "client.tick.end":
				ModernHooks.clientTickEnd((Minecraft) self);
				return pass;
			case "server.tick.end":
				ModernHooks.serverTickEnd();
				return pass;
			case "crash.saved":
				ModernCrash.saved((net.minecraft.CrashReport) self);
				return pass;
			default:
				// a hook of the version's own (1.21.1's view keeps its frames and builds by hooks): its Version's
				return Version.hook(hook, self, arguments, pass);
		}
	}

	/**
	 * Minecraft is made (its run is starting, which Main calls right after constructing it): the probe is given the
	 * game's own way out (Minecraft.stop, which the Quit button calls), then it dials, as the 1.7.10 probe does from
	 * its MixinMinecraft. A quit asked for before there is a game to quit
	 * happens as soon as there is.
	 */
	private static void launched(Minecraft minecraft) {
		Probe probe = Probe.get();
		if (probe != null) {
			ModernHooks.register(probe);
			probe.leaveBy(minecraft::stop);
		}
		Probe.launched(null);
	}
}

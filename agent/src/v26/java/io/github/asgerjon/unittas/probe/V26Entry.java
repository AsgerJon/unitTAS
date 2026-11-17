package io.github.asgerjon.unittas.probe;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Gui;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.multiplayer.chat.GuiMessageSource;
import net.minecraft.client.resources.sounds.SoundInstance;
import net.minecraft.client.sounds.SoundManager;
import net.minecraft.network.chat.Component;

import java.io.File;
import java.util.Set;
import java.util.function.BiFunction;

/**
 * The probe as the agent's hooks reach it (SPEC.md 19.7 step 5): each hook by its name (the agent's Hooks), as the
 * 26.3 Fabric probe's mixins were. The agent and the probe speak in JDK types only (the agent's jar may be hidden from
 * the game's loader, and so from the probe's): start() is given the game's folder, the pass mark (a BEFORE hook's
 * "go on"), the hooked classes and those rewritten so far, and answers with this BiFunction, which each hook calls
 * with its name and [the hooked class, the instance, the arguments]. start() wakes the probe at the game's first hook
 * (its start file read, as the 1.7.10 probe's coremod and the Fabric probe's preLaunch did), and loads every hooked
 * class at once, so the agent rewrites them all before the probe says it is ready.
 */
public final class V26Entry implements BiFunction<String, Object[], Object> {

	private static volatile Object pass;
	private static volatile Set<String> hooked = Set.of();
	private static volatile Set<String> rewritten = Set.of();

	private V26Entry() {
	}

	/** Called by the agent's bridge, once, in the game's own class loader's child. */
	public static BiFunction<String, Object[], Object> start(File game, Object passMark, Set<String> hookedClasses,
		Set<String> rewrittenClasses) throws ClassNotFoundException {
		pass = passMark;
		hooked = hookedClasses;
		rewritten = rewrittenClasses;
		Probe.early(game, new V26Port());
		ClassLoader gameLoader = Minecraft.class.getClassLoader();
		for (String each : hookedClasses) {
			Class.forName(each.replace('/', '.'), false, gameLoader);
		}
		return new V26Entry();
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
				V26Hooks.clientTickStart();
				return pass;
			case "window.title": {
				String title = V26Hooks.title();
				return title == null ? pass : title;
			}
			case "screen.set":
				V26Hooks.screen(((Gui) self).screen(), (Screen) arguments[0]);
				return pass;
			case "server.tick.start":
				V26Hooks.serverTickStart();
				return pass;
			case "chat.line":
				V26Chat.heard((Component) arguments[0], (GuiMessageSource) arguments[2]);
				return pass;
			case "sound.play":
				V26Sounds.heard((SoundManager) self, (SoundInstance) arguments[0]);
				return pass;
			case "real.input":
				// the real keyboard and mouse dropped, the pointer never grabbed, while the probe is awake (PROTOCOL.md 2.5)
				return V26Hooks.awake() ? Boolean.TRUE : pass;
			case "mouse.grabbed": {
				// the mouse counted as grabbed while a world is open and no screen is: holding attack to mine needs it
				Minecraft mc = Minecraft.getInstance();
				return V26Hooks.awake() && mc.level != null && mc.gui.screen() == null ? Boolean.TRUE : pass;
			}
			// after a method: its value is dropped
			case "client.tick.end":
				V26Hooks.clientTickEnd((Minecraft) self);
				return pass;
			case "server.tick.end":
				V26Hooks.serverTickEnd();
				return pass;
			default:
				throw new IllegalArgumentException("the probe knows no hook " + hook);
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
			V26Hooks.register(probe);
			probe.leaveBy(minecraft::stop);
		}
		Probe.launched(null);
	}
}

package io.github.asgerjon.unittas.probe;

import io.github.asgerjon.unittas.agent.Bridge;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Gui;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.multiplayer.chat.GuiMessageSource;
import net.minecraft.client.resources.sounds.SoundInstance;
import net.minecraft.client.sounds.SoundManager;
import net.minecraft.network.chat.Component;

import java.io.File;

/**
 * The probe as the agent's hooks reach it (SPEC.md 19.7 step 5): each hook by its name (the agent's Hooks), as the
 * 26.3 Fabric probe's mixins were. start() wakes the probe at the game's first hook (its start file read, as the 1.7.10
 * probe's coremod and the Fabric probe's preLaunch did), and loads every hooked class at once, so the agent rewrites
 * them all before the probe says it is ready.
 */
public final class V26Entry implements Bridge.Handler {

	private V26Entry() {
	}

	/** Called by the agent's Bridge, once, in the game's own class loader's child. */
	public static Bridge.Handler start(File game) throws ClassNotFoundException {
		Probe.early(game, new V26Port());
		ClassLoader gameLoader = Minecraft.class.getClassLoader();
		for (String hooked : Bridge.hookedClasses()) {
			Class.forName(hooked.replace('/', '.'), false, gameLoader);
		}
		return new V26Entry();
	}

	@Override
	public Object before(String hook, Object self, Object[] arguments) {
		switch (hook) {
			case "client.tick.start":
				V26Hooks.clientTickStart();
				return Bridge.PASS;
			case "window.title": {
				String title = V26Hooks.title();
				return title == null ? Bridge.PASS : title;
			}
			case "screen.set":
				V26Hooks.screen(((Gui) self).screen(), (Screen) arguments[0]);
				return Bridge.PASS;
			case "server.tick.start":
				V26Hooks.serverTickStart();
				return Bridge.PASS;
			case "chat.line":
				V26Chat.heard((Component) arguments[0], (GuiMessageSource) arguments[2]);
				return Bridge.PASS;
			case "sound.play":
				V26Sounds.heard((SoundManager) self, (SoundInstance) arguments[0]);
				return Bridge.PASS;
			case "real.input":
				// the real keyboard and mouse dropped, the pointer never grabbed, while the probe is awake (PROTOCOL.md 2.5)
				return V26Hooks.awake() ? Boolean.TRUE : Bridge.PASS;
			case "mouse.grabbed": {
				// the mouse counted as grabbed while a world is open and no screen is: holding attack to mine needs it
				Minecraft mc = Minecraft.getInstance();
				return V26Hooks.awake() && mc.level != null && mc.gui.screen() == null ? Boolean.TRUE : Bridge.PASS;
			}
			default:
				throw new IllegalArgumentException("the probe knows no hook " + hook + " before a method");
		}
	}

	@Override
	public void after(String hook, Object self, Object[] arguments) {
		switch (hook) {
			case "minecraft.made":
				launched((Minecraft) self);
				break;
			case "client.tick.end":
				V26Hooks.clientTickEnd((Minecraft) self);
				break;
			case "server.tick.end":
				V26Hooks.serverTickEnd();
				break;
			default:
				throw new IllegalArgumentException("the probe knows no hook " + hook + " after a method");
		}
	}

	/**
	 * Minecraft is made: the probe is given the game's own way out (Minecraft.stop, which the Quit button calls), then
	 * it dials, as the 1.7.10 probe does from its MixinMinecraft. A quit asked for before there is a game to quit
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

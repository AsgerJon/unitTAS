package io.github.asgerjon.unittas.probe;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiScreen;
import net.minecraft.client.settings.KeyBinding;
import org.lwjgl.input.Keyboard;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

/**
 * The tests' input in 1.7.10 (PROTOCOL.md 8.9), on the client thread: looking, the key bindings held and let go, the
 * camera, keys typed into a screen. The probe's operations and the Java front end's helpers both use these.
 */
public final class Input {

	private Input() {
	}

	/** Turns the client player to look this way (degrees; yaw 0 is south, pitch 90 down), this tick and the last. */
	public static void look(Minecraft mc, float yaw, float pitch) {
		mc.thePlayer.rotationYaw = yaw;
		mc.thePlayer.rotationPitch = pitch;
		mc.thePlayer.prevRotationYaw = yaw;
		mc.thePlayer.prevRotationPitch = pitch;
	}

	/** A key binding's code by its id ("key.jump", a mod's own), or null when the game has no such binding. */
	public static Integer bindingCode(Minecraft mc, String id) {
		for (KeyBinding binding : mc.gameSettings.keyBindings) {
			if (binding.getKeyDescription().equals(id)) {
				return binding.getKeyCode();
			}
		}
		return null;
	}

	/** Puts the key down, as pressing it does: held, and pressed once. */
	public static void down(int code) {
		KeyBinding.setKeyBindState(code, true);
		KeyBinding.onTick(code);
	}

	public static void up(int code) {
		KeyBinding.setKeyBindState(code, false);
	}

	/** The camera: 0 first person, 1 third person from behind, 2 from the front. */
	public static void camera(Minecraft mc, int view) {
		mc.gameSettings.thirdPersonView = view;
	}

	/**
	 * Sends GuiScreen.keyTyped to the screen (dev names first, then the obfuscated ones). What the screen throws comes
	 * out as itself: it is the screen's failure, not unitTAS's.
	 */
	public static void keyTyped(GuiScreen screen, char character, int keyCode) {
		Method keyTyped;
		try {
			try {
				keyTyped = GuiScreen.class.getDeclaredMethod("keyTyped", char.class, int.class);
			} catch (NoSuchMethodException e) {
				keyTyped = GuiScreen.class.getDeclaredMethod("func_73869_a", char.class, int.class);
			}
			keyTyped.setAccessible(true);
		} catch (ReflectiveOperationException e) {
			throw new IllegalStateException("Can't find GuiScreen.keyTyped to type into " + screen, e);
		}
		try {
			keyTyped.invoke(screen, character, keyCode);
		} catch (InvocationTargetException e) {
			Throwable thrown = e.getCause();
			if (thrown instanceof RuntimeException) {
				throw (RuntimeException) thrown;
			}
			if (thrown instanceof Error) {
				throw (Error) thrown;
			}
			throw new IllegalStateException(screen.getClass().getName() + ".keyTyped threw", thrown);
		} catch (IllegalAccessException e) {
			throw new IllegalStateException("Can't type into " + screen, e);
		}
	}

	/**
	 * A portable key's LWJGL 2 code and the character it types (PROTOCOL.md 5.8), or null for a name that is none:
	 * letters, digits, space, enter, escape, tab, backspace, delete, the arrows, home, end, page_up, page_down, f1-f12.
	 */
	public static int[] portableKey(String name) {
		if (name.length() == 1 && Character.isLetterOrDigit(name.charAt(0))) {
			int code = Keyboard.getKeyIndex(name.toUpperCase(java.util.Locale.ROOT));
			return code == Keyboard.KEY_NONE ? null : new int[]{code, name.charAt(0)};
		}
		switch (name) {
			case "space":
				return new int[]{Keyboard.KEY_SPACE, ' '};
			case "enter":
				return new int[]{Keyboard.KEY_RETURN, '\r'};
			case "escape":
				return new int[]{Keyboard.KEY_ESCAPE, 0};
			case "tab":
				return new int[]{Keyboard.KEY_TAB, 0};
			case "backspace":
				return new int[]{Keyboard.KEY_BACK, 0};
			case "delete":
				return new int[]{Keyboard.KEY_DELETE, 0};
			case "up":
				return new int[]{Keyboard.KEY_UP, 0};
			case "down":
				return new int[]{Keyboard.KEY_DOWN, 0};
			case "left":
				return new int[]{Keyboard.KEY_LEFT, 0};
			case "right":
				return new int[]{Keyboard.KEY_RIGHT, 0};
			case "home":
				return new int[]{Keyboard.KEY_HOME, 0};
			case "end":
				return new int[]{Keyboard.KEY_END, 0};
			case "page_up":
				return new int[]{Keyboard.KEY_PRIOR, 0};
			case "page_down":
				return new int[]{Keyboard.KEY_NEXT, 0};
			default:
				if (name.matches("f([1-9]|1[0-2])")) {
					int code = Keyboard.getKeyIndex(name.toUpperCase(java.util.Locale.ROOT));
					return code == Keyboard.KEY_NONE ? null : new int[]{code, 0};
				}
				return null;
		}
	}
}

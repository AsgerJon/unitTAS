package io.github.asgerjon.unittas.probe;

import net.minecraft.client.Minecraft;
import org.lwjgl.input.Keyboard;
import org.lwjgl.input.Mouse;

/** The window's part of a run (PROTOCOL.md 2.5), shared by the probe and the Java runner. */
public final class Window {

	private Window() {
	}

	/**
	 * The tests are the only input: the real mouse and keyboard events go before the game reads them (call it at the
	 * start of the client tick, ahead of the screens and the game), so the window works without focus and a stray click
	 * doesn't disturb a test. The game counts as focused while no screen is open, as holding a key to mine needs.
	 */
	public static void ignoreRealInput(Minecraft mc) {
		while (Mouse.next()) {
			// dropped
		}
		while (Keyboard.next()) {
			// dropped
		}
		if (mc.theWorld != null && mc.currentScreen == null) {
			mc.inGameHasFocus = true;
		}
	}
}

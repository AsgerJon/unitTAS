package io.github.asgerjon.unittas.probe;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiNewChat;
import net.minecraft.util.ScreenShotHelper;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.List;

/** Pictures of the window (PROTOCOL.md 8.10), on the client thread. The probe and the Java front end both use these. */
public final class Pictures {

	private Pictures() {
	}

	/**
	 * Empties the chat's lines from the screen. Not clearChatMessages: a mod may cancel that one (to keep the chat
	 * between worlds, say).
	 */
	@SuppressWarnings("rawtypes")
	public static void clearChat(Minecraft mc) {
		GuiNewChat chat = mc.ingameGUI.getChatGUI();
		for (String[] names : new String[][]{{"chatLines", "field_146252_h"}, {"field_146253_i"}}) {
			for (String name : names) {
				try {
					java.lang.reflect.Field field = GuiNewChat.class.getDeclaredField(name);
					field.setAccessible(true);
					((List) field.get(chat)).clear();
					break;
				} catch (ReflectiveOperationException e) {
					// the other name, in an obfuscated game
				}
			}
		}
	}

	/**
	 * What the window shows now, as a PNG: in {@code folder}'s screenshots/ as {@code name}, the way the game's own F2
	 * does it (ScreenShotHelper reads the frame the game drew).
	 */
	public static void save(Minecraft mc, File folder, String name) {
		ScreenShotHelper.saveScreenshot(folder, name, mc.displayWidth, mc.displayHeight, mc.getFramebuffer());
	}

	/** The same, to exactly the file asked for: saved where the game saves it, then moved there. */
	public static void saveAs(Minecraft mc, File file) throws IOException {
		File folder = Files.createTempDirectory("unittas-picture").toFile();
		try {
			save(mc, folder, "picture.png");
			File made = new File(folder, "screenshots/picture.png");
			if (!made.isFile()) {
				throw new IOException("the game saved no picture (" + made + ")");
			}
			File parent = file.getAbsoluteFile().getParentFile();
			if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
				throw new IOException("can't make " + parent);
			}
			Files.move(made.toPath(), file.toPath(), StandardCopyOption.REPLACE_EXISTING);
		} finally {
			File shots = new File(folder, "screenshots");
			if (shots.isDirectory()) {
				Files.deleteIfExists(shots.toPath());
			}
			Files.deleteIfExists(folder.toPath());
		}
	}
}

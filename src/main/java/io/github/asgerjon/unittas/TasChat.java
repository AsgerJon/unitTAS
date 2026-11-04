package io.github.asgerjon.unittas;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiChat;
import net.minecraft.client.gui.GuiScreen;
import net.minecraft.client.gui.GuiTextField;
import org.lwjgl.input.Keyboard;

import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * The chat screen as a test typed into it: what it shows, more keys, and Enter. It reads 1.7.10's own chat screen; a
 * mod with a chat of its own answers through its {@link TasHooks} (chatText, chatSuggestions, chatUsage).
 */
public final class TasChat {

	/** Ticks after a key before the screen is read: suggestions for 1.7.10's commands come from the server. */
	private static final int SETTLE_TICKS = 4;

	private final TasGame game;

	TasChat(TasGame game) {
		this.game = game;
	}

	/** Types more, key by key. */
	public TasChat typeMore(String text) {
		game.client(() -> {
			GuiScreen screen = openChat();
			for (char character : text.toCharArray()) {
				TasTestCase.keyTyped(screen, character, 0);
			}
			return null;
		});
		game.clientTicks(SETTLE_TICKS);
		return this;
	}

	/** Presses a key such as Keyboard.KEY_TAB, KEY_UP, KEY_BACK. */
	public TasChat key(int keyCode) {
		game.client(() -> {
			TasTestCase.keyTyped(openChat(), '\0', keyCode);
			return null;
		});
		game.clientTicks(SETTLE_TICKS);
		return this;
	}

	/** The text in the input. */
	public String text() {
		return game.client(() -> {
			GuiScreen screen = openChat();
			String text = TasPlugins.first(hooks -> hooks.chatText(screen));
			return text != null ? text : ((GuiTextField) chatField(GuiTextField.class)).getText();
		});
	}

	/**
	 * The suggestion list as shown. In 1.7.10's own chat: the completions the server sent for the last Tab (press
	 * key(Keyboard.KEY_TAB) first), empty before any.
	 */
	public List<String> suggestions() {
		return game.client(() -> {
			GuiScreen screen = openChat();
			List<String> shown = TasPlugins.first(hooks -> hooks.chatSuggestions(screen));
			if (shown != null) {
				return new ArrayList<>(shown);
			}
			List<String> completions = new ArrayList<>();
			for (Object completion : (List<?>) chatField(List.class)) {
				completions.add(String.valueOf(completion));
			}
			return completions;
		});
	}

	/** The grey usage or the red error above the input; 1.7.10's own chat shows none, so it is empty there. */
	public List<String> usage() {
		return game.client(() -> {
			GuiScreen screen = openChat();
			List<String> usage = TasPlugins.first(hooks -> hooks.chatUsage(screen));
			return usage == null ? Collections.<String>emptyList() : new ArrayList<>(usage);
		});
	}

	/** Presses Enter: the chat sends the text and closes; returns what came back. */
	public TasCommand enter() {
		String text = text();
		int mark = game.chatMark();
		game.client(() -> {
			TasTestCase.keyTyped(openChat(), '\r', Keyboard.KEY_RETURN);
			return null;
		});
		game.clientTicks(SETTLE_TICKS);
		return new TasCommand(text, -1, game.chatSince(mark));
	}

	public void close() {
		game.client(() -> {
			if (Minecraft.getMinecraft().currentScreen instanceof GuiChat) {
				Minecraft.getMinecraft().displayGuiScreen(null);
			}
			return null;
		});
	}

	private static GuiScreen openChat() {
		GuiScreen screen = Minecraft.getMinecraft().currentScreen;
		if (!(screen instanceof GuiChat)) {
			throw new AssertionError("the chat isn't open (the screen is " + (screen == null ? "the game" : screen.getClass().getSimpleName()) + ")");
		}
		return screen;
	}

	/**
	 * 1.7.10's GuiChat field of that type, by its type rather than its name (the same in a dev and an obfuscated game):
	 * the input is its one GuiTextField, the completions from the server its one List.
	 */
	private static Object chatField(Class<?> type) {
		GuiScreen screen = openChat();
		for (Field field : GuiChat.class.getDeclaredFields()) {
			if (!Modifier.isStatic(field.getModifiers()) && type.isAssignableFrom(field.getType())) {
				try {
					field.setAccessible(true);
					return field.get(screen);
				} catch (IllegalAccessException e) {
					throw new IllegalStateException("Can't read GuiChat's " + type.getSimpleName(), e);
				}
			}
		}
		throw new IllegalStateException("GuiChat has no " + type.getSimpleName() + " field");
	}
}

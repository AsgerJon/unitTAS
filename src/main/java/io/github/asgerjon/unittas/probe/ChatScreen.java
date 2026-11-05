package io.github.asgerjon.unittas.probe;

import io.github.asgerjon.unittas.TasPlugins;
import net.minecraft.client.gui.GuiChat;
import net.minecraft.client.gui.GuiScreen;
import net.minecraft.client.gui.GuiTextField;

import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * The chat screen as it shows (PROTOCOL.md 8.6, chat.read), on the client thread: the input, the suggestions, the
 * usage line. 1.7.10's own GuiChat is read by its fields' types (the same in a dev game and an obfuscated one); a mod
 * with a chat of its own answers through its TasHooks (chatText, chatSuggestions, chatUsage). The probe and TasChat both
 * read it here.
 */
public final class ChatScreen {

	private ChatScreen() {
	}

	/** The text in the input. */
	public static String text(GuiScreen screen) {
		String text = TasPlugins.first(hooks -> hooks.chatText(screen));
		return text != null ? text : ((GuiTextField) field(screen, GuiTextField.class)).getText();
	}

	/** The suggestions as shown: in 1.7.10's own chat, the completions the server sent for the last Tab. */
	public static List<String> suggestions(GuiScreen screen) {
		List<String> shown = TasPlugins.first(hooks -> hooks.chatSuggestions(screen));
		if (shown != null) {
			return new ArrayList<>(shown);
		}
		List<String> completions = new ArrayList<>();
		for (Object completion : (List<?>) field(screen, List.class)) {
			completions.add(String.valueOf(completion));
		}
		return completions;
	}

	/** The line above the input (a command's usage, its error); 1.7.10's own chat has none. */
	public static List<String> usage(GuiScreen screen) {
		List<String> usage = TasPlugins.first(hooks -> hooks.chatUsage(screen));
		return usage == null ? Collections.<String>emptyList() : new ArrayList<>(usage);
	}

	/** GuiChat's one field of that type, by its type rather than its name. */
	private static Object field(GuiScreen screen, Class<?> type) {
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

package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.mojang.brigadier.suggestion.Suggestion;
import com.mojang.brigadier.suggestion.Suggestions;
import com.mojang.serialization.DynamicOps;
import com.mojang.serialization.JsonOps;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.ChatFormatting;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.components.CommandSuggestions;
import net.minecraft.client.gui.screens.ChatScreen;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.multiplayer.ClientPacketListener;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.ComponentSerialization;
import net.minecraft.network.chat.Style;
import net.minecraft.network.chat.TextColor;
import net.minecraft.util.FormattedCharSequence;

import java.util.Optional;
import java.util.concurrent.CompletableFuture;

/**
 * The chat in 26.3 (PROTOCOL.md 8.6 and 7; SPEC.md 19.7 step 2), as 1.7.10's: every line the client is given is kept
 * (chat.send's lines, command.run's in multiplayer) and sent as a chat event when asked for, its text plain, with the
 * colour codes 1.7.10's chat writes (an error's begins with the red one, §c), as the game's JSON, and its kind (chat, a
 * player's; system, the game's); chat.read reads the open chat's text, the suggestions as the text they were made for
 * would be after each, and the usage it shows; chat.send sends a line as typed into the chat and sent.
 */
public final class ModernChat {

	/** The chat screen's text box and its suggestions; the suggestions' pending, usage and shown list (all private). */
	private static final java.lang.reflect.Field INPUT = Members.field(ChatScreen.class, "input");
	private static final java.lang.reflect.Field SUGGESTIONS = Members.field(ChatScreen.class, "commandSuggestions");
	private static final java.lang.reflect.Field PENDING = Members.field(CommandSuggestions.class, "pendingSuggestions");
	private static final java.lang.reflect.Field USAGE = Members.field(CommandSuggestions.class, "commandUsage");
	private static final java.lang.reflect.Field SHOWN = Members.field(CommandSuggestions.class, "suggestions");
	/** A shown list's text it was made for, and its suggestions. */
	private static final java.lang.reflect.Field MADE_FOR = Members.field(CommandSuggestions.SuggestionsList.class,
		"originalContents");
	private static final java.lang.reflect.Field LIST = Members.field(CommandSuggestions.SuggestionsList.class,
		"suggestionList");

	private ModernChat() {
	}

	static void bind(Probe probe) {
		probe.op("chat.read").does(ModernChat::read);
		probe.op("chat.send").does(ModernChat::send).settles(ModernChat::lines);
	}

	/** A chat line the client was given (ChatComponent.addMessage, through MixinChatComponent). */
	public static void heard(Component message, String kind) {
		Probe probe = Probe.get();
		if (probe == null || message == null) {
			return;
		}
		String plain = message.getString();
		String formatted = legacy(message);
		String json = json(message);
		probe.chat.add(plain, formatted, json);
		if (probe.events.chat) {
			probe.event("chat", Json.object("plain", plain, "formatted", formatted, "json", json,
				"kind", kind));
		}
	}

	/** The line with the colour codes 1.7.10's chat writes: § and the code before each part of a named colour. */
	static String legacy(Component message) {
		StringBuilder out = new StringBuilder();
		message.visit((style, part) -> {
			TextColor color = style.getColor();
			if (color != null) {
				for (ChatFormatting format : ChatFormatting.values()) {
					if (color.equals(TextColor.fromLegacyFormat(format))) {
						out.append(format);
						break;
					}
				}
			}
			out.append(part);
			return Optional.empty();
		}, Style.EMPTY);
		return out.toString();
	}

	/** The line as the game's own JSON, by its registries when a world is open. */
	private static String json(Component message) {
		Minecraft mc = Minecraft.getInstance();
		DynamicOps<JsonElement> ops = mc.level == null ? JsonOps.INSTANCE
			: mc.level.registryAccess().createSerializationContext(JsonOps.INSTANCE);
		return ComponentSerialization.CODEC.encodeStart(ops, message).result().map(JsonElement::toString).orElse("");
	}

	private static JsonElement read(Call call) throws ProbeException {
		Screen screen = Version.screen();
		if (!(screen instanceof ChatScreen)) {
			throw new ProbeException("NotReady", "the chat isn't open (the screen is "
				+ (screen == null ? "none" : Members.className(screen.getClass())) + ")", null);
		}
		String text = Members.<net.minecraft.client.gui.components.EditBox>get(INPUT, screen).getValue();
		CommandSuggestions shown = Members.get(SUGGESTIONS, screen);
		JsonArray offered = new JsonArray();
		CompletableFuture<Suggestions> pending = Members.get(PENDING, shown);
		CommandSuggestions.SuggestionsList list = Members.get(SHOWN, shown);
		if (list != null) {
			// the list the chat shows, each applied to the text it was made for: Tab keeps it while it cycles, the text
			// changing under it
			String madeFor = Members.get(MADE_FOR, list);
			for (Suggestion each : Members.<java.util.List<Suggestion>>get(LIST, list)) {
				offered.add(each.apply(madeFor));
			}
		} else if (pending != null && pending.isDone() && !pending.isCompletedExceptionally()) {
			for (Suggestion each : pending.join().getList()) {
				offered.add(each.apply(text));
			}
		}
		JsonArray usage = new JsonArray();
		for (FormattedCharSequence line : Members.<java.util.List<FormattedCharSequence>>get(USAGE, shown)) {
			StringBuilder plain = new StringBuilder();
			line.accept((index, style, codePoint) -> {
				plain.appendCodePoint(codePoint);
				return true;
			});
			usage.add(plain.toString());
		}
		return Json.object("text", text, "suggestions", offered, "usage", usage);
	}

	/** As if typed into the chat and sent: into the chat's history, and to the server, a command as one (8.6). */
	private static JsonElement send(Call call) throws ProbeException {
		Minecraft mc = Minecraft.getInstance();
		String text = call.string("text", null);
		if (text == null) {
			throw ProbeException.badRequest("text", "chat.send needs the text");
		}
		ClientPacketListener connection = mc.getConnection();
		if (mc.player == null || connection == null) {
			throw new ProbeException("NotReady", "chat.send needs a world", null);
		}
		call.mark = call.probe.chat.mark();
		Version.chat().addRecentChat(text);
		if (text.startsWith("/")) {
			connection.sendCommand(text.substring(1));
		} else {
			connection.sendChat(text);
		}
		return Json.object("lines", new JsonArray(), "errors", new JsonArray());
	}

	/** chat.send's rest: settle_ticks client ticks, then the lines that came meanwhile, the red ones its errors. */
	private static JsonElement lines(Call call, JsonElement value) throws ProbeException, InterruptedException {
		ModernThings.waitClient(call, call.number("settle_ticks", 4, 0, 1200), value);
		JsonArray lines = new JsonArray();
		JsonArray errors = new JsonArray();
		for (JsonObject line : call.probe.chat.since(call.mark)) {
			lines.add(line.get("plain"));
			if (Json.string(line, "formatted").startsWith("§c")) {
				errors.add(line.get("plain"));
			}
		}
		return Json.object("lines", lines, "errors", errors);
	}
}

package io.github.asgerjon.unittas.probe.link;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;
import com.google.gson.JsonParseException;
import com.google.gson.JsonParser;
import com.google.gson.JsonPrimitive;

import java.nio.charset.StandardCharsets;
import java.util.Collection;
import java.util.Map;

/**
 * The protocol's lines of JSON (PROTOCOL.md 3), through Minecraft's own Gson: one object a line, UTF-8, the newline
 * escaped inside values, nulls kept, no HTML escaping, non-finite numbers spelled as the protocol spells them.
 */
public final class Json {

	/** Nulls kept: the protocol's null is a value ("world": null), and Gson leaves null members out unless told. */
	private static final Gson GSON = new GsonBuilder().disableHtmlEscaping().serializeNulls().create();

	private Json() {
	}

	/** The message in a line; IllegalArgumentException when it isn't a JSON object. */
	public static JsonObject parse(String line) {
		JsonElement element;
		try {
			element = new JsonParser().parse(line);
		} catch (JsonParseException | IllegalStateException e) {
			throw new IllegalArgumentException("not JSON: " + e.getMessage(), e);
		}
		if (element == null || !element.isJsonObject()) {
			throw new IllegalArgumentException("a message is a JSON object, not " + (element == null ? "nothing" : element));
		}
		return element.getAsJsonObject();
	}

	/** One message as one line, ended by a newline. */
	public static byte[] line(JsonObject message) {
		return (GSON.toJson(message) + "\n").getBytes(StandardCharsets.UTF_8);
	}

	/** An object from keys and values in turn: object("a", 1, "b", "two"). */
	public static JsonObject object(Object... keysAndValues) {
		JsonObject object = new JsonObject();
		for (int i = 0; i + 1 < keysAndValues.length; i += 2) {
			object.add(String.valueOf(keysAndValues[i]), of(keysAndValues[i + 1]));
		}
		return object;
	}

	/** A value as JSON: null, strings, numbers, booleans, JSON already, collections and maps of those. */
	public static JsonElement of(Object value) {
		if (value == null) {
			return JsonNull.INSTANCE;
		}
		if (value instanceof JsonElement) {
			return (JsonElement) value;
		}
		if (value instanceof String) {
			return new JsonPrimitive((String) value);
		}
		if (value instanceof Boolean) {
			return new JsonPrimitive((Boolean) value);
		}
		if (value instanceof Double || value instanceof Float) {
			double number = ((Number) value).doubleValue();
			if (Double.isNaN(number)) {
				return new JsonPrimitive("NaN");
			}
			if (Double.isInfinite(number)) {
				return new JsonPrimitive(number > 0 ? "Infinity" : "-Infinity");
			}
			return new JsonPrimitive(number);
		}
		if (value instanceof Number) {
			return new JsonPrimitive((Number) value);
		}
		if (value instanceof Collection<?>) {
			JsonArray array = new JsonArray();
			for (Object item : (Collection<?>) value) {
				array.add(of(item));
			}
			return array;
		}
		if (value instanceof Map<?, ?>) {
			JsonObject object = new JsonObject();
			for (Map.Entry<?, ?> entry : ((Map<?, ?>) value).entrySet()) {
				object.add(String.valueOf(entry.getKey()), of(entry.getValue()));
			}
			return object;
		}
		return new JsonPrimitive(String.valueOf(value));
	}

	/** The string under the key, or null when there is none or it isn't a string. */
	public static String string(JsonObject object, String key) {
		JsonElement value = object == null ? null : object.get(key);
		return value != null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isString() ? value.getAsString() : null;
	}
}

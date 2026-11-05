package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.entity.Entity;
import net.minecraft.item.ItemStack;
import net.minecraft.nbt.NBTBase;
import net.minecraft.server.MinecraftServer;

import java.lang.reflect.Array;
import java.lang.reflect.Constructor;
import java.lang.reflect.Executable;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;

/**
 * Reflection, the way into what no operation reaches (PROTOCOL.md 5.9): a starting point (from), steps along a path
 * (a field or no-argument method by name, a call with arguments, an index, a key), and the value found turned into JSON,
 * or kept as a ref. Names are the running game's (MCP in a development run, Searge in a real client): the probe maps
 * none, the orchestrator translates readable names. Runs on the request's side.
 */
final class Reflect {

	private static final int MOST_ELEMENTS = 10000;

	/** A class itself, as a starting point: its static fields and methods. */
	private static final class Statics {
		final Class<?> type;

		Statics(Class<?> type) {
			this.type = type;
		}
	}

	/** What a JSON value can't become. */
	private static final Object NO = new Object();

	private Reflect() {
	}

	static ClassLoader loader() {
		return Minecraft.class.getClassLoader();
	}

	// ---------------------------------------------------------------- where a path starts

	static Object from(Call call, JsonElement from) throws ProbeException {
		if (from == null || from.isJsonNull()) {
			throw ProbeException.badRequest("from", "reflection needs a from: \"player\", \"world\", \"minecraft\","
				+ " {\"entity\": n}, {\"ref\": n}, {\"class\": name} or {\"new\": name, \"args\": [...]}");
		}
		if (from.isJsonPrimitive()) {
			String name = from.getAsString();
			switch (name) {
				case "player":
					return GameOps.player(call);
				case "world":
					return GameOps.player(call).worldObj;
				case "minecraft":
					return call.side == Side.CLIENT ? Minecraft.getMinecraft() : MinecraftServer.getServer();
				default:
					throw ProbeException.badRequest("from", "from is \"player\", \"world\" or \"minecraft\", not " + name);
			}
		}
		JsonObject object = from.getAsJsonObject();
		if (object.has("entity")) {
			int id = object.get("entity").getAsInt();
			Entity found = GameOps.player(call).worldObj.getEntityByID(id);
			if (found == null) {
				throw new ProbeException("NotFound", "no entity " + id + " in the world", Json.object("what", id));
			}
			return found;
		}
		if (object.has("ref")) {
			return ref(call, object.get("ref").getAsInt());
		}
		if (object.has("class")) {
			return new Statics(type(object.get("class").getAsString()));
		}
		if (object.has("new")) {
			Class<?> type = type(object.get("new").getAsString());
			JsonArray args = object.has("args") ? object.getAsJsonArray("args") : new JsonArray();
			String sig = Json.string(object, "sig");
			List<Constructor<?>> constructors = new ArrayList<>();
			for (Constructor<?> constructor : type.getDeclaredConstructors()) {
				constructors.add(constructor);
			}
			Executable chosen = choose(call, constructors, args, sig, "new " + type.getName());
			try {
				chosen.setAccessible(true);
				return ((Constructor<?>) chosen).newInstance(convertAll(call, chosen, args));
			} catch (InvocationTargetException e) {
				throw thrown("new " + type.getName(), e.getCause());
			} catch (ReflectiveOperationException e) {
				throw new ProbeException("ProbeError", "can't make a " + type.getName() + ": " + e, null);
			}
		}
		throw ProbeException.badRequest("from", "from is none of the kinds: " + from);
	}

	static Object ref(Call call, int id) throws ProbeException {
		Refs.Ref ref = call.probe.refs.get(id);
		if (ref == null) {
			throw new ProbeException("NotFound", "no ref " + id + ": " + call.probe.refs.why(id), Json.object("what", id));
		}
		if (ref.side != call.side) {
			call.warn("ref " + id + " was made on the " + ref.side.wire + " and is used on the " + call.side.wire
				+ " thread: its objects belong to the " + ref.side.wire);
		}
		return ref.object;
	}

	static Class<?> type(String name) throws ProbeException {
		try {
			return Class.forName(name, false, loader());
		} catch (ClassNotFoundException | LinkageError e) {
			throw new ProbeException("NotFound", "no class " + name, Json.object("what", name));
		}
	}

	// ---------------------------------------------------------------- along the path

	static Object walk(Call call, Object here, JsonArray path, int upTo) throws ProbeException {
		Object at = here;
		for (int i = 0; i < upTo; i++) {
			if (at == null) {
				throw new ProbeException("NotFound", "the path reached null before step " + i + " (" + path.get(i) + ")",
					Json.object("what", path.get(i)));
			}
			at = step(call, at, path.get(i));
		}
		return at;
	}

	private static Object step(Call call, Object here, JsonElement step) throws ProbeException {
		if (step.isJsonPrimitive()) {
			return byName(call, here, step.getAsString());
		}
		if (!step.isJsonObject()) {
			throw ProbeException.badRequest("path", "a step is a name or an object, not " + step);
		}
		JsonObject object = step.getAsJsonObject();
		if (object.has("name")) {
			return byName(call, here, pick(here, names(object.get("name"), "name"), Member.ANY));
		}
		if (object.has("call")) {
			JsonArray args = object.has("args") ? object.getAsJsonArray("args") : new JsonArray();
			String name = pick(here, names(object.get("call"), "call"), Member.METHOD);
			return invoke(call, here, name, args, Json.string(object, "sig"));
		}
		if (object.has("index")) {
			int index = object.get("index").getAsInt();
			if (here.getClass().isArray()) {
				if (index < 0 || index >= Array.getLength(here)) {
					throw new ProbeException("NotFound", "no index " + index + " in an array of " + Array.getLength(here), null);
				}
				return Array.get(here, index);
			}
			if (here instanceof List<?>) {
				List<?> list = (List<?>) here;
				if (index < 0 || index >= list.size()) {
					throw new ProbeException("NotFound", "no index " + index + " in a list of " + list.size(), null);
				}
				return list.get(index);
			}
			throw ProbeException.badRequest("path", "an index needs an array or a list, not a " + here.getClass().getName());
		}
		if (object.has("key")) {
			if (!(here instanceof Map<?, ?>)) {
				throw ProbeException.badRequest("path", "a key needs a map, not a " + here.getClass().getName());
			}
			return ((Map<?, ?>) here).get(object.get("key").getAsString());
		}
		throw ProbeException.badRequest("path", "a step is a name, {\"name\": ...}, {\"call\": ...}, {\"index\": n} or"
			+ " {\"key\": k}, not " + step);
	}

	/** A field by that name, read; else a method with no arguments, called. */
	private static Object byName(Call call, Object here, String name) throws ProbeException {
		Field field = field(owner(here), name, here instanceof Statics);
		if (field != null) {
			try {
				return field.get(here instanceof Statics ? null : here);
			} catch (IllegalAccessException e) {
				throw new ProbeException("ProbeError", "can't read " + name + ": " + e, null);
			}
		}
		return invoke(call, here, name, new JsonArray(), null);
	}

	/** What a candidate name must be on the object's class chain to fit. */
	private enum Member {
		/** a name step's: a field, or a method */
		ANY("a field or a method"),
		/** a call's */
		METHOD("a method"),
		/** reflect.set's last step's */
		FIELD("a field");

		final String words;

		Member(String words) {
			this.words = words;
		}
	}

	/** A step's name, or its candidates (PROTOCOL.md 5.9): a string, or a list of strings that isn't empty. */
	private static List<String> names(JsonElement given, String key) throws ProbeException {
		List<String> out = new ArrayList<>();
		if (given.isJsonPrimitive() && given.getAsJsonPrimitive().isString()) {
			out.add(given.getAsString());
			return out;
		}
		if (given.isJsonArray() && given.getAsJsonArray().size() > 0) {
			for (JsonElement each : given.getAsJsonArray()) {
				if (!each.isJsonPrimitive() || !each.getAsJsonPrimitive().isString()) {
					throw ProbeException.badRequest("path", key + "'s candidates are names, not " + each);
				}
				out.add(each.getAsString());
			}
			return out;
		}
		throw ProbeException.badRequest("path", key + " is a name, or a list of candidate names, not " + given);
	}

	/**
	 * The one of the candidate names the object's class chain has (PROTOCOL.md 5.9): the orchestrator sends a readable
	 * name's Searge names with it, not knowing the class a step lands on. A single name is taken as it is (its own
	 * error, if any, says more). Several fitting is a BadRequest naming them; none, NotFound naming them all.
	 */
	private static String pick(Object here, List<String> names, Member member) throws ProbeException {
		if (names.size() == 1) {
			return names.get(0);
		}
		Class<?> type = owner(here);
		boolean statics = here instanceof Statics;
		List<String> fits = new ArrayList<>();
		for (String name : names) {
			boolean has = member != Member.METHOD && field(type, name, statics) != null
				|| member != Member.FIELD && hasMethod(type, name, statics);
			if (has && !fits.contains(name)) {
				fits.add(name);
			}
		}
		if (fits.size() == 1) {
			return fits.get(0);
		}
		if (fits.isEmpty()) {
			throw new ProbeException("NotFound", type.getName() + " has none of " + String.join(", ", names) + " as "
				+ member.words, Json.object("what", names));
		}
		throw ProbeException.badRequest("path", "several of the candidates are " + member.words + " of " + type.getName()
			+ ": " + String.join(", ", fits));
	}

	/** Whether the class chain (or the class's interfaces) has a method by that name, static or not as asked. */
	private static boolean hasMethod(Class<?> type, String name, boolean statics) {
		for (Class<?> at = type; at != null; at = at.getSuperclass()) {
			for (Method method : at.getDeclaredMethods()) {
				if (method.getName().equals(name) && statics == Modifier.isStatic(method.getModifiers())) {
					return true;
				}
			}
		}
		if (!statics) {
			for (Class<?> face : type.getInterfaces()) {
				for (Method method : face.getMethods()) {
					if (method.getName().equals(name)) {
						return true;
					}
				}
			}
		}
		return false;
	}

	private static Class<?> owner(Object here) {
		return here instanceof Statics ? ((Statics) here).type : here.getClass();
	}

	/** The field by name, up the class chain, of any visibility; static ones only for a class itself. */
	static Field field(Class<?> type, String name, boolean statics) {
		for (Class<?> at = type; at != null; at = at.getSuperclass()) {
			try {
				Field field = at.getDeclaredField(name);
				if (statics == Modifier.isStatic(field.getModifiers())) {
					field.setAccessible(true);
					return field;
				}
			} catch (NoSuchFieldException e) {
				// further up
			}
		}
		return null;
	}

	private static Object invoke(Call call, Object here, String name, JsonArray args, String sig) throws ProbeException {
		boolean statics = here instanceof Statics;
		// by signature, the most specific first: an override up the chain is the same method, not a second one
		Map<String, Method> bySignature = new java.util.LinkedHashMap<>();
		for (Class<?> at = owner(here); at != null; at = at.getSuperclass()) {
			for (Method method : at.getDeclaredMethods()) {
				if (method.getName().equals(name) && statics == Modifier.isStatic(method.getModifiers())) {
					bySignature.putIfAbsent(signature(method), method);
				}
			}
		}
		for (Class<?> face : owner(here).getInterfaces()) {
			for (Method method : face.getMethods()) {
				if (method.getName().equals(name) && !statics) {
					bySignature.putIfAbsent(signature(method), method);
				}
			}
		}
		List<Method> named = new ArrayList<>(bySignature.values());
		if (named.isEmpty()) {
			throw new ProbeException("NotFound", owner(here).getName() + " has no field or method " + name
				+ " (names are the running game's: MCP in a development run, Searge in a real client)", Json.object("what", name));
		}
		Method chosen = (Method) choose(call, named, args, sig, name);
		try {
			chosen.setAccessible(true);
			return chosen.invoke(statics ? null : here, convertAll(call, chosen, args));
		} catch (InvocationTargetException e) {
			throw thrown(name, e.getCause());
		} catch (IllegalAccessException e) {
			throw new ProbeException("ProbeError", "can't call " + name + ": " + e, null);
		}
	}

	private static ProbeException thrown(String what, Throwable cause) {
		return new ProbeException("GameError", what + " threw " + cause, Json.object(
			"exception", cause == null ? null : cause.getClass().getName(), "trace", Probe.trace(cause == null ? new Throwable() : cause)));
	}

	/**
	 * The one method or constructor the arguments fit: by their number, then by which ones every argument converts to;
	 * with sig, the one of that signature. Ambiguous: a BadRequest naming the candidates by their signatures.
	 */
	private static Executable choose(Call call, List<? extends Executable> all, JsonArray args, String sig, String what)
		throws ProbeException {
		List<Executable> fits = new ArrayList<>();
		for (Executable each : all) {
			if (sig != null) {
				if (signature(each).equals(sig)) {
					return each;
				}
				continue;
			}
			if (each.getParameterCount() != args.size()) {
				continue;
			}
			boolean ok = true;
			Class<?>[] types = each.getParameterTypes();
			for (int i = 0; i < types.length && ok; i++) {
				ok = convert(call, args.get(i), types[i]) != NO;
			}
			if (ok) {
				fits.add(each);
			}
		}
		if (fits.size() == 1) {
			return fits.get(0);
		}
		List<String> names = new ArrayList<>();
		for (Executable each : sig != null ? all : fits.isEmpty() ? all : fits) {
			names.add(signature(each));
		}
		if (fits.isEmpty()) {
			throw new ProbeException("NotFound", "no " + what + " takes these " + args.size() + " arguments"
				+ (sig != null ? " with the signature " + sig : "") + "; there are " + String.join(", ", names),
				Json.object("what", what));
		}
		throw ProbeException.badRequest("path", what + " is ambiguous for these arguments: " + String.join(", ", names)
			+ " (give \"sig\" to choose)");
	}

	/** A method's or constructor's JVM descriptor: "(II)I". */
	static String signature(Executable each) {
		StringBuilder out = new StringBuilder("(");
		for (Class<?> type : each.getParameterTypes()) {
			out.append(descriptor(type));
		}
		out.append(')').append(each instanceof Method ? descriptor(((Method) each).getReturnType()) : "V");
		return out.toString();
	}

	private static String descriptor(Class<?> type) {
		if (type.isArray()) {
			return "[" + descriptor(type.getComponentType());
		}
		if (type == int.class) {
			return "I";
		}
		if (type == long.class) {
			return "J";
		}
		if (type == boolean.class) {
			return "Z";
		}
		if (type == byte.class) {
			return "B";
		}
		if (type == char.class) {
			return "C";
		}
		if (type == short.class) {
			return "S";
		}
		if (type == float.class) {
			return "F";
		}
		if (type == double.class) {
			return "D";
		}
		if (type == void.class) {
			return "V";
		}
		return "L" + type.getName().replace('.', '/') + ";";
	}

	// ---------------------------------------------------------------- JSON into Java

	private static Object[] convertAll(Call call, Executable target, JsonArray args) throws ProbeException {
		Class<?>[] types = target.getParameterTypes();
		Object[] values = new Object[types.length];
		for (int i = 0; i < types.length; i++) {
			Object value = convert(call, args.get(i), types[i]);
			if (value == NO) {
				throw ProbeException.badRequest("path", "argument " + i + " (" + args.get(i) + ") isn't a " + types[i].getName());
			}
			values[i] = value;
		}
		return values;
	}

	/** The JSON value as the type, or NO. */
	@SuppressWarnings({"unchecked", "rawtypes"})
	static Object convert(Call call, JsonElement value, Class<?> type) {
		Class<?> boxed = box(type);
		if (value == null || value.isJsonNull()) {
			return type.isPrimitive() ? NO : null;
		}
		if (value.isJsonObject()) {
			JsonObject object = value.getAsJsonObject();
			try {
				if (object.has("ref")) {
					Object held = ref(call, object.get("ref").getAsInt());
					return held == null || boxed.isInstance(held) ? held : NO;
				}
				if (object.has("entity")) {
					Entity found = GameOps.player(call).worldObj.getEntityByID(object.get("entity").getAsInt());
					return found != null && boxed.isInstance(found) ? found : NO;
				}
				if (object.has("id") && boxed.isAssignableFrom(ItemStack.class)) {
					return ThingOps.stack(object);
				}
			} catch (ProbeException e) {
				return NO;
			}
			return NO;
		}
		if (value.isJsonArray()) {
			return NO;
		}
		if (value.getAsJsonPrimitive().isBoolean()) {
			return boxed == Boolean.class || boxed == Object.class ? value.getAsBoolean() : NO;
		}
		if (value.getAsJsonPrimitive().isNumber()) {
			double number = value.getAsDouble();
			boolean whole = number == Math.floor(number) && !Double.isInfinite(number);
			if (boxed == Integer.class && whole && number >= Integer.MIN_VALUE && number <= Integer.MAX_VALUE) {
				return (int) number;
			}
			if (boxed == Long.class && whole) {
				return value.getAsLong();
			}
			if (boxed == Short.class && whole && number >= Short.MIN_VALUE && number <= Short.MAX_VALUE) {
				return (short) number;
			}
			if (boxed == Byte.class && whole && number >= Byte.MIN_VALUE && number <= Byte.MAX_VALUE) {
				return (byte) number;
			}
			if (boxed == Double.class) {
				return number;
			}
			if (boxed == Float.class) {
				return (float) number;
			}
			if (boxed == Object.class || boxed == Number.class) {
				return whole ? (Object) value.getAsLong() : (Object) number;
			}
			return NO;
		}
		String text = value.getAsString();
		if (boxed == String.class || boxed == Object.class || boxed == CharSequence.class) {
			return text;
		}
		if (boxed == Character.class && text.length() == 1) {
			return text.charAt(0);
		}
		if (type.isEnum()) {
			try {
				return Enum.valueOf((Class) type, text);
			} catch (IllegalArgumentException e) {
				return NO;
			}
		}
		if ("player".equals(text)) {
			try {
				Object player = GameOps.player(call);
				return boxed.isInstance(player) ? player : NO;
			} catch (ProbeException e) {
				return NO;
			}
		}
		return NO;
	}

	private static Class<?> box(Class<?> type) {
		if (!type.isPrimitive()) {
			return type;
		}
		if (type == int.class) {
			return Integer.class;
		}
		if (type == long.class) {
			return Long.class;
		}
		if (type == boolean.class) {
			return Boolean.class;
		}
		if (type == byte.class) {
			return Byte.class;
		}
		if (type == char.class) {
			return Character.class;
		}
		if (type == short.class) {
			return Short.class;
		}
		if (type == float.class) {
			return Float.class;
		}
		if (type == double.class) {
			return Double.class;
		}
		return Void.class;
	}

	// ---------------------------------------------------------------- Java into JSON

	/** The value as JSON (5.9): itself, a summary, SNBT, a list, or a ref; as "ref" a ref, as "text" its toString. */
	static JsonElement out(Call call, Object value, String as) {
		if ("text".equals(as)) {
			return Json.of(value == null ? null : cut(String.valueOf(value)));
		}
		if ("ref".equals(as)) {
			return value == null ? JsonNull.INSTANCE : ref(call, value);
		}
		return value(call, value, 0);
	}

	private static JsonObject ref(Call call, Object value) {
		int id = call.probe.refs.add(value, call.side);
		return Json.object("ref", id, "class", value.getClass().getName(), "text", cut(String.valueOf(value)));
	}

	private static String cut(String text) {
		return text.length() > 200 ? text.substring(0, 200) + "..." : text;
	}

	private static JsonElement value(Call call, Object value, int depth) {
		if (value == null) {
			return JsonNull.INSTANCE;
		}
		if (value instanceof Boolean || value instanceof Number || value instanceof String) {
			return Json.of(value);
		}
		if (value instanceof Character) {
			return Json.of(String.valueOf(value));
		}
		if (value instanceof Enum<?>) {
			return Json.of(((Enum<?>) value).name());
		}
		if (value instanceof ItemStack) {
			return Values.item((ItemStack) value);
		}
		if (value instanceof Entity) {
			return Values.entity((Entity) value);
		}
		if (value instanceof NBTBase) {
			return Json.of(Snbt.write((NBTBase) value));
		}
		if (depth < 3 && value.getClass().isArray() && Array.getLength(value) <= MOST_ELEMENTS) {
			JsonArray array = new JsonArray();
			for (int i = 0; i < Array.getLength(value); i++) {
				array.add(value(call, Array.get(value, i), depth + 1));
			}
			return array;
		}
		if (depth < 3 && value instanceof Collection<?> && ((Collection<?>) value).size() <= MOST_ELEMENTS) {
			JsonArray array = new JsonArray();
			for (Object each : (Collection<?>) value) {
				array.add(value(call, each, depth + 1));
			}
			return array;
		}
		if (depth < 3 && value instanceof Map<?, ?> && ((Map<?, ?>) value).size() <= MOST_ELEMENTS) {
			Map<?, ?> map = (Map<?, ?>) value;
			boolean named = true;
			for (Object key : map.keySet()) {
				named &= key instanceof String;
			}
			if (named) {
				JsonObject object = new JsonObject();
				for (Map.Entry<?, ?> entry : map.entrySet()) {
					object.add((String) entry.getKey(), value(call, entry.getValue(), depth + 1));
				}
				return object;
			}
			JsonArray pairs = new JsonArray();
			for (Map.Entry<?, ?> entry : map.entrySet()) {
				JsonArray pair = new JsonArray();
				pair.add(value(call, entry.getKey(), depth + 1));
				pair.add(value(call, entry.getValue(), depth + 1));
				pairs.add(pair);
			}
			return pairs;
		}
		return ref(call, value);
	}

	// ---------------------------------------------------------------- the operations

	static JsonElement get(Call call) throws ProbeException {
		JsonArray path = path(call);
		Object found = walk(call, from(call, call.args.get("from")), path, path.size());
		String as = call.string("as", "value");
		if (!as.equals("value") && !as.equals("ref") && !as.equals("text")) {
			throw ProbeException.badRequest("as", "as is value, ref or text, not " + as);
		}
		return out(call, found instanceof Statics ? ((Statics) found).type : found, as);
	}

	static JsonElement set(Call call) throws ProbeException {
		JsonArray path = path(call);
		JsonElement last = path.size() == 0 ? null : path.get(path.size() - 1);
		boolean named = last != null && (last.isJsonPrimitive() || last.isJsonObject() && last.getAsJsonObject().has("name"));
		if (!named) {
			throw ProbeException.badRequest("path", "reflect.set's path ends in a field's name (or its candidates)");
		}
		Object owner = walk(call, from(call, call.args.get("from")), path, path.size() - 1);
		if (owner == null) {
			throw new ProbeException("NotFound", "the path reached null before its last step " + last, null);
		}
		String name = last.isJsonPrimitive() ? last.getAsString()
			: pick(owner, names(last.getAsJsonObject().get("name"), "name"), Member.FIELD);
		Field field = field(owner(owner), name, owner instanceof Statics);
		if (field == null) {
			throw new ProbeException("NotFound", owner(owner).getName() + " has no field " + name, Json.object("what", name));
		}
		if (Modifier.isFinal(field.getModifiers())) {
			throw ProbeException.badRequest("path", name + " is final: reflect.set doesn't change a final field");
		}
		Object value = convert(call, call.args.get("value"), field.getType());
		if (value == NO) {
			throw ProbeException.badRequest("value", call.args.get("value") + " isn't a " + field.getType().getName());
		}
		try {
			field.set(owner instanceof Statics ? null : owner, value);
		} catch (IllegalAccessException e) {
			throw new ProbeException("ProbeError", "can't set " + name + ": " + e, null);
		}
		return new JsonObject();
	}

	private static JsonArray path(Call call) throws ProbeException {
		JsonElement path = call.args.get("path");
		if (path == null || path.isJsonNull()) {
			return new JsonArray();
		}
		if (!path.isJsonArray()) {
			throw ProbeException.badRequest("path", "path is a list of steps");
		}
		return path.getAsJsonArray();
	}

	/** A screen made by reflection, for screen.open's {"class": ..., "args": [...]}. */
	static Object make(Call call, JsonObject spec) throws ProbeException {
		JsonObject from = new JsonObject();
		from.add("new", spec.get("class"));
		if (spec.has("args")) {
			from.add("args", spec.get("args"));
		}
		if (spec.has("sig")) {
			from.add("sig", spec.get("sig"));
		}
		return from(call, from);
	}
}

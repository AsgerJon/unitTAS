package io.github.asgerjon.unittas.probe;

import net.minecraft.nbt.NBTBase;
import net.minecraft.nbt.NBTTagByte;
import net.minecraft.nbt.NBTTagByteArray;
import net.minecraft.nbt.NBTTagCompound;
import net.minecraft.nbt.NBTTagDouble;
import net.minecraft.nbt.NBTTagFloat;
import net.minecraft.nbt.NBTTagInt;
import net.minecraft.nbt.NBTTagIntArray;
import net.minecraft.nbt.NBTTagList;
import net.minecraft.nbt.NBTTagLong;
import net.minecraft.nbt.NBTTagShort;
import net.minecraft.nbt.NBTTagString;

import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;
import java.util.TreeSet;
import java.util.regex.Pattern;

/**
 * NBT as modern SNBT text (PROTOCOL.md 5.6), the probe's own reader and writer: 1.7.10's JsonToNBT reads another
 * syntax. Numbers carry their type (1b 2s 3 4L 5.5f 6.25d), arrays theirs ([B;1b,2b], [I;1,2]); keys are written in
 * order, quoted when they aren't plain.
 */
public final class Snbt {

	private static final Pattern BARE_KEY = Pattern.compile("^[A-Za-z0-9._+-]+$");
	private static final Pattern NUMBER = Pattern.compile("^[-+]?(?:\\d+\\.?\\d*|\\.\\d+)(?:[eE][-+]?\\d+)?([bBsSlLfFdD]?)$");
	/** NBTTagList's elements (no getter for them in 1.7.10): MCP's name, then Searge's. */
	private static final Field LIST = field(NBTTagList.class, "tagList", "field_74747_a");

	private Snbt() {
	}

	private static Field field(Class<?> owner, String... names) {
		for (String name : names) {
			try {
				Field found = owner.getDeclaredField(name);
				found.setAccessible(true);
				return found;
			} catch (NoSuchFieldException e) {
				// the other name
			}
		}
		throw new IllegalStateException(owner.getName() + " has none of the fields " + String.join(", ", names));
	}

	// ---------------------------------------------------------------- writing

	public static String write(NBTBase tag) {
		StringBuilder out = new StringBuilder();
		write(tag, out);
		return out.toString();
	}

	private static void write(NBTBase tag, StringBuilder out) {
		switch (tag.getId()) {
			case 1:
				out.append(((NBTTagByte) tag).getByte()).append('b');
				break;
			case 2:
				out.append(((NBTTagShort) tag).getShort()).append('s');
				break;
			case 3:
				out.append(((NBTTagInt) tag).getInt());
				break;
			case 4:
				out.append(((NBTTagLong) tag).getLong()).append('L');
				break;
			case 5:
				out.append(((NBTTagFloat) tag).getFloat()).append('f');
				break;
			case 6:
				out.append(((NBTTagDouble) tag).getDouble()).append('d');
				break;
			case 7: {
				out.append("[B;");
				byte[] bytes = ((NBTTagByteArray) tag).getByteArray();
				for (int i = 0; i < bytes.length; i++) {
					out.append(i == 0 ? "" : ",").append(bytes[i]).append('b');
				}
				out.append(']');
				break;
			}
			case 8:
				quote(((NBTTagString) tag).getString(), out);
				break;
			case 9: {
				out.append('[');
				List<NBTBase> items = elements((NBTTagList) tag);
				for (int i = 0; i < items.size(); i++) {
					out.append(i == 0 ? "" : ",");
					write(items.get(i), out);
				}
				out.append(']');
				break;
			}
			case 10: {
				NBTTagCompound compound = (NBTTagCompound) tag;
				out.append('{');
				boolean first = true;
				for (Object key : new TreeSet<Object>(compound.getKeySet())) {
					String name = String.valueOf(key);
					out.append(first ? "" : ",");
					first = false;
					if (BARE_KEY.matcher(name).matches()) {
						out.append(name);
					} else {
						quote(name, out);
					}
					out.append(':');
					write(compound.getTag(name), out);
				}
				out.append('}');
				break;
			}
			case 11: {
				out.append("[I;");
				int[] ints = ((NBTTagIntArray) tag).getIntArray();
				for (int i = 0; i < ints.length; i++) {
					out.append(i == 0 ? "" : ",").append(ints[i]);
				}
				out.append(']');
				break;
			}
			default:
				throw new IllegalArgumentException("no SNBT for NBT type " + tag.getId());
		}
	}

	private static void quote(String text, StringBuilder out) {
		out.append('"').append(text.replace("\\", "\\\\").replace("\"", "\\\"")).append('"');
	}

	@SuppressWarnings("unchecked")
	private static List<NBTBase> elements(NBTTagList list) {
		try {
			return new ArrayList<>((List<NBTBase>) LIST.get(list));
		} catch (IllegalAccessException e) {
			throw new IllegalStateException("can't read an NBT list", e);
		}
	}

	// ---------------------------------------------------------------- reading

	/** The NBT the text describes; IllegalArgumentException, with the place, for text that isn't SNBT. */
	public static NBTBase read(String text) {
		Reader reader = new Reader(text);
		NBTBase value = reader.value();
		if (reader.peek() != 0) {
			throw reader.fail("more after the value");
		}
		return value;
	}

	/** A compound, as items', tiles' and entities' NBT is. */
	public static NBTTagCompound readCompound(String text) {
		NBTBase value = read(text);
		if (!(value instanceof NBTTagCompound)) {
			throw new IllegalArgumentException("a compound ({...}) is needed, not " + text);
		}
		return (NBTTagCompound) value;
	}

	private static final class Reader {
		final String text;
		int at;

		Reader(String text) {
			this.text = text;
		}

		IllegalArgumentException fail(String what) {
			return new IllegalArgumentException("not SNBT: " + what + " at " + at + " in " + text);
		}

		char peek() {
			while (at < text.length() && Character.isWhitespace(text.charAt(at))) {
				at++;
			}
			return at < text.length() ? text.charAt(at) : 0;
		}

		void take(char expected) {
			if (peek() != expected) {
				throw fail("'" + expected + "' expected");
			}
			at++;
		}

		NBTBase value() {
			char head = peek();
			if (head == '{') {
				return compound();
			}
			if (head == '[') {
				return list();
			}
			if (head == '"' || head == '\'') {
				return new NBTTagString(quoted());
			}
			if (head == 0) {
				throw fail("a value expected");
			}
			return bare();
		}

		NBTTagCompound compound() {
			take('{');
			NBTTagCompound found = new NBTTagCompound();
			if (peek() == '}') {
				at++;
				return found;
			}
			while (true) {
				String key = peek() == '"' || peek() == '\'' ? quoted() : bareKey();
				take(':');
				found.setTag(key, value());
				if (peek() == ',') {
					at++;
					continue;
				}
				take('}');
				return found;
			}
		}

		NBTBase list() {
			take('[');
			if (at + 1 < text.length() && text.charAt(at + 1) == ';' && "BIL".indexOf(text.charAt(at)) >= 0) {
				char kind = text.charAt(at);
				at += 2;
				if (kind == 'L') {
					throw fail("1.7.10 has no long arrays");
				}
				List<NBTBase> items = new ArrayList<>();
				if (peek() != ']') {
					while (true) {
						items.add(value());
						if (peek() == ',') {
							at++;
							continue;
						}
						break;
					}
				}
				take(']');
				if (kind == 'B') {
					byte[] bytes = new byte[items.size()];
					for (int i = 0; i < bytes.length; i++) {
						if (!(items.get(i) instanceof NBTTagByte)) {
							throw fail("a B array holds bytes only");
						}
						bytes[i] = ((NBTTagByte) items.get(i)).getByte();
					}
					return new NBTTagByteArray(bytes);
				}
				int[] ints = new int[items.size()];
				for (int i = 0; i < ints.length; i++) {
					if (!(items.get(i) instanceof NBTTagInt)) {
						throw fail("an I array holds ints only");
					}
					ints[i] = ((NBTTagInt) items.get(i)).getInt();
				}
				return new NBTTagIntArray(ints);
			}
			NBTTagList list = new NBTTagList();
			if (peek() == ']') {
				at++;
				return list;
			}
			byte type = -1;
			while (true) {
				NBTBase item = value();
				if (type >= 0 && item.getId() != type) {
					throw fail("a list's items are all of one type");
				}
				type = item.getId();
				list.appendTag(item);
				if (peek() == ',') {
					at++;
					continue;
				}
				take(']');
				return list;
			}
		}

		String quoted() {
			char quote = text.charAt(at);
			at++;
			StringBuilder out = new StringBuilder();
			while (at < text.length()) {
				char next = text.charAt(at++);
				if (next == '\\') {
					if (at >= text.length()) {
						break;
					}
					out.append(text.charAt(at++));
				} else if (next == quote) {
					return out.toString();
				} else {
					out.append(next);
				}
			}
			throw fail("an unclosed string");
		}

		String bareKey() {
			int start = at;
			while (at < text.length() && BARE_KEY.matcher(String.valueOf(text.charAt(at))).matches()) {
				at++;
			}
			if (at == start) {
				throw fail("a key expected");
			}
			return text.substring(start, at);
		}

		NBTBase bare() {
			int start = at;
			while (at < text.length() && (Character.isLetterOrDigit(text.charAt(at)) || "._+-:".indexOf(text.charAt(at)) >= 0)) {
				at++;
			}
			String word = text.substring(start, at);
			if (word.isEmpty()) {
				throw fail("a value expected");
			}
			if (word.equals("true")) {
				return new NBTTagByte((byte) 1);
			}
			if (word.equals("false")) {
				return new NBTTagByte((byte) 0);
			}
			java.util.regex.Matcher number = NUMBER.matcher(word);
			if (!number.matches()) {
				return new NBTTagString(word);
			}
			String suffix = number.group(1).toLowerCase(java.util.Locale.ROOT);
			String digits = suffix.isEmpty() ? word : word.substring(0, word.length() - 1);
			try {
				switch (suffix) {
					case "b":
						return new NBTTagByte(Byte.parseByte(digits));
					case "s":
						return new NBTTagShort(Short.parseShort(digits));
					case "l":
						return new NBTTagLong(Long.parseLong(digits));
					case "f":
						return new NBTTagFloat(Float.parseFloat(digits));
					case "d":
						return new NBTTagDouble(Double.parseDouble(digits));
					default:
						if (digits.contains(".") || digits.toLowerCase(java.util.Locale.ROOT).contains("e")) {
							return new NBTTagDouble(Double.parseDouble(digits));
						}
						return new NBTTagInt(Integer.parseInt(digits));
				}
			} catch (NumberFormatException e) {
				throw fail("a number out of its type's range: " + word);
			}
		}
	}
}

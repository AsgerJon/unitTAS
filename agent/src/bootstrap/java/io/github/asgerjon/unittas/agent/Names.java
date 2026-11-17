package io.github.asgerjon.unittas.agent;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

/**
 * A version's names, one way round (SPEC.md 19.7 step 6b): the orchestrator's table (unittas.mojangnames), each class,
 * field and method of the game from Mojang's names to the ones the game runs under, or with inverse() the other way.
 * Its first line says its format, what the names run under (obfuscated, intermediary, srg) and the game; then a line
 * per name, tab apart: "c FROM TO", or "f"/"m" OWNER NAME DESCRIPTOR TO, in the from side's names. A line it can't
 * read is refused, saying where. JDK only.
 */
final class Names {

	static final String HEADER = "unittas-names";
	static final String FORMAT = "1";

	/** What the names run under (obfuscated, intermediary, srg) and the game they are for. */
	final String kind;
	final String minecraft;
	private final Map<String, String> classes;
	private final Map<String, String> fields;
	private final Map<String, String> methods;

	private Names(String kind, String minecraft, Map<String, String> classes, Map<String, String> fields,
		Map<String, String> methods) {
		this.kind = kind;
		this.minecraft = minecraft;
		this.classes = classes;
		this.fields = fields;
		this.methods = methods;
	}

	/** The table at that path. IllegalArgumentException for a line it can't read. */
	static Names read(Path table) throws IOException {
		Map<String, String> classes = new HashMap<>();
		Map<String, String> fields = new HashMap<>();
		Map<String, String> methods = new HashMap<>();
		try (BufferedReader in = Files.newBufferedReader(table, StandardCharsets.UTF_8)) {
			String[] header = split(in.readLine(), table, 1);
			if (header.length != 4 || !header[0].equals(HEADER) || !header[1].equals(FORMAT)) {
				throw new IllegalArgumentException(table + " isn't a table of names in format " + FORMAT
					+ " (its first line: " + String.join(" ", header) + ")");
			}
			int number = 1;
			for (String line = in.readLine(); line != null; line = in.readLine()) {
				number++;
				String[] parts = split(line, table, number);
				if (parts[0].equals("c") && parts.length == 3) {
					classes.put(parts[1], parts[2]);
				} else if ((parts[0].equals("f") || parts[0].equals("m")) && parts.length == 5) {
					(parts[0].equals("f") ? fields : methods).put(key(parts[1], parts[2], parts[3]), parts[4]);
				} else {
					throw new IllegalArgumentException("line " + number + " of " + table + " can't be read: " + line);
				}
			}
			return new Names(header[2], header[3], classes, fields, methods);
		}
	}

	/** The same names the other way round: from the running game's to Mojang's, descriptors in the running names. */
	Names inverse() {
		Map<String, String> classesBack = new HashMap<>();
		for (Map.Entry<String, String> each : classes.entrySet()) {
			classesBack.put(each.getValue(), each.getKey());
		}
		return new Names(kind, minecraft, classesBack, invert(fields), invert(methods));
	}

	private Map<String, String> invert(Map<String, String> members) {
		Map<String, String> back = new HashMap<>();
		for (Map.Entry<String, String> each : members.entrySet()) {
			String[] parts = each.getKey().split("\t", -1);
			back.put(key(className(parts[0]), each.getValue(), descriptor(parts[2])), parts[1]);
		}
		return back;
	}

	/** Whether a class (by its internal name) is the game's. */
	boolean known(String internalName) {
		return classes.containsKey(internalName);
	}

	/** A class's other name; a class not the game's (the JDK's, a library's, the probe's) is itself. */
	String className(String internalName) {
		return classes.getOrDefault(internalName, internalName);
	}

	/** A Class entry's name renamed: a class's, or an array's descriptor. */
	String typeName(String classEntry) {
		return classEntry.startsWith("[") ? descriptor(classEntry) : className(classEntry);
	}

	/** A field's other name, or null when the table hasn't it. */
	String field(String owner, String name, String descriptor) {
		return fields.get(key(owner, name, descriptor));
	}

	/** A method's other name, or null when the table hasn't it. */
	String method(String owner, String name, String descriptor) {
		return methods.get(key(owner, name, descriptor));
	}

	/** A field's or a method's descriptor with each class in it renamed. */
	String descriptor(String descriptor) {
		StringBuilder out = new StringBuilder(descriptor.length());
		int at = 0;
		while (at < descriptor.length()) {
			char each = descriptor.charAt(at);
			if (each == 'L') {
				int end = descriptor.indexOf(';', at);
				if (end < 0) {
					throw new IllegalArgumentException("a descriptor with an unended class: " + descriptor);
				}
				out.append('L').append(className(descriptor.substring(at + 1, end))).append(';');
				at = end + 1;
			} else {
				out.append(each);
				at++;
			}
		}
		return out.toString();
	}

	/** A generic signature (JVMS 4.7.9.1: a class's, a method's or a field's) with each class in it renamed. */
	String signature(String signature) {
		return new Signature(signature).renamed();
	}

	static String key(String owner, String name, String descriptor) {
		return owner + "\t" + name + "\t" + descriptor;
	}

	/** The running classes back to Mojang's, and members by what reflection knows of them: built at the first lookup. */
	private volatile Map<String, String> classesBack;
	private volatile Map<String, String> fieldsByName;
	private volatile Map<String, String> methodsByParameters;

	/**
	 * What the probe's reflection asks (its Members, through the bridge, in JDK types only: SPEC.md 19.7 step 6c), a
	 * key to an answer, null where there is none:
	 * - "kind": what the names run under (obfuscated, intermediary, srg);
	 * - "c RUNNING": a running class's Mojang name (internal names), null for a class not the game's;
	 * - "C MOJANG": a class's running name by its Mojang name, null for a class not the game's;
	 * - "f OWNER NAME": a field's running name, by its Mojang owner and name (a class declares one field by a name);
	 * - "m OWNER NAME (PARAMETERS)": a method's running name, by its Mojang owner, name and parameters' descriptors.
	 * Another key is an IllegalArgumentException.
	 */
	String lookup(String key) {
		String[] parts = key.split("\t", -1);
		if (parts.length == 1 && parts[0].equals("kind")) {
			return kind;
		}
		if (classesBack == null) {
			index();
		}
		if (parts.length == 2 && parts[0].equals("c")) {
			return classesBack.get(parts[1]);
		}
		if (parts.length == 2 && parts[0].equals("C")) {
			return classes.get(parts[1]);
		}
		if (parts.length == 3 && parts[0].equals("f")) {
			return fieldsByName.get(parts[1] + "\t" + parts[2]);
		}
		if (parts.length == 4 && parts[0].equals("m")) {
			return methodsByParameters.get(parts[1] + "\t" + parts[2] + "\t" + parts[3]);
		}
		throw new IllegalArgumentException("the names know no key " + key.replace('\t', ' '));
	}

	private synchronized void index() {
		if (classesBack != null) {
			return;
		}
		Map<String, String> back = new HashMap<>();
		for (Map.Entry<String, String> each : classes.entrySet()) {
			back.put(each.getValue(), each.getKey());
		}
		Map<String, String> byName = new HashMap<>();
		for (Map.Entry<String, String> each : fields.entrySet()) {
			String[] parts = each.getKey().split("\t", -1);
			byName.put(parts[0] + "\t" + parts[1], each.getValue());
		}
		Map<String, String> byParameters = new HashMap<>();
		for (Map.Entry<String, String> each : methods.entrySet()) {
			String[] parts = each.getKey().split("\t", -1);
			String parameters = parts[2].substring(0, parts[2].indexOf(')') + 1);
			byParameters.put(parts[0] + "\t" + parts[1] + "\t" + parameters, each.getValue());
		}
		fieldsByName = byName;
		methodsByParameters = byParameters;
		classesBack = back;
	}

	private static String[] split(String line, Path table, int number) {
		if (line == null) {
			throw new IllegalArgumentException(table + " is empty");
		}
		return line.split("\t", -1);
	}

	/** One signature read and written again, its classes renamed (JVMS 4.7.9.1's grammar). */
	private final class Signature {

		private final String text;
		private final StringBuilder out = new StringBuilder();
		private int at;

		Signature(String text) {
			this.text = text;
		}

		String renamed() {
			if (peek() == '<') {
				typeParameters();
			}
			if (peek() == '(') {
				take('(');
				while (peek() != ')') {
					javaType();
				}
				take(')');
				if (peek() == 'V') {
					take('V');
				} else {
					javaType();
				}
				while (at < text.length() && peek() == '^') {
					take('^');
					reference();
				}
			} else {
				while (at < text.length()) {
					javaType();
				}
			}
			if (at != text.length()) {
				throw error();
			}
			return out.toString();
		}

		private void typeParameters() {
			take('<');
			while (peek() != '>') {
				int colon = text.indexOf(':', at);
				if (colon < 0) {
					throw error();
				}
				out.append(text, at, colon);
				at = colon;
				take(':');
				if (peek() != ':' && peek() != '>') {
					reference();
				}
				while (peek() == ':') {
					take(':');
					reference();
				}
			}
			take('>');
		}

		private void javaType() {
			if ("BCDFIJSZ".indexOf(peek()) >= 0) {
				out.append(text.charAt(at++));
			} else {
				reference();
			}
		}

		private void reference() {
			switch (peek()) {
				case 'L':
					classType();
					break;
				case 'T': {
					int end = text.indexOf(';', at);
					if (end < 0) {
						throw error();
					}
					out.append(text, at, end + 1);
					at = end + 1;
					break;
				}
				case '[':
					take('[');
					javaType();
					break;
				default:
					throw error();
			}
		}

		/** L outer <args> (. inner <args>)* ; renamed as a whole, written back in the same shape. */
		private void classType() {
			take('L', false);
			String name = identifier();
			String running = className(name);
			out.append('L').append(running);
			typeArguments();
			while (peek() == '.') {
				at++;
				String inner = identifier();
				name = name + "$" + inner;
				String runningInner = className(name);
				if (!runningInner.startsWith(running + "$")) {
					throw new IllegalArgumentException("a signature names " + name + ", whose other name " + runningInner
						+ " isn't nested in " + running + "'s: " + text);
				}
				out.append('.').append(runningInner, running.length() + 1, runningInner.length());
				running = runningInner;
				typeArguments();
			}
			take(';');
		}

		private void typeArguments() {
			if (peek() != '<') {
				return;
			}
			take('<');
			while (peek() != '>') {
				if (peek() == '*') {
					take('*');
					continue;
				}
				if (peek() == '+' || peek() == '-') {
					out.append(text.charAt(at++));
				}
				reference();
			}
			take('>');
		}

		private String identifier() {
			int start = at;
			while (at < text.length() && "<.;".indexOf(text.charAt(at)) < 0) {
				at++;
			}
			if (at == start) {
				throw error();
			}
			return text.substring(start, at);
		}

		private char peek() {
			if (at >= text.length()) {
				throw error();
			}
			return text.charAt(at);
		}

		private void take(char expected) {
			take(expected, true);
		}

		private void take(char expected, boolean written) {
			if (peek() != expected) {
				throw error();
			}
			at++;
			if (written) {
				out.append(expected);
			}
		}

		private IllegalArgumentException error() {
			return new IllegalArgumentException("a signature that can't be read at " + at + ": " + text);
		}
	}
}

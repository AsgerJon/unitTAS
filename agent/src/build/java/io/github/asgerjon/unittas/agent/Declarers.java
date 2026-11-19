package io.github.asgerjon.unittas.agent;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Enumeration;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.stream.Stream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/**
 * Which class declares each game member a probe reaches (SPEC.md 19.7 step 6b), for the agent's renamer: javac names
 * the type a member was reached through (LocalPlayer's getX), the table names it by the class that declares it
 * (Entity's), so the builder finds that class once, against the version's stubs, and packs what it found into the
 * probe's jar (RenamingLoader.DECLARERS). Found for every field and method a class reaches through the game's classes or its own,
 * for each of its own methods that overrides the game's, and for each lambda made for the game's own interface: the
 * first class of the game that declares it, by the JVM's own order (JVMS 5.4.3), or "-" where none does (a JDK
 * method on a game class). Run by bin/build_agent.py, never shipped. JDK only.
 *
 *   java -cp BUILD Declarers STUBS.jar PROBE-CLASSES OUT
 */
public final class Declarers {

	private static final String LAMBDAS = "java/lang/invoke/LambdaMetafactory";

	/**
	 * A class as far as finding a declarer needs: its supertypes, and what it declares (name and descriptor). A class,
	 * not a record: the agent's code is Java 8's (SPEC.md 19.7 step 11a).
	 */
	private static final class Header {
		private final String superName;
		private final List<String> interfaces;
		private final Set<String> fields;
		private final Map<String, Integer> methods;

		Header(String superName, List<String> interfaces, Set<String> fields, Map<String, Integer> methods) {
			this.superName = superName;
			this.interfaces = interfaces;
			this.fields = fields;
			this.methods = methods;
		}

		String superName() {
			return superName;
		}

		List<String> interfaces() {
			return interfaces;
		}

		Set<String> fields() {
			return fields;
		}

		Map<String, Integer> methods() {
			return methods;
		}
	}

	private final Map<String, Header> headers = new HashMap<>();
	private final Set<String> game;

	private Declarers(Set<String> game) {
		this.game = game;
	}

	public static void main(String[] args) throws IOException {
		if (args.length != 3) {
			throw new IllegalArgumentException("Declarers STUBS.jar PROBE-CLASSES OUT");
		}
		Map<String, byte[]> stubs = new HashMap<>();
		try (ZipFile jar = new ZipFile(args[0])) {
			Enumeration<? extends ZipEntry> entries = jar.entries();
			while (entries.hasMoreElements()) {
				ZipEntry entry = entries.nextElement();
				if (entry.getName().endsWith(".class")) {
					try (InputStream in = jar.getInputStream(entry)) {
						stubs.put(entry.getName().substring(0, entry.getName().length() - 6), ClassBytes.readAll(in));
					}
				}
			}
		}
		Map<String, byte[]> probe = new HashMap<>();
		Path root = Paths.get(args[1]);
		try (Stream<Path> paths = Files.walk(root)) {
			for (Path path : (Iterable<Path>) paths::iterator) {
				String name = root.relativize(path).toString().replace('\\', '/');
				if (name.endsWith(".class")) {
					probe.put(name.substring(0, name.length() - 6), Files.readAllBytes(path));
				}
			}
		}
		Map<String, String> found = of(stubs, probe);
		List<String> lines = new ArrayList<>();
		for (Map.Entry<String, String> each : found.entrySet()) {
			lines.add(each.getKey() + "\t" + each.getValue());
		}
		Files.write(Paths.get(args[2]), lines, StandardCharsets.UTF_8);
	}

	/**
	 * The declarers of what the classes reach, the probe's and the game's (the game's classes only as far as their
	 * declarations, as stubs have them; their own code too where it is there): (owner, name, descriptor) to the class
	 * declaring it, all by Mojang's names.
	 */
	static Map<String, String> of(Map<String, byte[]> gameClasses, Map<String, byte[]> probeClasses)
		throws IOException {
		Declarers declarers = new Declarers(gameClasses.keySet());
		Map<String, ClassBytes> files = new TreeMap<>();
		for (Map<String, byte[]> classes : Arrays.asList(gameClasses, probeClasses)) {
			for (Map.Entry<String, byte[]> each : classes.entrySet()) {
				ClassBytes file = new ClassBytes(each.getValue());
				files.put(each.getKey(), file);
				declarers.headers.put(file.name(), header(file));
			}
		}
		Map<String, String> found = new TreeMap<>();
		for (ClassBytes file : files.values()) {
			// a stub has no code, and what its constant pool still names its code is gone with it
			if (hasCode(file)) {
				declarers.reached(file, found);
			}
		}
		return found;
	}

	private static boolean hasCode(ClassBytes file) {
		for (ClassBytes.Member method : file.methods) {
			for (ClassBytes.Attribute attribute : method.attributes) {
				if (file.utf8(attribute.name()).equals("Code")) {
					return true;
				}
			}
		}
		return false;
	}

	private static Header header(ClassBytes file) {
		List<String> interfaces = new ArrayList<>();
		for (int each : file.interfaces) {
			interfaces.add(file.className(each));
		}
		Set<String> fields = new HashSet<>();
		for (ClassBytes.Member field : file.fields) {
			fields.add(file.utf8(field.name) + file.utf8(field.descriptor));
		}
		Map<String, Integer> methods = new HashMap<>();
		for (ClassBytes.Member method : file.methods) {
			methods.put(file.utf8(method.name) + file.utf8(method.descriptor), method.access);
		}
		return new Header(file.superName(), interfaces, fields, methods);
	}

	private void reached(ClassBytes file, Map<String, String> found) throws IOException {
		String self = file.name();
		int size = file.poolSize();
		for (int index = 1; index < size; index++) {
			int tag = file.tag(index);
			if (tag != ClassBytes.FIELD && tag != ClassBytes.METHOD && tag != ClassBytes.INTERFACE_METHOD) {
				continue;
			}
			String owner = file.className(file.reference(index, 0));
			int nameAndType = file.reference(index, 1);
			String name = file.utf8(file.reference(nameAndType, 0));
			String descriptor = file.utf8(file.reference(nameAndType, 1));
			if (headers.containsKey(owner)) {
				found.put(Names.key(owner, name, descriptor),
					tag == ClassBytes.FIELD ? field(owner, name + descriptor) : method(owner, name + descriptor, false));
			}
		}
		if (!game.contains(self)) {
			for (ClassBytes.Member method : file.methods) {
				String name = file.utf8(method.name);
				String descriptor = file.utf8(method.descriptor);
				if (!name.startsWith("<") && (method.access & (ClassBytes.STATIC | ClassBytes.PRIVATE)) == 0) {
					String declarer = method(self, name + descriptor, true);
					if (!declarer.equals("-")) {
						found.put(Names.key(self, name, descriptor), declarer);
					}
				}
			}
		}
		lambdas(file, found);
	}

	/** Each lambda made for an interface of the game's, by the interface's method its call site names. */
	private void lambdas(ClassBytes file, Map<String, String> found) throws IOException {
		List<int[]> bootstraps = new ArrayList<>();
		for (ClassBytes.Attribute attribute : file.attributes) {
			if (file.utf8(attribute.name()).equals("BootstrapMethods")) {
				java.io.DataInputStream in = new java.io.DataInputStream(new java.io.ByteArrayInputStream(attribute.body()));
				int count = in.readUnsignedShort();
				for (int i = 0; i < count; i++) {
					int handle = in.readUnsignedShort();
					int[] method = new int[1 + in.readUnsignedShort()];
					method[0] = handle;
					for (int j = 1; j < method.length; j++) {
						method[j] = in.readUnsignedShort();
					}
					bootstraps.add(method);
				}
			}
		}
		for (int index = 1; index < file.poolSize(); index++) {
			if (file.tag(index) != ClassBytes.INVOKE_DYNAMIC) {
				continue;
			}
			if (file.reference(index, 0) >= bootstraps.size()) {
				throw new IllegalArgumentException(file.name() + " has an invokedynamic with no bootstrap method for it");
			}
			int[] bootstrap = bootstraps.get(file.reference(index, 0));
			int handled = file.reference(bootstrap[0], 0);
			if (!file.className(file.reference(handled, 0)).equals(LAMBDAS) || bootstrap.length < 2) {
				continue;
			}
			int nameAndType = file.reference(index, 1);
			String name = file.utf8(file.reference(nameAndType, 0));
			String descriptor = file.utf8(file.reference(nameAndType, 1));
			String made = descriptor.substring(descriptor.indexOf(')') + 1);
			String face = made.startsWith("L") ? made.substring(1, made.length() - 1) : "";
			if (headers.containsKey(face)) {
				String erased = file.utf8(file.reference(bootstrap[1], 0));
				found.put(Names.key(face, name, erased), method(face, name + erased, false));
			}
		}
	}

	/**
	 * A method's declarer: the class chain first, then its interfaces (JVMS 5.4.3.3), the first of the game's that
	 * declares it; "-" where none does. For an override ('above'), the class's own declaration doesn't count, nor a
	 * private or static method of the game's, which it can't override.
	 */
	private String method(String owner, String nameAndType, boolean above) {
		for (String each = owner; headers.containsKey(each); each = headers.get(each).superName()) {
			if (above && each.equals(owner)) {
				continue;
			}
			Integer access = headers.get(each).methods().get(nameAndType);
			if (access != null && game.contains(each)
				&& !(above && (access & (ClassBytes.STATIC | ClassBytes.PRIVATE)) != 0)) {
				return each;
			}
		}
		Set<String> seen = new HashSet<>();
		for (String each = owner; headers.containsKey(each); each = headers.get(each).superName()) {
			for (String face : headers.get(each).interfaces()) {
				String found = inInterfaces(face, nameAndType, seen);
				if (found != null) {
					return found;
				}
			}
		}
		return "-";
	}

	private String inInterfaces(String face, String nameAndType, Set<String> seen) {
		if (!headers.containsKey(face) || !seen.add(face)) {
			return null;
		}
		if (game.contains(face) && headers.get(face).methods().containsKey(nameAndType)) {
			return face;
		}
		for (String above : headers.get(face).interfaces()) {
			String found = inInterfaces(above, nameAndType, seen);
			if (found != null) {
				return found;
			}
		}
		return null;
	}

	/**
	 * A field's declarer (JVMS 5.4.3.2: the class, its interfaces, then its superclass): the first class that
	 * declares it, if the game's; "-" where it is a class's of the probe's own, or none of the classes known has it.
	 */
	private String field(String owner, String nameAndType) {
		String found = fieldIn(owner, nameAndType, new HashSet<>());
		return found == null || !game.contains(found) ? "-" : found;
	}

	private String fieldIn(String type, String nameAndType, Set<String> seen) {
		if (!headers.containsKey(type) || !seen.add(type)) {
			return null;
		}
		Header header = headers.get(type);
		if (header.fields().contains(nameAndType)) {
			return type;
		}
		for (String face : header.interfaces()) {
			String found = fieldIn(face, nameAndType, seen);
			if (found != null) {
				return found;
			}
		}
		return fieldIn(header.superName(), nameAndType, seen);
	}
}

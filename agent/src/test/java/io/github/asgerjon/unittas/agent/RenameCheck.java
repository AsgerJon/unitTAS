package io.github.asgerjon.unittas.agent;

import java.io.IOException;
import java.lang.reflect.Method;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Stream;

/**
 * The agent's names checked with no game (SPEC.md 19.7 step 6b). A small game of its own (agent/src/test/java's
 * game package, in Mojang's names) is obfuscated by a table the check makes, as ProGuard does Minecraft's: its
 * classes renamed a, b, c, its members by their name and descriptor, so an override keeps its method's name. Then:
 * - the probe beside it (the probe package, compiled against the game in Mojang's names) and the game both renamed
 *   by the table, as the agent renames its probe at run time, and run on their own: the probe sees what it saw before
 *   renaming, though no class of the game has a Mojang name any more;
 * - the obfuscated game turned back into stubs by the table the other way round, as the agent's builder makes them
 *   from a version's client jar: each stub the original's declarations, without code;
 * - generic signatures renamed, the hooks' table renamed, and what it can't name refused.
 * Each check prints "ok NAME" or "FAIL NAME: why"; it exits 1 if any failed. Given a folder, it writes the stubs
 * there, so that bin/tests/test_agent_names.py can compile the probe against them as the builder compiles a port.
 *
 *   java -cp CLASSES io.github.asgerjon.unittas.agent.RenameCheck [STUBS]
 */
public final class RenameCheck {

	private static final String GAME = "io/github/asgerjon/unittas/agent/game/";
	private static final String PROBE = "io/github/asgerjon/unittas/agent/probe/";
	private static final String ENTITY = GAME + "Entity";
	private static final String PLAYER = GAME + "Player";
	private static final String WORLD = GAME + "World";
	/** What the game keeps by its name, as ProGuard keeps an enum's and a constructor's. */
	private static final Set<String> KEPT = Set.of("<init>", "<clinit>", "values", "valueOf");

	private static int failures;

	private RenameCheck() {
	}

	private interface Check {
		void run() throws Exception;
	}

	public static void main(String[] args) throws Exception {
		Path classes = Path.of(RenameCheck.class.getProtectionDomain().getCodeSource().getLocation().toURI());
		Map<String, byte[]> game = classesUnder(classes, GAME);
		Map<String, byte[]> probe = classesUnder(classes, PROBE);
		Path work = Files.createTempDirectory("unittas-rename-check-");
		Path table = work.resolve("names.txt");
		Files.writeString(table, obfuscation(game), StandardCharsets.UTF_8);
		Names names = Names.read(table);
		Map<String, String> declarers = Declarers.of(game, probe);
		Map<String, byte[]> renamed = new TreeMap<>();
		// what the probe sees in Mojang's names, once: the game's statics (Entity.made) carry over a second run here,
		// where each renamed run has a game of its own
		String expected = io.github.asgerjon.unittas.agent.probe.Prober.run();

		check("renamed", () -> {
			Renamer renamer = new Renamer(names, declarers);
			for (Map.Entry<String, byte[]> each : game.entrySet()) {
				renamed.put(names.className(each.getKey()), renamer.rename(each.getValue()));
			}
			for (Map.Entry<String, byte[]> each : probe.entrySet()) {
				renamed.put(each.getKey(), renamer.rename(each.getValue()));
			}
			same(true, renamed.containsKey(names.className(ENTITY)));
			same(false, names.className(ENTITY).equals(ENTITY));
		});
		check("renamed-run", () -> {
			Loader loader = new Loader(renamed);
			Method run = loader.loadClass("io.github.asgerjon.unittas.agent.probe.Prober").getMethod("run");
			same(expected, run.invoke(null));
			// a nested class's simple name, as the JVM reads it from InnerClasses, is its running name's
			String hand = names.className(PLAYER + "$Hand");
			same(hand.substring(hand.lastIndexOf('$') + 1), loader.loadClass(hand).getSimpleName());
		});
		check("renaming-loader", () -> {
			// the probe's jar as the builder packs it: its classes in Mojang's names, the declarers, its manifest
			Path jar = work.resolve("probe.jar");
			java.util.jar.Manifest manifest = new java.util.jar.Manifest();
			manifest.getMainAttributes().put(java.util.jar.Attributes.Name.MANIFEST_VERSION, "1.0");
			manifest.getMainAttributes().put(java.util.jar.Attributes.Name.IMPLEMENTATION_VERSION, "0.0.0-check");
			try (java.util.jar.JarOutputStream out = new java.util.jar.JarOutputStream(Files.newOutputStream(jar),
				manifest)) {
				for (Map.Entry<String, byte[]> each : probe.entrySet()) {
					out.putNextEntry(new java.util.zip.ZipEntry(each.getKey() + ".class"));
					out.write(each.getValue());
				}
				out.putNextEntry(new java.util.zip.ZipEntry(RenamingLoader.DECLARERS));
				StringBuilder lines = new StringBuilder();
				for (Map.Entry<String, String> each : declarers.entrySet()) {
					lines.append(each.getKey()).append('\t').append(each.getValue()).append('\n');
				}
				out.write(lines.toString().getBytes(StandardCharsets.UTF_8));
			}
			Map<String, byte[]> gameOnly = new TreeMap<>(renamed);
			gameOnly.keySet().removeIf(name -> name.startsWith(PROBE));
			try (RenamingLoader loader = RenamingLoader.of(jar.toFile(), new Loader(gameOnly), names)) {
				Class<?> prober = loader.loadClass("io.github.asgerjon.unittas.agent.probe.Prober");
				same(expected, prober.getMethod("run").invoke(null));
				same("0.0.0-check", prober.getPackage().getImplementationVersion());
			}
		});
		check("no-mojang-names-left", () -> {
			Loader loader = new Loader(renamed);
			try {
				loader.loadClass(ENTITY.replace('/', '.'));
				throw new AssertionError("the renamed game still has " + ENTITY);
			} catch (ClassNotFoundException gone) {
				// as it should be: the renamed run above reached the game by its running names alone
			}
		});
		check("stubs", () -> {
			Renamer stubs = Renamer.stubs(names.inverse());
			Path folder = args.length > 0 ? Path.of(args[0]) : work.resolve("stubs");
			for (Map.Entry<String, byte[]> each : game.entrySet()) {
				byte[] stub = stubs.rename(renamed.get(names.className(each.getKey())));
				sameDeclarations(new ClassBytes(each.getValue()), new ClassBytes(stub));
				Path to = folder.resolve(each.getKey() + ".class");
				Files.createDirectories(to.getParent());
				Files.write(to, stub);
			}
		});
		check("signatures", () -> {
			String world = names.className(WORLD);
			String entity = names.className(ENTITY);
			String player = names.className(PLAYER);
			same("<L:Ljava/lang/Object;>(TL;L" + world + ";)Ljava/util/List<+L" + entity + ";>;",
				names.signature("<L:Ljava/lang/Object;>(TL;L" + WORLD + ";)Ljava/util/List<+L" + ENTITY + ";>;"));
			same("<T:L" + entity + ";>(Ljava/lang/Class<TT;>;)TT;^Ljava/io/IOException;",
				names.signature("<T:L" + ENTITY + ";>(Ljava/lang/Class<TT;>;)TT;^Ljava/io/IOException;"));
			same("L" + player + "<TT;>.a;", names.signature("L" + PLAYER + "<TT;>.Hand;"));
			same("Ljava/util/Map<*-[L" + entity + ";>;", names.signature("Ljava/util/Map<*-[L" + ENTITY + ";>;"));
			same("[[I", names.signature("[[I"));
		});
		check("refuses-unknown-member", () -> {
			Path without = work.resolve("without.txt");
			List<String> lines = new ArrayList<>(Files.readAllLines(table));
			same(true, lines.removeIf(line -> line.startsWith("m\t" + ENTITY + "\tgetX\t")));
			Files.write(without, lines);
			refused(() -> new Renamer(Names.read(without), declarers).rename(probe.get(PROBE + "Prober")));
		});
		check("refuses-unresolved", () -> {
			refused(() -> new Renamer(names, Map.of()).rename(probe.get(PROBE + "Prober")));
		});
		check("refuses-bad-table", () -> {
			Path bad = work.resolve("bad.txt");
			Files.writeString(bad, "unittas-names\t2\tobfuscated\tcheck\n");
			refused(() -> Names.read(bad));
		});
		check("lookup", () -> {
			// what the probe's Members asks the bridge, by Mojang's names, for what the game runs under
			java.util.function.Function<String, String> lookup = names::lookup;
			same("obfuscated", lookup.apply("kind"));
			same(ENTITY, lookup.apply("c\t" + names.className(ENTITY)));
			same(null, lookup.apply("c\tjava/lang/String"));
			same(names.className(ENTITY), lookup.apply("C\t" + ENTITY));
			same(null, lookup.apply("C\tjava/lang/String"));
			same(names.field(ENTITY, "x", "D"), lookup.apply("f\t" + ENTITY + "\tx"));
			same(names.method(ENTITY, "tick", "()V"), lookup.apply("m\t" + ENTITY + "\ttick\t()"));
			same(names.method(WORLD, "add", "(L" + ENTITY + ";)V"), lookup.apply("m\t" + WORLD + "\tadd\t(L" + ENTITY + ";)"));
			same(null, lookup.apply("m\t" + ENTITY + "\tgone\t()"));
			same(null, lookup.apply("f\t" + ENTITY + "\tgone"));
			refused(() -> lookup.apply("x\twhat"));
		});
		check("hooks-renamed", () -> {
			List<Hooks.Hook> renamedHooks = Hooks.renamed(List.of(
				new Hooks.Hook(ENTITY, "tick", "()V", Hooks.When.BEFORE, "tick"),
				new Hooks.Hook(WORLD, "add", "(L" + ENTITY + ";)V", Hooks.When.AFTER, "added")), names);
			same(new Hooks.Hook(names.className(ENTITY), names.method(ENTITY, "tick", "()V"), "()V", Hooks.When.BEFORE,
				"tick"), renamedHooks.get(0));
			same(new Hooks.Hook(names.className(WORLD), names.method(WORLD, "add", "(L" + ENTITY + ";)V"),
				"(L" + names.className(ENTITY) + ";)V", Hooks.When.AFTER, "added"), renamedHooks.get(1));
			refused(() -> Hooks.renamed(List.of(new Hooks.Hook(ENTITY, "gone", "()V", Hooks.When.BEFORE, "x")), names));
		});
		System.exit(failures == 0 ? 0 : 1);
	}

	/**
	 * The game's table, as the orchestrator writes Minecraft's: its classes named a, b, c in order (a nested class its
	 * outer's name, "$", a letter), each member by a name made of its own name and descriptor (so an override, or an
	 * interface's method and its implementation, keep one name), what the game keeps as itself.
	 */
	private static String obfuscation(Map<String, byte[]> game) throws IOException {
		Map<String, String> classNames = new TreeMap<>();
		int next = 0;
		for (String name : game.keySet()) {
			int nested = name.indexOf('$');
			if (nested < 0) {
				classNames.put(name, String.valueOf((char) ('a' + next++)));
			}
		}
		for (String name : game.keySet()) {
			int nested = name.indexOf('$');
			if (nested >= 0) {
				classNames.put(name, classNames.get(name.substring(0, nested)) + "$"
					+ (char) ('a' + countNested(classNames, name.substring(0, nested))));
			}
		}
		List<String> lines = new ArrayList<>();
		for (Map.Entry<String, String> each : classNames.entrySet()) {
			lines.add("c\t" + each.getKey() + "\t" + each.getValue());
		}
		for (Map.Entry<String, byte[]> each : game.entrySet()) {
			ClassBytes file = new ClassBytes(each.getValue());
			for (ClassBytes.Member field : file.fields) {
				lines.add(memberLine("f", each.getKey(), file.utf8(field.name), file.utf8(field.descriptor)));
			}
			for (ClassBytes.Member method : file.methods) {
				lines.add(memberLine("m", each.getKey(), file.utf8(method.name), file.utf8(method.descriptor)));
			}
		}
		Collections.sort(lines);
		return "unittas-names\t1\tobfuscated\tcheck\n" + String.join("\n", lines) + "\n";
	}

	private static int countNested(Map<String, String> classNames, String outer) {
		int count = 0;
		for (String name : classNames.keySet()) {
			if (name.startsWith(outer + "$")) {
				count++;
			}
		}
		return count;
	}

	private static String memberLine(String kind, String owner, String name, String descriptor) {
		String running = KEPT.contains(name) ? name
			: kind + Integer.toHexString((name + descriptor).hashCode() & 0x0FFFFFFF);
		return kind + "\t" + owner + "\t" + name + "\t" + descriptor + "\t" + running;
	}

	/** A stub has its original's name, supertypes, members (but the synthetic) and signatures, and no code. */
	private static void sameDeclarations(ClassBytes original, ClassBytes stub) throws java.io.IOException {
		same(original.name(), stub.name());
		same(original.superName(), stub.superName());
		same(interfaces(original), interfaces(stub));
		same(members(original, original.fields), members(stub, stub.fields));
		same(members(original, original.methods), members(stub, stub.methods));
		same(signature(original, original.attributes), signature(stub, stub.attributes));
		same(innerClasses(original), innerClasses(stub));
		for (ClassBytes.Member method : stub.methods) {
			for (ClassBytes.Attribute attribute : method.attributes) {
				if (stub.utf8(attribute.name()).equals("Code")) {
					throw new AssertionError(stub.name() + "." + stub.utf8(method.name) + " kept its code");
				}
			}
		}
	}

	/** Each nested class the file names: the class, its outer, its simple name, its flags. */
	private static List<String> innerClasses(ClassBytes file) throws java.io.IOException {
		List<String> found = new ArrayList<>();
		for (ClassBytes.Attribute attribute : file.attributes) {
			if (file.utf8(attribute.name()).equals("InnerClasses")) {
				byte[] body = attribute.body();
				for (int at = 2; at < body.length; at += 8) {
					int inner = ((body[at] & 0xFF) << 8) | (body[at + 1] & 0xFF);
					int outer = ((body[at + 2] & 0xFF) << 8) | (body[at + 3] & 0xFF);
					int simple = ((body[at + 4] & 0xFF) << 8) | (body[at + 5] & 0xFF);
					int flags = ((body[at + 6] & 0xFF) << 8) | (body[at + 7] & 0xFF);
					found.add(file.className(inner) + " " + (outer == 0 ? "" : file.className(outer)) + " "
						+ (simple == 0 ? "" : file.utf8(simple)) + " " + flags);
				}
			}
		}
		return found;
	}

	private static List<String> interfaces(ClassBytes file) {
		List<String> names = new ArrayList<>();
		for (int each : file.interfaces) {
			names.add(file.className(each));
		}
		return names;
	}

	private static Set<String> members(ClassBytes file, List<ClassBytes.Member> members) {
		Set<String> found = new TreeSet<>();
		for (ClassBytes.Member member : members) {
			if ((member.access & ClassBytes.SYNTHETIC) == 0) {
				found.add(file.utf8(member.name) + " " + file.utf8(member.descriptor) + " " + member.access + " "
					+ signature(file, member.attributes));
			}
		}
		return found;
	}

	private static String signature(ClassBytes file, List<ClassBytes.Attribute> attributes) {
		for (ClassBytes.Attribute attribute : attributes) {
			if (file.utf8(attribute.name()).equals("Signature")) {
				byte[] body = attribute.body();
				return file.utf8(((body[0] & 0xFF) << 8) | (body[1] & 0xFF));
			}
		}
		return "";
	}

	private static Map<String, byte[]> classesUnder(Path root, String folder) throws IOException {
		Map<String, byte[]> found = new TreeMap<>();
		try (Stream<Path> paths = Files.walk(root.resolve(folder))) {
			for (Path path : (Iterable<Path>) paths::iterator) {
				String name = root.relativize(path).toString().replace('\\', '/');
				if (name.endsWith(".class")) {
					found.put(name.substring(0, name.length() - ".class".length()), Files.readAllBytes(path));
				}
			}
		}
		return found;
	}

	private static void check(String name, Check check) {
		try {
			check.run();
			System.out.println("ok " + name);
		} catch (Throwable e) {
			failures++;
			Throwable cause = e instanceof java.lang.reflect.InvocationTargetException ? e.getCause() : e;
			System.out.println("FAIL " + name + ": " + cause);
		}
	}

	private static void refused(Check check) throws Exception {
		try {
			check.run();
		} catch (IllegalArgumentException expected) {
			return;
		}
		throw new AssertionError("done, where it should have been refused");
	}

	private static void same(Object expected, Object actual) {
		if (expected == null ? actual != null : !expected.equals(actual)) {
			throw new AssertionError("expected " + expected + ", got " + actual);
		}
	}

	/** The renamed classes on their own, under the JDK's: no class of the check's is seen through it. */
	private static final class Loader extends ClassLoader {

		private final Map<String, byte[]> classes;

		Loader(Map<String, byte[]> classes) {
			super(ClassLoader.getPlatformClassLoader());
			this.classes = classes;
		}

		@Override
		protected Class<?> findClass(String name) throws ClassNotFoundException {
			byte[] bytes = classes.get(name.replace('.', '/'));
			if (bytes == null) {
				throw new ClassNotFoundException(name);
			}
			return defineClass(name, bytes, 0, bytes.length);
		}
	}
}

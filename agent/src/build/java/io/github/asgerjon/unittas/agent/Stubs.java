package io.github.asgerjon.unittas.agent;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

/**
 * A version's stubs (SPEC.md 19.7 step 6b): every class of its client jar, which runs under obfuscated names, as
 * Mojang names it, declarations only (Renamer.stubs), into a jar that javac compiles the version's probe against.
 * The table is the orchestrator's (unittas.mojangnames), read the other way round. The jar's entries are in a fixed
 * order with a fixed time, so the same client jar makes the same stubs. Run by bin/build_agent.py, never shipped:
 * the stubs stay in the user's download cache. JDK only.
 *
 *   java -cp BUILD Stubs CLIENT.jar TABLE OUT.jar
 */
public final class Stubs {

	/** Every entry's time: 1980-01-01, as the agent's own jars. */
	private static final long STAMP = 315532800000L;

	private Stubs() {
	}

	public static void main(String[] args) throws IOException {
		if (args.length != 3) {
			throw new IllegalArgumentException("Stubs CLIENT.jar TABLE OUT.jar");
		}
		Names names = Names.read(Paths.get(args[1]));
		Map<String, byte[]> stubs = of(Paths.get(args[0]), names);
		Path out = Paths.get(args[2]);
		Path part = out.resolveSibling(out.getFileName() + ".part");
		try (OutputStream file = Files.newOutputStream(part); ZipOutputStream jar = new ZipOutputStream(file)) {
			for (Map.Entry<String, byte[]> each : stubs.entrySet()) {
				ZipEntry entry = new ZipEntry(each.getKey() + ".class");
				entry.setTime(STAMP);
				jar.putNextEntry(entry);
				jar.write(each.getValue());
				jar.closeEntry();
			}
		}
		Files.move(part, out, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
		System.out.println(stubs.size() + " stubs in " + out);
	}

	/** Each class of the client jar as a stub, by its Mojang name. */
	static Map<String, byte[]> of(Path client, Names names) throws IOException {
		Renamer renamer = Renamer.stubs(names.inverse());
		Names back = names.inverse();
		Map<String, byte[]> stubs = new TreeMap<>();
		List<String> unknown = new ArrayList<>();
		try (ZipFile jar = new ZipFile(client.toFile())) {
			Enumeration<? extends ZipEntry> entries = jar.entries();
			while (entries.hasMoreElements()) {
				ZipEntry entry = entries.nextElement();
				String name = entry.getName();
				if (!name.endsWith(".class")) {
					continue;
				}
				String running = name.substring(0, name.length() - ".class".length());
				if (!back.known(running)) {
					unknown.add(running);
					continue;
				}
				try (InputStream in = jar.getInputStream(entry)) {
					stubs.put(back.className(running), renamer.rename(ClassBytes.readAll(in)));
				}
			}
		}
		if (!unknown.isEmpty()) {
			throw new IllegalArgumentException(unknown.size() + " classes of " + client + " aren't in the table of names"
				+ " (the first: " + unknown.get(0) + "): the table isn't this jar's");
		}
		return stubs;
	}
}

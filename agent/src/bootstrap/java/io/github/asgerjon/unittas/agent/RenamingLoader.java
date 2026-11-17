package io.github.asgerjon.unittas.agent;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.security.CodeSigner;
import java.security.CodeSource;
import java.util.HashMap;
import java.util.Map;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

/**
 * The probe's class loader where the game runs under other names than Mojang's (SPEC.md 19.7 step 6b): each class of
 * the probe's jar renamed as it loads (Renamer), by the version's table and the declarers the builder packed into the
 * jar (DECLARERS), then defined under the game's own class loader, its package with the jar's manifest (the probe's
 * version, for its hello). A class that can't be renamed is a ClassFormatError naming why: the probe isn't run by
 * names that would reach the wrong members. JDK only.
 */
final class RenamingLoader extends URLClassLoader {

	/** The probe jar's file of declarers (owner NAME DESCRIPTOR declarer, tab apart), which the builder writes. */
	static final String DECLARERS = "unittas-probe-declarers.txt";

	private final Renamer renamer;
	private final Manifest manifest;
	private final URL jar;

	private RenamingLoader(URL jar, ClassLoader parent, Renamer renamer, Manifest manifest) {
		super("unittas-probe", new URL[] {jar}, parent);
		this.jar = jar;
		this.renamer = renamer;
		this.manifest = manifest;
	}

	/** The loader of that probe jar, renaming by those names. IllegalArgumentException if the jar has no declarers. */
	static RenamingLoader of(File jar, ClassLoader parent, Names names) throws IOException {
		Manifest manifest;
		Map<String, String> declarers = new HashMap<>();
		try (JarFile file = new JarFile(jar)) {
			manifest = file.getManifest();
			if (file.getEntry(DECLARERS) == null) {
				throw new IllegalArgumentException(jar + " has no " + DECLARERS + ": a probe built for a version under"
					+ " Mojang's own names can't be renamed to " + names.kind + " ones");
			}
			try (InputStream in = file.getInputStream(file.getEntry(DECLARERS));
				BufferedReader lines = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
				int number = 0;
				for (String line = lines.readLine(); line != null; line = lines.readLine()) {
					number++;
					String[] parts = line.split("\t", -1);
					if (parts.length != 4) {
						throw new IllegalArgumentException("line " + number + " of " + DECLARERS + " can't be read: " + line);
					}
					declarers.put(Names.key(parts[0], parts[1], parts[2]), parts[3]);
				}
			}
		}
		return new RenamingLoader(jar.toURI().toURL(), parent, new Renamer(names, declarers), manifest);
	}

	@Override
	protected Class<?> findClass(String name) throws ClassNotFoundException {
		URL found = findResource(name.replace('.', '/') + ".class");
		if (found == null) {
			throw new ClassNotFoundException(name);
		}
		byte[] renamed;
		try (InputStream in = found.openStream()) {
			renamed = renamer.rename(in.readAllBytes());
		} catch (IOException | IllegalArgumentException e) {
			throw new ClassFormatError("[unitTAS] the probe's " + name + " can't be renamed: " + e.getMessage());
		}
		int dot = name.lastIndexOf('.');
		if (dot > 0) {
			String packageName = name.substring(0, dot);
			if (getDefinedPackage(packageName) == null) {
				if (manifest != null) {
					definePackage(packageName, manifest, jar);
				} else {
					definePackage(packageName, null, null, null, null, null, null, null);
				}
			}
		}
		return defineClass(name, renamed, 0, renamed.length, new CodeSource(jar, (CodeSigner[]) null));
	}
}

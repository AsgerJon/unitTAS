package io.github.asgerjon.unittas.probe.link;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Properties;
import java.util.regex.Pattern;

/**
 * The start file an orchestrator leaves in the game's folder before it starts the game (PROTOCOL.md 2.1): where to
 * dial, this launch's token, the protocol versions it speaks, the game's name and role. It is read once and deleted at
 * once, so a crash never leaves the next ordinary game in test mode. Only JDK classes here: it is read from the
 * coremod, before any Minecraft class may be touched.
 */
public final class StartFile {

	public static final String PATH = "unittas/probe.properties";
	/** The only address the probe ever dials (PROTOCOL.md 15). */
	public static final String LOOPBACK = "127.0.0.1";

	private static final Pattern CONNECT = Pattern.compile("^127\\.0\\.0\\.1:(\\d{1,5})$");
	private static final Pattern TOKEN = Pattern.compile("^[0-9a-f]{64}$");
	private static final Pattern NAME = Pattern.compile("^[A-Za-z0-9_.-]{1,64}$");

	public final int port;
	public final String token;
	public final List<Integer> protocols;
	public final String name;
	public final String role;
	/** False if the file couldn't be deleted after it was read (the probe says so in the log). */
	public final boolean deleted;

	private StartFile(int port, String token, List<Integer> protocols, String name, String role, boolean deleted) {
		this.port = port;
		this.token = token;
		this.protocols = Collections.unmodifiableList(protocols);
		this.name = name;
		this.role = role;
		this.deleted = deleted;
	}

	/**
	 * The start file in the game's folder, read and then deleted; null when there is none (the probe stays asleep). A
	 * file that can't be used (an address other than 127.0.0.1, a key missing or malformed) throws, deleted all the same.
	 */
	public static StartFile take(File gameDir) {
		File file = new File(gameDir, PATH);
		if (!file.isFile()) {
			return null;
		}
		Properties properties = new Properties();
		boolean deleted;
		try (InputStream in = new FileInputStream(file)) {
			properties.load(in);
		} catch (IOException e) {
			throw new IllegalStateException("can't read the start file " + file + ": " + e, e);
		} finally {
			deleted = file.delete();
		}
		return parse(properties, deleted);
	}

	static StartFile parse(Properties properties, boolean deleted) {
		String connect = value(properties, "connect");
		java.util.regex.Matcher address = CONNECT.matcher(connect);
		if (!address.matches()) {
			throw new IllegalStateException("the start file says connect=" + connect + ": the probe dials 127.0.0.1 only");
		}
		int port = Integer.parseInt(address.group(1));
		if (port < 1 || port > 65535) {
			throw new IllegalStateException("the start file's port " + port + " is no port");
		}
		String token = value(properties, "token");
		if (!TOKEN.matcher(token).matches()) {
			throw new IllegalStateException("the start file's token isn't 64 hexadecimal digits");
		}
		List<Integer> protocols = new ArrayList<>();
		for (String part : value(properties, "protocol").split(",")) {
			try {
				protocols.add(Integer.parseInt(part.trim()));
			} catch (NumberFormatException e) {
				throw new IllegalStateException("the start file's protocol list has " + part + " in it", e);
			}
		}
		String name = value(properties, "name");
		if (!NAME.matcher(name).matches()) {
			throw new IllegalStateException("the start file's name " + name + " isn't a plain name");
		}
		String role = value(properties, "role");
		if (!role.equals("client") && !role.equals("server")) {
			throw new IllegalStateException("the start file's role is " + role + ", neither client nor server");
		}
		return new StartFile(port, token, protocols, name, role, deleted);
	}

	private static String value(Properties properties, String key) {
		String value = properties.getProperty(key);
		if (value == null || value.trim().isEmpty()) {
			throw new IllegalStateException("the start file has no " + key);
		}
		return value.trim();
	}
}

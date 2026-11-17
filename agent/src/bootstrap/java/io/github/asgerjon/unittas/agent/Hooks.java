package io.github.asgerjon.unittas.agent;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/**
 * The game's methods the probe hooks (SPEC.md 19.7 steps 5 and 6c): each version's in its own file, packed into its
 * agent's jar (agent/src/VERSION/hooks.txt, read at premain by read()), by Mojang's names, so that this bootstrap is
 * the same for every version. A hook BEFORE is called as the method is, and may end it there (its value then the
 * method's); a hook AFTER is called once the method has returned (Rewriter wraps each hooked method: step 6a). A
 * constructor can't be wrapped, so nothing hooks one.
 */
final class Hooks {

	enum When {
		BEFORE, AFTER
	}

	/** One hook: where, when, and its name the probe knows it by. A null descriptor takes the name's every method. */
	record Hook(String owner, String method, String descriptor, When when, String id) {
	}

	/** A version's hooks, and the probe's entry class they reach (the bridge starts it at the first hook). */
	record Table(String entry, List<Hook> hooks) {
	}

	/**
	 * A hooks file: '#' lines and blank ones aside, its first line "entry CLASS", then a hook a line, tab apart: when
	 * (BEFORE, AFTER), the class, the method, the descriptor ("*" for every method by the name), the hook's name.
	 * IllegalArgumentException naming the line it can't read ('where' says whose file it is).
	 */
	static Table read(InputStream in, String where) throws IOException {
		BufferedReader lines = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8));
		String entry = null;
		List<Hook> hooks = new ArrayList<>();
		int number = 0;
		for (String line = lines.readLine(); line != null; line = lines.readLine()) {
			number++;
			if (line.isBlank() || line.startsWith("#")) {
				continue;
			}
			String[] parts = line.split("\t", -1);
			if (entry == null) {
				if (parts.length != 2 || !parts[0].equals("entry") || parts[1].isEmpty()) {
					throw new IllegalArgumentException("line " + number + " of " + where + "'s hooks isn't its entry class:"
						+ " " + line);
				}
				entry = parts[1];
				continue;
			}
			if (parts.length != 5 || !(parts[0].equals("BEFORE") || parts[0].equals("AFTER"))) {
				throw new IllegalArgumentException("line " + number + " of " + where + "'s hooks can't be read: " + line);
			}
			hooks.add(new Hook(parts[1], parts[2], parts[3].equals("*") ? null : parts[3], When.valueOf(parts[0]),
				parts[4]));
		}
		if (entry == null) {
			throw new IllegalArgumentException(where + "'s hooks name no entry class");
		}
		return new Table(entry, List.copyOf(hooks));
	}

	private Hooks() {
	}

	/**
	 * The hooks as the game runs under other names (SPEC.md 19.7 step 6b): each hooked class, method and descriptor
	 * by the table's. A hook the table can't name is refused: never put in by its Mojang name, where it would match
	 * nothing (or, worse, another method).
	 */
	static List<Hook> renamed(List<Hook> hooks, Names names) {
		List<Hook> renamed = new ArrayList<>();
		for (Hook hook : hooks) {
			if (hook.descriptor() == null) {
				throw new IllegalArgumentException("a hook with no descriptor can't be renamed: " + hook);
			}
			String method = names.method(hook.owner(), hook.method(), hook.descriptor());
			if (method == null) {
				throw new IllegalArgumentException("no " + names.kind + " name for the hooked " + hook.owner() + "."
					+ hook.method() + hook.descriptor());
			}
			renamed.add(new Hook(names.className(hook.owner()), method, names.descriptor(hook.descriptor()), hook.when(),
				hook.id()));
		}
		return List.copyOf(renamed);
	}
}

package io.github.asgerjon.unittas;

import cpw.mods.fml.common.discovery.ASMDataTable;
import net.minecraft.entity.player.EntityPlayerMP;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.function.Consumer;
import java.util.function.Function;

/** The mods' {@link TasHooks} (the classes marked {@link TasPlugin}), made at start-up, called in their names' order. */
public final class TasPlugins {

	private static final List<TasHooks> HOOKS = new ArrayList<>();
	/** Hooks that couldn't be made, or that threw: the report lists each as an error. */
	private static final List<String> PROBLEMS = Collections.synchronizedList(new ArrayList<>());

	private TasPlugins() {
	}

	private static boolean found;

	/** At start-up, before the run begins (the probe's or the Java runner's: once, whichever comes first). */
	public static synchronized void find(ASMDataTable table) {
		if (found) {
			return;
		}
		found = true;
		Set<String> names = new TreeSet<>();
		for (ASMDataTable.ASMData data : table.getAll(TasPlugin.class.getName())) {
			names.add(data.getClassName());
		}
		for (String name : names) {
			try {
				Class<?> type = Class.forName(name, true, TasPlugins.class.getClassLoader());
				if (!TasHooks.class.isAssignableFrom(type)) {
					PROBLEMS.add(name + " is marked @TasPlugin but doesn't implement TasHooks");
					continue;
				}
				HOOKS.add((TasHooks) type.getConstructor().newInstance());
			} catch (ReflectiveOperationException | LinkageError e) {
				PROBLEMS.add("couldn't make the hooks " + name + ": " + e);
			}
		}
	}

	static List<String> problems() {
		synchronized (PROBLEMS) {
			return new ArrayList<>(PROBLEMS);
		}
	}

	/** Calls each hook; one that throws is reported (progress, log, report) and the others still run. */
	static void each(String what, UnitTas.Request request, Consumer<TasHooks> call) {
		for (TasHooks hooks : HOOKS) {
			try {
				call.accept(hooks);
			} catch (RuntimeException | Error e) {
				String problem = hooks.getClass().getName() + "." + what + " threw " + e;
				PROBLEMS.add(problem);
				request.progress(problem);
				UnitTas.LOG.error(problem, e);
			}
		}
	}

	/**
	 * Calls each hook and says how each went, for the probe's hooks.run: the class, and what it threw or null. One that
	 * throws doesn't stop the others.
	 */
	public static List<Object[]> run(Consumer<TasHooks> call) {
		List<Object[]> outcomes = new ArrayList<>();
		for (TasHooks hooks : HOOKS) {
			try {
				call.accept(hooks);
				outcomes.add(new Object[]{hooks.getClass().getName(), null});
			} catch (RuntimeException | Error e) {
				outcomes.add(new Object[]{hooks.getClass().getName(), e});
			}
		}
		return outcomes;
	}

	/** The first hook's answer that isn't null, or null when no hook answers. */
	public static <T> T first(Function<TasHooks, T> ask) {
		for (TasHooks hooks : HOOKS) {
			T answer = ask.apply(hooks);
			if (answer != null) {
				return answer;
			}
		}
		return null;
	}

	/** Each hook's resetPlayer, on the server thread; one that throws fails the test (it starts from a wrong state). */
	static void resetPlayer(EntityPlayerMP player) {
		for (TasHooks hooks : HOOKS) {
			hooks.resetPlayer(player);
		}
	}
}

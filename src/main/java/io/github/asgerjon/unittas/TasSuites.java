package io.github.asgerjon.unittas;

import cpw.mods.fml.common.discovery.ASMDataTable;

import java.util.Collection;
import java.util.Collections;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/**
 * The suites a run can ask for: every test class marked {@link TasSuite}, by suite, as Forge's annotation table lists
 * them. Only the names are kept here; the runner loads the classes when it runs them.
 */
final class TasSuites {

	/** Each suite's classes, by name; the suites and their classes in name order. */
	private static final Map<String, Set<String>> SUITES = new TreeMap<>();

	private TasSuites() {
	}

	/** At start-up, before the run begins. */
	static void find(ASMDataTable table) {
		for (ASMDataTable.ASMData data : table.getAll(TasSuite.class.getName())) {
			Object suite = data.getAnnotationInfo().get("value");
			if (suite != null) {
				SUITES.computeIfAbsent(suite.toString(), name -> new TreeSet<>()).add(data.getClassName());
			}
		}
	}

	static Collection<String> names() {
		return Collections.unmodifiableSet(SUITES.keySet());
	}

	/** The names of the suite's classes, or null when there is no suite of that name. */
	static Collection<String> classNames(String suite) {
		Set<String> classes = SUITES.get(suite);
		return classes == null ? null : Collections.unmodifiableSet(classes);
	}
}

package io.github.asgerjon.unittas.agent;

import io.github.asgerjon.unittas.agent.sample.Sample;
import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BiFunction;

/**
 * The agent's rewriter checked on class files of its own (SPEC.md 19.7 step 6a), with no game: the samples wrapped,
 * loaded under the JVM's verifier and run, the hooks a recorder in the system properties where the game's hooks find
 * the bridge. Each check prints "ok NAME" or "FAIL NAME: why"; it exits 1 if any failed. bin/tests/test_agent_wrap.py
 * runs it under every Java the agent runs on (17, 21, 25).
 *
 *   java -cp CLASSES io.github.asgerjon.unittas.agent.WrapCheck
 */
public final class WrapCheck {

	private static final String SAMPLE = "io/github/asgerjon/unittas/agent/sample/Sample";
	private static final String SUB = "io/github/asgerjon/unittas/agent/sample/SubSample";
	private static final String ABSTRACT = "io/github/asgerjon/unittas/agent/sample/AbstractSample";
	private static final String INTERFACE = "io/github/asgerjon/unittas/agent/sample/InterfaceSample";

	private static final Object PASS = new Object();
	/** Each hook's answer while a check runs; a hook not named passes. */
	private static final Map<String, Object> ANSWERS = new HashMap<>();
	/** Each hook's call as it came: [its name, the hooked class, the instance, the arguments...]. */
	private static final List<Object[]> CALLS = new ArrayList<>();

	private static Class<?> sample;
	private static Class<?> sub;
	private static int failures;

	private WrapCheck() {
	}

	private interface Check {
		void run() throws Exception;
	}

	public static void main(String[] args) throws Exception {
		System.getProperties().put(Bridge.PASS, PASS);
		System.getProperties().put(Bridge.HOOKS, (BiFunction<String, Object[], Object>) WrapCheck::hook);
		List<Hooks.Hook> hooks = Arrays.asList(
			new Hooks.Hook(SAMPLE, "count", "(I)I", Hooks.When.BEFORE, "count"),
			new Hooks.Hook(SAMPLE, "tick", "()V", Hooks.When.BEFORE, "tick.start"),
			new Hooks.Hook(SAMPLE, "tick", "()V", Hooks.When.AFTER, "tick.end"),
			new Hooks.Hook(SAMPLE, "mix", "(JDLjava/lang/String;ZCF)J", Hooks.When.BEFORE, "mix"),
			new Hooks.Hook(SAMPLE, "title", "()Ljava/lang/String;", Hooks.When.BEFORE, "title"),
			new Hooks.Hook(SAMPLE, "grabbed", "()Z", Hooks.When.BEFORE, "grabbed"),
			new Hooks.Hook(SAMPLE, "half", "(D)D", Hooks.When.AFTER, "half"),
			new Hooks.Hook(SAMPLE, "pick", null, Hooks.When.BEFORE, "pick"),
			new Hooks.Hook(SAMPLE, "loops", "(I)I", Hooks.When.AFTER, "loops"));
		byte[] wrapped = rewrite(hooks, SAMPLE);
		if (wrapped == null) {
			System.out.println("FAIL wrapped: the rewriter refused the sample");
			System.exit(1);
		}
		try {
			Loader loader = new Loader();
			sample = loader.define(SAMPLE, wrapped);
			sub = loader.define(SUB, bytesOf(SUB));
			// linked now, so the JVM's verifier has seen every method
			sample.getConstructor();
		} catch (Throwable e) {
			System.out.println("FAIL wrapped: the JVM refused the wrapped sample: " + e);
			System.exit(1);
		}
		System.out.println("ok wrapped");

		check("before-passes", () -> {
			Object it = make(sample);
			same(5, call(it, "count", 5));
			same(5, sample.getField("counted").get(it));
			same(Arrays.asList("@count", "count"), seen());
			Object[] call = CALLS.get(0);
			same(Arrays.asList("count", sample, it, 5), Arrays.asList(call));
		});
		check("before-answers", () -> {
			ANSWERS.put("count", 99);
			Object it = make(sample);
			same(99, call(it, "count", 5));
			same(0, sample.getField("counted").get(it));
			same(Arrays.asList("@count"), seen());
		});
		check("before-and-after", () -> {
			call(make(sample), "tick");
			same(Arrays.asList("@tick.start", "tick", "@tick.end"), seen());
		});
		check("static-arguments", () -> {
			Method mix = sample.getMethod("mix", long.class, double.class, String.class, boolean.class, char.class,
				float.class);
			same(79L, mix.invoke(null, 7L, 2.5, "abc", true, 'A', 1.5f));
			same(Arrays.asList("@mix", "mix"), seen());
			same(Arrays.asList("mix", sample, null, 7L, 2.5, "abc", true, 'A', 1.5f), Arrays.asList(CALLS.get(0)));
		});
		check("reference-answer", () -> {
			ANSWERS.put("title", "unitTAS");
			same("unitTAS", call(make(sample), "title"));
			same(Arrays.asList("@title"), seen());
		});
		check("boolean-answer", () -> {
			Object it = make(sample);
			ANSWERS.put("grabbed", Boolean.TRUE);
			same(true, call(it, "grabbed"));
			ANSWERS.clear();
			same(false, call(it, "grabbed"));
			same(Arrays.asList("@grabbed", "@grabbed", "grabbed"), seen());
		});
		check("after-primitive", () -> {
			same(2.25, call(make(sample), "half", 4.5));
			same(Arrays.asList("half", "@half"), seen());
		});
		check("overloads", () -> {
			Object it = make(sample);
			same("int 3", sample.getMethod("pick", int.class).invoke(it, 3));
			same("string x", sample.getMethod("pick", String.class).invoke(it, "x"));
			ANSWERS.put("pick", "both");
			same("both", sample.getMethod("pick", int.class).invoke(it, 3));
			same("both", sample.getMethod("pick", String.class).invoke(it, "x"));
			same(Arrays.asList("@pick", "@pick", "@pick", "@pick"), seen());
		});
		check("own-branches", () -> {
			Object it = make(sample);
			Sample original = new Sample();
			for (int n = 0; n <= 12; n++) {
				same(original.loops(n), call(it, "loops", n));
			}
			same(13, CALLS.size());
		});
		check("super-call", () -> {
			call(make(sub), "tick");
			same(Arrays.asList("sub", "@tick.start", "tick", "@tick.end"), seen());
		});
		check("reflection", () -> {
			Method tick = sample.getMethod("tick");
			same(true, Modifier.isPublic(tick.getModifiers()));
			Method original = sample.getDeclaredMethod("tick$unittas");
			same(true, Modifier.isPrivate(original.getModifiers()));
		});
		check("refuses-missing", () -> refused(SAMPLE, new Hooks.Hook(SAMPLE, "gone", "()V", Hooks.When.BEFORE, "x")));
		check("refuses-constructor",
			() -> refused(SAMPLE, new Hooks.Hook(SAMPLE, "<init>", null, Hooks.When.AFTER, "x")));
		check("refuses-abstract",
			() -> refused(ABSTRACT, new Hooks.Hook(ABSTRACT, "nothing", "()V", Hooks.When.BEFORE, "x")));
		check("refuses-interface",
			() -> refused(INTERFACE, new Hooks.Hook(INTERFACE, "answer", "()I", Hooks.When.BEFORE, "x")));
		check("others-untouched", () -> same(null, new Rewriter(Arrays.asList(new Hooks.Hook(SAMPLE, "tick", "()V",
			Hooks.When.BEFORE, "x"))).transform(null, SUB, null, null, bytesOf(SUB))));
		check("hooks-read", () -> {
			Hooks.Table table = Hooks.read(new java.io.ByteArrayInputStream(("# a comment\n\nentry\tx.y.Entry\n"
				+ "BEFORE\ta/B\ttick\t()V\ttick.start\nAFTER\ta/B\tpick\t*\tpicked\n").getBytes(
				java.nio.charset.StandardCharsets.UTF_8)), "the check's");
			same("x.y.Entry", table.entry());
			same(Arrays.asList(new Hooks.Hook("a/B", "tick", "()V", Hooks.When.BEFORE, "tick.start"),
				new Hooks.Hook("a/B", "pick", null, Hooks.When.AFTER, "picked")), table.hooks());
			for (String bad : Arrays.asList("BEFORE\ta/B\ttick\t()V\tx\n", "entry\tx.Entry\nWHILE\ta/B\tt\t()V\tx\n",
				"entry\tx.Entry\nBEFORE\ta/B\t()V\tx\n")) {
				try {
					Hooks.read(new java.io.ByteArrayInputStream(bad.getBytes(java.nio.charset.StandardCharsets.UTF_8)), "bad");
					throw new AssertionError("read, where it should have been refused: " + bad);
				} catch (IllegalArgumentException expected) {
					// as it should be
				}
			}
		});
		System.exit(failures == 0 ? 0 : 1);
	}

	/** The recorder every hook calls: the call kept, "@NAME" said in the hooked class's SEEN, the answer given. */
	@SuppressWarnings("unchecked")
	private static Object hook(String id, Object[] call) {
		Object[] kept = new Object[call.length + 1];
		kept[0] = id;
		System.arraycopy(call, 0, kept, 1, call.length);
		CALLS.add(kept);
		try {
			((List<String>) ((Class<?>) call[0]).getField("SEEN").get(null)).add("@" + id);
		} catch (ReflectiveOperationException e) {
			throw new IllegalStateException(e);
		}
		return ANSWERS.getOrDefault(id, PASS);
	}

	private static void check(String name, Check check) {
		ANSWERS.clear();
		CALLS.clear();
		try {
			seenList().clear();
			check.run();
			System.out.println("ok " + name);
		} catch (Throwable e) {
			failures++;
			Throwable cause = e instanceof java.lang.reflect.InvocationTargetException ? e.getCause() : e;
			System.out.println("FAIL " + name + ": " + cause);
		}
	}

	private static byte[] rewrite(List<Hooks.Hook> hooks, String name) throws IOException {
		return new Rewriter(hooks).transform(null, name, null, null, bytesOf(name));
	}

	private static void refused(String name, Hooks.Hook hook) throws IOException {
		if (rewrite(Arrays.asList(hook), name) != null) {
			throw new AssertionError("rewritten, where it should have been refused: " + hook);
		}
	}

	private static Object make(Class<?> type) throws ReflectiveOperationException {
		return type.getConstructor().newInstance();
	}

	private static Object call(Object on, String name, Object... arguments) throws ReflectiveOperationException {
		for (Method method : on.getClass().getMethods()) {
			if (method.getName().equals(name) && method.getParameterCount() == arguments.length) {
				return method.invoke(on, arguments);
			}
		}
		throw new NoSuchMethodException(name);
	}

	@SuppressWarnings("unchecked")
	private static List<String> seenList() throws ReflectiveOperationException {
		return (List<String>) sample.getField("SEEN").get(null);
	}

	private static List<String> seen() throws ReflectiveOperationException {
		return new ArrayList<>(seenList());
	}

	private static void same(Object expected, Object actual) {
		if (expected == null ? actual != null : !expected.equals(actual)) {
			throw new AssertionError("expected " + expected + ", got " + actual);
		}
	}

	private static byte[] bytesOf(String name) throws IOException {
		try (InputStream in = WrapCheck.class.getResourceAsStream("/" + name + ".class")) {
			if (in == null) {
				throw new IOException("no class file for " + name);
			}
			return ClassBytes.readAll(in);
		}
	}

	/** The wrapped sample's own loader: its classes defined from the bytes given, the rest from the check's. */
	private static final class Loader extends ClassLoader {

		Loader() {
			super(WrapCheck.class.getClassLoader());
		}

		Class<?> define(String name, byte[] bytes) {
			return defineClass(name.replace('/', '.'), bytes, 0, bytes.length);
		}
	}
}

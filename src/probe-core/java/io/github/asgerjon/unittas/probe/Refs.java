package io.github.asgerjon.unittas.probe;

import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * The objects the probe holds on to for reflection (PROTOCOL.md 5.9): a number for each, the side it was made on.
 * Released by refs.release, by refs.clear (after every test), and, those of the server side, when their world closes.
 * A released ref is remembered for a while, so using it says why it is gone.
 */
final class Refs {

	private static final int REMEMBERED = 10000;

	static final class Ref {
		final Object object;
		final Side side;

		Ref(Object object, Side side) {
			this.object = object;
			this.side = side;
		}
	}

	private final AtomicInteger next = new AtomicInteger(1);
	private final Map<Integer, Ref> held = new LinkedHashMap<>();
	private final Map<Integer, String> gone = new LinkedHashMap<>();

	synchronized int add(Object object, Side side) {
		int id = next.getAndIncrement();
		held.put(id, new Ref(object, side));
		return id;
	}

	/** The ref, or null; why it is gone, in {@link #why}. */
	synchronized Ref get(int id) {
		return held.get(id);
	}

	synchronized String why(int id) {
		String reason = gone.get(id);
		return reason != null ? reason : id < next.get() ? "it was released" : "there never was one";
	}

	synchronized int size() {
		return held.size();
	}

	synchronized void release(int id, String reason) {
		if (held.remove(id) != null) {
			remember(id, reason);
		}
	}

	synchronized void clear(String reason) {
		for (Integer id : held.keySet()) {
			remember(id, reason);
		}
		held.clear();
	}

	/** The refs of one side: the server's, when its world closes. */
	synchronized void clear(Side side, String reason) {
		Iterator<Map.Entry<Integer, Ref>> each = held.entrySet().iterator();
		while (each.hasNext()) {
			Map.Entry<Integer, Ref> entry = each.next();
			if (entry.getValue().side == side) {
				remember(entry.getKey(), reason);
				each.remove();
			}
		}
	}

	private void remember(int id, String reason) {
		gone.put(id, reason);
		if (gone.size() > REMEMBERED) {
			gone.remove(gone.keySet().iterator().next());
		}
	}
}

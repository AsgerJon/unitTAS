package io.github.asgerjon.unittas.probe;

import java.util.Queue;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/**
 * The ticks of the game's two threads, and the work done on them (PROTOCOL.md 4): steps queued from other threads run
 * at the end of the side's next tick, in the order they came; then the work that runs every tick until it is done
 * (wait.until's checks, debug.lag); then the tick is counted. Waiting for a side gives up only when that side hasn't
 * ticked for the stall's length, so a game that is slow but ticking is waited for. One for the game, shared by the
 * probe and the Java runner; whoever runs the game calls {@link #noteThread} at the start of each tick and
 * {@link #ticked} at its end. No Minecraft class here.
 */
public final class Sides {

	/** The stall rule's length unless a request names its own. */
	public static final int STALL_SECONDS = 15;

	private static final Sides INSTANCE = new Sides();

	/** A side that stopped ticking: no tick for the stall's length. */
	public static final class Stalled extends RuntimeException {
		public final Side side;
		public final long sinceTickMs;

		Stalled(Side side, long sinceTickMs, int stallSeconds) {
			super("the " + side.wire + " didn't tick for " + stallSeconds + " s");
			this.side = side;
			this.sinceTickMs = sinceTickMs;
		}
	}

	/** Work done at the end of every tick of a side until it says it is done. Runs on that side's thread. */
	public interface EveryTick {
		/** True when it is done (it is then dropped). */
		boolean tick();
	}

	private static final class State {
		final Queue<Runnable> steps = new ConcurrentLinkedQueue<>();
		final CopyOnWriteArrayList<EveryTick> every = new CopyOnWriteArrayList<>();
		volatile long ticks;
		volatile Thread thread;
		volatile long tickedAt;
	}

	private final State client = new State();
	private final State server = new State();
	private final Object tickLock = new Object();

	private Sides() {
	}

	public static Sides get() {
		return INSTANCE;
	}

	private State of(Side side) {
		return side == Side.CLIENT ? client : server;
	}

	// ---------------------------------------------------------------- from the side's own thread

	/** At the start of each tick (and its end): which thread the side is, and that it is ticking. */
	public void noteThread(Side side) {
		State state = of(side);
		state.thread = Thread.currentThread();
		state.tickedAt = System.currentTimeMillis();
	}

	/**
	 * At the end of each tick: the queued steps, then the every-tick work, then the count, which wakes the waiters. Only
	 * the steps queued before this tick's end began: one queued meanwhile (a waiter woken by the step before it, queuing
	 * its next) waits for the next tick, so a step takes a tick (EFR's report, 2026-11-05; StepTests). They are counted,
	 * not swapped out for a fresh queue, so a step never lands in a queue that has already been run.
	 */
	public void ticked(Side side) {
		State state = of(side);
		noteThread(side);
		for (int queued = state.steps.size(); queued > 0; queued--) {
			Runnable step = state.steps.poll();
			if (step == null) {
				break;
			}
			step.run();
		}
		for (EveryTick work : state.every) {
			boolean done;
			try {
				done = work.tick();
			} catch (RuntimeException e) {
				done = true;
			}
			if (done) {
				state.every.remove(work);
			}
		}
		synchronized (tickLock) {
			state.ticks++;
			tickLock.notifyAll();
		}
	}

	// ---------------------------------------------------------------- from anywhere

	public long ticks(Side side) {
		return of(side).ticks;
	}

	/** When the side last ticked (System.currentTimeMillis()); 0 if it never has. */
	public long tickedAt(Side side) {
		return of(side).tickedAt;
	}

	/** The side's thread as last seen; null before its first tick. */
	public Thread thread(Side side) {
		return of(side).thread;
	}

	/** Whether the caller is the side's own thread (a step then runs at once: queued, it would wait for itself). */
	public boolean onThread(Side side) {
		return Thread.currentThread() == of(side).thread;
	}

	/** Work for the end of every tick of the side, from its next tick on (or this one, if called on it). */
	public void everyTick(Side side, EveryTick work) {
		of(side).every.add(work);
	}

	/**
	 * Runs the step on the side's thread at the end of its next tick and returns what it returns; at once when called on
	 * that thread. Throws what the step throws; Stalled when the side doesn't tick for the stall's length meanwhile; and
	 * InterruptedException when the waiting thread is interrupted (the step is then never run, if it hadn't started).
	 * {@code queued} sees the task before it waits, so it can be cancelled.
	 */
	public <T> T run(Side side, Callable<T> step, int stallSeconds, java.util.function.Consumer<FutureTask<T>> queued)
		throws Exception {
		if (onThread(side)) {
			return step.call();
		}
		FutureTask<T> task = new FutureTask<>(step);
		if (queued != null) {
			queued.accept(task);
		}
		of(side).steps.add(task);
		try {
			while (true) {
				long since = System.currentTimeMillis() - tickedAt(side);
				long left = stallSeconds * 1000L - since;
				if (left <= 0) {
					task.cancel(false);
					throw new Stalled(side, since, stallSeconds);
				}
				try {
					return task.get(Math.min(left, 500), TimeUnit.MILLISECONDS);
				} catch (TimeoutException e) {
					// still waiting: the stall is measured again
				}
			}
		} catch (ExecutionException e) {
			Throwable cause = e.getCause();
			if (cause instanceof Exception) {
				throw (Exception) cause;
			}
			if (cause instanceof Error) {
				throw (Error) cause;
			}
			throw new IllegalStateException(cause);
		} catch (InterruptedException | java.util.concurrent.CancellationException e) {
			task.cancel(false);
			if (e instanceof java.util.concurrent.CancellationException) {
				throw new InterruptedException("cancelled");
			}
			throw (InterruptedException) e;
		}
	}

	/**
	 * Queues the step for the side's next tick and returns at once: for a step that keeps its thread busy longer than the
	 * stall rule allows (making a world: the client waits in it while the integrated server starts). The caller watches
	 * for what the step brings about itself.
	 */
	public <T> FutureTask<T> post(Side side, Callable<T> step) {
		FutureTask<T> task = new FutureTask<>(step);
		of(side).steps.add(task);
		return task;
	}

	/**
	 * The side's thread is gone (the integrated server stopped with its world): its steps still queued are cancelled and
	 * its every-tick work dropped, so none of it runs in the next world, and it has no thread until it ticks again.
	 */
	public void forget(Side side) {
		State state = of(side);
		state.thread = null;
		state.tickedAt = 0;
		Runnable step;
		while ((step = state.steps.poll()) != null) {
			if (step instanceof FutureTask<?>) {
				((FutureTask<?>) step).cancel(false);
			}
		}
		state.every.clear();
	}

	/** Waits until the side has ticked {@code n} more times than now; the milliseconds it took. */
	public long waitTicks(Side side, long n, int stallSeconds) throws InterruptedException {
		return waitUntilTick(side, ticks(side) + n, stallSeconds);
	}

	/**
	 * Waits until the side's tick count is at least {@code target}, giving up (Stalled) only when no tick has come for
	 * the stall's length: the timer starts again at each tick. Not on the side's own thread, which doesn't tick while it
	 * waits.
	 */
	public long waitUntilTick(Side side, long target, int stallSeconds) throws InterruptedException {
		if (onThread(side)) {
			throw new IllegalStateException("can't wait for " + side.wire + " ticks on the " + side.wire
				+ " thread: it doesn't tick while it waits");
		}
		long started = System.currentTimeMillis();
		State state = of(side);
		synchronized (tickLock) {
			long seen = state.ticks;
			long giveUp = started + stallSeconds * 1000L;
			while (state.ticks < target) {
				long now = System.currentTimeMillis();
				if (state.ticks != seen) {
					seen = state.ticks;
					giveUp = now + stallSeconds * 1000L;
				}
				long left = giveUp - now;
				if (left <= 0) {
					throw new Stalled(side, now - state.tickedAt, stallSeconds);
				}
				tickLock.wait(left);
			}
		}
		return System.currentTimeMillis() - started;
	}
}

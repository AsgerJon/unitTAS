package io.github.asgerjon.unittas.probe;

import java.util.concurrent.FutureTask;

/**
 * A request being run, for cancel (PROTOCOL.md 4.6): the thread waiting for it, the step it has queued on a side, and
 * what stops a check that runs every tick. Cancel and the request's end are taken under this object's lock, so a
 * cancel that comes too late never reaches the thread's next request.
 */
final class Running {

	final long id;
	private Thread thread;
	private FutureTask<?> queued;
	private Runnable onCancel;
	private boolean done;
	private boolean cancelled;
	private boolean started;

	Running(long id) {
		this.id = id;
	}

	synchronized void waitingOn(Thread waiter) {
		thread = waiter;
	}

	synchronized void queued(FutureTask<?> task) {
		queued = task;
	}

	/** What else stops when the request is cancelled (a check every tick). */
	synchronized void onCancel(Runnable stop) {
		onCancel = stop;
		if (cancelled) {
			stop.run();
		}
	}

	synchronized boolean cancelled() {
		return cancelled;
	}

	/** The request has its answer; a cancel after this finds nothing. */
	synchronized void finish() {
		done = true;
		thread = null;
	}

	/**
	 * On the side's thread, as the request's step starts: false if it was cancelled first (then the step doesn't run).
	 * From here on a cancel is too late.
	 */
	synchronized boolean begin() {
		if (cancelled) {
			return false;
		}
		started = true;
		return true;
	}

	/**
	 * Cancels the request if it isn't too late: not yet started, or waiting. A step already running on its side's thread
	 * is too late: it answers as it would have. (FutureTask.cancel alone can't tell: it also cancels a step that is
	 * running, and throws away what it returns; so the step says when it starts, in {@link #begin}.)
	 */
	synchronized boolean cancel() {
		if (done || started) {
			return false;
		}
		if (queued != null) {
			queued.cancel(false);
		}
		cancelled = true;
		if (onCancel != null) {
			onCancel.run();
		}
		if (thread != null) {
			thread.interrupt();
		}
		return true;
	}
}

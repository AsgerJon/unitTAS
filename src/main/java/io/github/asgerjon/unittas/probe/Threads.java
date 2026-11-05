package io.github.asgerjon.unittas.probe;

import java.lang.management.LockInfo;
import java.lang.management.ManagementFactory;
import java.lang.management.MonitorInfo;
import java.lang.management.ThreadInfo;

/**
 * Every thread's stack with its locks, from the JDK alone: it never waits on the game, so it answers however stuck the
 * game is. hang-threads.txt (TasHang) and debug.threads (PROTOCOL.md 8.12) both end with it.
 */
public final class Threads {

	private Threads() {
	}

	public static String dump() {
		StringBuilder out = new StringBuilder();
		for (ThreadInfo thread : ManagementFactory.getThreadMXBean().dumpAllThreads(true, true)) {
			out.append('"').append(thread.getThreadName()).append("\" ").append(thread.getThreadState());
			LockInfo lock = thread.getLockInfo();
			if (lock != null) {
				out.append(" on ").append(lock);
				if (thread.getLockOwnerName() != null) {
					out.append(" owned by \"").append(thread.getLockOwnerName()).append('"');
				}
			}
			out.append('\n');
			StackTraceElement[] stack = thread.getStackTrace();
			MonitorInfo[] monitors = thread.getLockedMonitors();
			for (int i = 0; i < stack.length; i++) {
				out.append("\tat ").append(stack[i]).append('\n');
				for (MonitorInfo monitor : monitors) {
					if (monitor.getLockedStackDepth() == i) {
						out.append("\t- locked ").append(monitor).append('\n');
					}
				}
			}
			out.append('\n');
		}
		return out.toString();
	}
}

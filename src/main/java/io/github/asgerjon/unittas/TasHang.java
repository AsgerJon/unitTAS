package io.github.asgerjon.unittas;

import net.minecraft.client.Minecraft;
import net.minecraft.network.NetworkManager;
import net.minecraft.network.NetworkSystem;
import net.minecraft.server.integrated.IntegratedServer;
import net.minecraft.util.ScreenShotHelper;

import java.io.File;
import java.lang.management.LockInfo;
import java.lang.management.ManagementFactory;
import java.lang.management.MonitorInfo;
import java.lang.management.ThreadInfo;
import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.List;

/**
 * Evidence of a test world that won't load (stuck at "Loading world"), or of a game that stopped: pictures of the game's
 * own window while it loads, and at the time limit every thread's stack with its locks, the screen, and the state of
 * both ends of the local connection. Written into the results folder, so it is there whoever watches (the sandbox the
 * runs are watched from can neither see the window nor attach to the game).
 */
final class TasHang {

	private TasHang() {
	}

	/** The window as it is now, as screenshots/loading-NNNs.png; returns that path. */
	static String picture(Minecraft mc, File results, int seconds) {
		return picture(mc, results, String.format("loading-%03ds.png", seconds));
	}

	/** The window as it is now, as screenshots/file (no chat cleared, nothing else touched); returns that path. */
	static String picture(Minecraft mc, File results, String file) {
		try {
			ScreenShotHelper.saveScreenshot(results, file, mc.displayWidth, mc.displayHeight, mc.getFramebuffer());
			return "screenshots/" + file;
		} catch (RuntimeException e) {
			return "none (" + e + ")";
		}
	}

	/** Threads, screen and connection into hang-threads.txt; returns its name. */
	static String dump(Minecraft mc, File results) {
		StringBuilder out = new StringBuilder();
		out.append("screen: ").append(mc.currentScreen == null ? "none" : mc.currentScreen.getClass().getName()).append('\n');
		out.append("client world: ").append(mc.theWorld != null).append(", client player: ").append(mc.thePlayer != null).append('\n');
		try {
			NetworkManager client = (NetworkManager) field(Minecraft.class, mc, "myNetworkManager", "field_71453_ak");
			out.append("client connection: ").append(describe(client)).append('\n');
			IntegratedServer server = mc.getIntegratedServer();
			out.append("integrated server: ").append(server == null ? "none" : "running " + server.isServerRunning()
					+ ", in its run loop " + server.serverIsInRunLoop() + ", players " + server.getCurrentPlayerCount()).append('\n');
			if (server != null) {
				NetworkSystem network = server.getNetworkSystem();
				List<?> managers = (List<?>) field(NetworkSystem.class, network, "networkManagers", "field_151272_f");
				synchronized (managers) {
					out.append("server connections: ").append(managers.size()).append('\n');
					for (Object manager : managers) {
						out.append("  ").append(describe((NetworkManager) manager)).append('\n');
					}
				}
			}
		} catch (Exception e) {
			out.append("connection state unreadable: ").append(e).append('\n');
		}
		out.append("\nthe connection's steps so far (TasTrace, also in loading-trace.txt):\n").append(TasTrace.text());
		out.append('\n');
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
		File file = new File(results, "hang-threads.txt");
		try {
			Files.write(file.toPath(), out.toString().getBytes(StandardCharsets.UTF_8));
		} catch (Exception e) {
			return "nowhere (" + e + ")";
		}
		return file.getName();
	}

	private static String describe(NetworkManager manager) {
		if (manager == null) {
			return "none";
		}
		try {
			Object channel = field(NetworkManager.class, manager, "channel", "field_150746_k");
			Object handler = manager.getNetHandler();
			return "channel " + (channel == null ? "null" : channel + (manager.isChannelOpen() ? " open" : " closed"))
					+ ", handler " + (handler == null ? "none" : handler.getClass().getSimpleName());
		} catch (Exception e) {
			return "unreadable (" + e + ")";
		}
	}

	private static Object field(Class<?> owner, Object target, String... names) throws Exception {
		for (String name : names) {
			try {
				Field field = owner.getDeclaredField(name);
				field.setAccessible(true);
				return field.get(target);
			} catch (NoSuchFieldException ignored) {
			}
		}
		throw new NoSuchFieldException(owner.getSimpleName() + "." + names[0]);
	}
}

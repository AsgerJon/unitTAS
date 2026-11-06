package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import cpw.mods.fml.client.FMLClientHandler;
import io.github.asgerjon.unittas.TasTrace;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiDisconnected;
import net.minecraft.client.gui.GuiDownloadTerrain;
import net.minecraft.client.gui.GuiMainMenu;
import net.minecraft.client.multiplayer.GuiConnecting;
import net.minecraft.client.multiplayer.ServerData;
import net.minecraft.client.resources.I18n;
import net.minecraft.util.IChatComponent;

import java.lang.reflect.Field;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.FutureTask;

/**
 * A client joining a dedicated server and leaving it (PROTOCOL.md 9.3; SPEC.md 11.3, step 3), as the multiplayer
 * screen's Direct Connect and the pause menu's Disconnect do. A client's own: given at its preInit (ClientHooks).
 * It joins 127.0.0.1 only: a test client is never sent out onto the network.
 */
final class JoinOps {

	/** The only address a test client joins. */
	static final String LOOPBACK = "127.0.0.1";
	/**
	 * The join guard: client ticks a client may stand at the connecting screen before its join is taken as dropped. A
	 * login over loopback takes a few ticks; the client's network gives up on a silent server only after 20 s.
	 */
	static final int DROPPED_TICKS = 200;
	/** How often a dropped join is tried again before it is given up. */
	static final int RETRIES = 1;
	/** What a dropped join is said as. */
	static final String DROPPED = "the server dropped the client's connection before its login (1.7.10's race: a"
		+ " connection the server's network tick lists before its channel is set is dropped, and the client waits for an"
		+ " answer that never comes): " + DROPPED_TICKS + " client ticks at the connecting screen";
	private static final String CONNECTING = GuiConnecting.class.getName();

	private JoinOps() {
	}

	static void bind(Probe probe) {
		probe.op("server.join").does(JoinOps::join);
		probe.op("server.leave").does(JoinOps::leave);
	}

	/** In a server's world, on the client: its player and world there, past the terrain screen, no world of its own. */
	static boolean inRemoteWorld(Minecraft mc) {
		return mc.thePlayer != null && mc.theWorld != null && !mc.isIntegratedServerRunning()
			&& !(mc.currentScreen instanceof GuiDownloadTerrain);
	}

	/**
	 * What the disconnected screen says: its title and its message, as a player reads them ("Failed to connect to the
	 * server: Connection refused: ..."). Its fields are found by what they hold, not by name.
	 */
	static String reason(GuiDisconnected screen) {
		String title = null;
		String message = null;
		for (Field field : GuiDisconnected.class.getDeclaredFields()) {
			try {
				field.setAccessible(true);
				Object value = field.get(screen);
				if (value instanceof String && title == null) {
					title = I18n.format((String) value);
				} else if (value instanceof IChatComponent && message == null) {
					message = ((IChatComponent) value).getUnformattedText();
				}
			} catch (IllegalAccessException | RuntimeException e) {
				// one field unread: the reason says what the other does
			}
		}
		if (title == null && message == null) {
			return "disconnected (the screen gave no reason)";
		}
		return title == null ? message : message == null ? title : title + ": " + message;
	}

	private static JsonElement join(Call call) throws ProbeException, InterruptedException {
		Probe probe = call.probe;
		Snapshot snapshot = probe.snapshot;
		String address = call.string("address", LOOPBACK);
		if (!LOOPBACK.equals(address)) {
			throw ProbeException.badRequest("address", "a test client joins a server on " + LOOPBACK + " only, not " + address);
		}
		long port = call.number("port", -1, 1, 65535);
		if (port < 0) {
			throw ProbeException.badRequest("port", "server.join needs the server's port");
		}
		long settle = call.number("settle_ticks", 40, 0, 72000);
		long maxSeconds = call.number("max_seconds", 180, 1, 3600);
		if (snapshot.joined != null) {
			throw new ProbeException("NotReady", "this client has joined " + snapshot.joined + " already",
				Json.object("joined", snapshot.joined));
		}
		Sides sides = Sides.get();
		// asked on the client thread, as it is now: the snapshot is a tick behind a request that follows another at once
		String busy;
		try {
			busy = sides.run(Side.CLIENT, () -> {
				Minecraft mc = Minecraft.getMinecraft();
				if (mc.isIntegratedServerRunning() || mc.theWorld != null) {
					return "in a world" + (mc.isIntegratedServerRunning() ? " of its own" : "");
				}
				return mc.currentScreen instanceof GuiConnecting ? "joining a server already" : null;
			}, Sides.STALL_SECONDS, null);
		} catch (Sides.Stalled stalled) {
			throw Ops.stalled(probe, stalled);
		} catch (ProbeException | InterruptedException | RuntimeException e) {
			throw e;
		} catch (Exception e) {
			throw new ProbeException("ProbeError", "server.join couldn't look at the client: " + e, null);
		}
		if (busy != null) {
			throw new ProbeException("NotReady", "a client joins a server from the title screen; it is " + busy,
				Json.object("state", snapshot.state, "screen", snapshot.screen));
		}
		String where = address + ":" + port;
		long started = System.currentTimeMillis();
		snapshot.disconnected = null;
		snapshot.changing = true;
		try {
			FutureTask<Void> connect = sides.post(Side.CLIENT, () -> {
				TasTrace.start();
				connect(where);
				return null;
			});
			long inSince = -1;
			long connectingSince = -1;
			int dropped = 0;
			long nextEvent = started;
			while (true) {
				failed(connect);
				long tick = sides.ticks(Side.CLIENT);
				if (!connect.isDone() || !CONNECTING.equals(snapshot.screen)) {
					connectingSince = -1;
				} else if (connectingSince < 0) {
					connectingSince = tick;
				} else if (tick - connectingSince >= DROPPED_TICKS) {
					// the join guard: decided by the client's ticks, never by the clock (SPEC.md 9.8)
					dropped++;
					probe.event("connection", Json.object("state", "dropped", "address", address, "port", port, "ms",
						System.currentTimeMillis() - started));
					if (dropped > RETRIES) {
						back(sides);
						throw new ProbeException("Disconnected", DROPPED + "; and again after one more try", Json.object(
							"reason", DROPPED, "address", address, "port", port, "trace", TasTrace.lines()));
					}
					call.warn(DROPPED + ": cancelled and joined again");
					connect = sides.post(Side.CLIENT, () -> {
						abort(Minecraft.getMinecraft());
						connect(where);
						return null;
					});
					connectingSince = -1;
					continue;
				}
				String refused = snapshot.disconnected;
				if (refused != null) {
					// the client is left at the title screen again, as it was asked from
					back(sides);
					snapshot.state = "menu";
					throw new ProbeException("Disconnected", "couldn't join " + where + ": " + refused, Json.object(
						"reason", refused, "address", address, "port", port, "trace", TasTrace.lines()));
				}
				long now = System.currentTimeMillis();
				if (connect.isDone() && snapshot.remote) {
					long ticks = sides.ticks(Side.CLIENT);
					if (inSince < 0) {
						inSince = ticks;
					}
					if (ticks - inSince >= settle) {
						break;
					}
				} else {
					inSince = -1;
				}
				if (now - started > maxSeconds * 1000L) {
					throw new ProbeException("TimedOut", "didn't join " + where + " within " + maxSeconds + " s", Json.object(
						"seconds", maxSeconds, "screen", snapshot.screen, "trace", TasTrace.lines()));
				}
				if (now >= nextEvent) {
					probe.event("connection", Json.object("state", "joining", "address", address, "port", port, "ms",
						now - started, "screen", snapshot.screen));
					nextEvent = now + 1000;
				}
				Thread.sleep(50);
			}
			snapshot.joined = where;
			snapshot.state = "world";
		} finally {
			snapshot.changing = false;
		}
		TasTrace.stop();
		long ms = System.currentTimeMillis() - started;
		probe.event("connection", Json.object("state", "joined", "address", address, "port", port, "ms", ms));
		return Json.object("load_ms", ms);
	}

	private static JsonElement leave(Call call) throws ProbeException, InterruptedException {
		Probe probe = call.probe;
		Snapshot snapshot = probe.snapshot;
		long maxSeconds = call.number("max_seconds", 60, 1, 3600);
		String was = snapshot.joined;
		if (was == null) {
			throw new ProbeException("NotReady", "this client has joined no server", Json.object("state", snapshot.state));
		}
		long started = System.currentTimeMillis();
		snapshot.changing = true;
		try {
			// as the pause menu's Disconnect: the server told, the world dropped, the title screen
			FutureTask<Void> step = Sides.get().post(Side.CLIENT, () -> {
				Worlds.close(Minecraft.getMinecraft());
				return null;
			});
			while (!(step.isDone() && snapshot.joined == null && snapshot.menu)) {
				failed(step);
				if (System.currentTimeMillis() - started > maxSeconds * 1000L) {
					throw new ProbeException("TimedOut", "didn't leave " + was + " within " + maxSeconds + " s",
						Json.object("seconds", maxSeconds, "screen", snapshot.screen));
				}
				Thread.sleep(50);
			}
			snapshot.state = "menu";
		} finally {
			snapshot.changing = false;
		}
		probe.refs.clear(Side.CLIENT, "its server (" + was + ") left");
		return Json.object("leave_ms", System.currentTimeMillis() - started);
	}

	/**
	 * As Direct Connect does: through FML, which readies its handshake for the play client first (a GuiConnecting made
	 * directly leaves FML's handshake waiting on nothing: a NullPointerException in waitForPlayClient). Its server list
	 * is made first, as the multiplayer screen makes it when it opens (connectToServer reads it). On the client thread.
	 */
	private static void connect(String where) {
		FMLClientHandler.instance().setupServerList();
		FMLClientHandler.instance().connectToServer(new GuiMainMenu(), new ServerData("unitTAS", where));
	}

	/**
	 * A join that isn't answered, cancelled as the connecting screen's Cancel does: no more tries from it, its
	 * connection closed. Its fields are found by what they hold. The screen is replaced next, so its own updates (which
	 * would show a disconnected screen) never run. On the client thread.
	 */
	private static void abort(Minecraft mc) {
		if (!(mc.currentScreen instanceof GuiConnecting)) {
			return;
		}
		for (Field field : GuiConnecting.class.getDeclaredFields()) {
			if (java.lang.reflect.Modifier.isStatic(field.getModifiers())) {
				continue;
			}
			try {
				field.setAccessible(true);
				if (field.getType() == boolean.class) {
					field.setBoolean(mc.currentScreen, true);
				} else if (net.minecraft.network.NetworkManager.class.isAssignableFrom(field.getType())) {
					Object manager = field.get(mc.currentScreen);
					if (manager != null) {
						((net.minecraft.network.NetworkManager) manager).closeChannel(
							new net.minecraft.util.ChatComponentText("unitTAS: a dropped join, tried again"));
					}
				}
			} catch (IllegalAccessException | RuntimeException e) {
				Probe.LOG.warn("unitTAS probe: couldn't cancel the dropped join's {}: {}", field.getName(), e.toString());
			}
		}
	}

	/** After a refused join: the title screen again, once the client has shown why. */
	private static void back(Sides sides) {
		sides.post(Side.CLIENT, () -> {
			abort(Minecraft.getMinecraft());
			Minecraft.getMinecraft().displayGuiScreen(new GuiMainMenu());
			return null;
		});
	}

	private static void failed(FutureTask<Void> step) throws ProbeException {
		if (!step.isDone()) {
			return;
		}
		try {
			step.get();
		} catch (ExecutionException e) {
			Throwable cause = e.getCause();
			throw new ProbeException("GameError", "the game failed to connect: " + cause, Json.object(
				"exception", cause == null ? null : cause.getClass().getName(), "trace", Probe.trace(cause == null ? e : cause)));
		} catch (java.util.concurrent.CancellationException | InterruptedException e) {
			throw new ProbeException("ProbeError", "the step to connect never ran", null);
		}
	}
}

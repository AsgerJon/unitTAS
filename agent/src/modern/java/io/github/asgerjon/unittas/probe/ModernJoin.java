package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.ConnectScreen;
import net.minecraft.client.gui.screens.DisconnectedScreen;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.TitleScreen;

import java.util.concurrent.ExecutionException;
import java.util.concurrent.FutureTask;

/**
 * A modern client joining a dedicated server and leaving it (PROTOCOL.md 9.3; SPEC.md 19.7 step 10c), as 1.7.10's
 * JoinOps has it: as the multiplayer screen's Direct Connect and the pause menu's Disconnect do, each version's calls
 * its Version's. It joins 127.0.0.1 only: a test client is never sent out onto the network. No join guard: a modern
 * server has no login race of 1.7.10's kind, and a join that never comes is the request's own limit (max_seconds).
 * A client's own: given by ModernHooks.register.
 */
final class ModernJoin {

	/** The only address a test client joins. */
	static final String LOOPBACK = "127.0.0.1";

	private ModernJoin() {
	}

	static void bind(Probe probe) {
		probe.op("server.join").does(ModernJoin::join);
		probe.op("server.leave").does(ModernJoin::leave);
	}

	/** In a server's world, on the client: its player and level there, past the loading screen, no world of its own. */
	static boolean inRemoteWorld(Minecraft mc, Screen screen) {
		return mc.player != null && mc.level != null && mc.getSingleplayerServer() == null
			&& !Version.levelLoading(screen);
	}

	/**
	 * The client's join bookkeeping at the end of its tick (ModernHooks.clientTickEnd), as 1.7.10's ClientHooks has it:
	 * whether it is in a server's world, what a disconnected screen says, and its leaving (left, kicked, or the server
	 * gone: the disconnected screen says which) as a connection event.
	 */
	static void ticked(Probe probe, Minecraft mc, Screen screen) {
		Snapshot snapshot = probe.snapshot;
		snapshot.remote = inRemoteWorld(mc, screen);
		if (screen instanceof DisconnectedScreen && snapshot.disconnected == null) {
			snapshot.disconnected = Version.disconnectReason(screen);
		}
		if (snapshot.joined != null && mc.level == null) {
			String was = snapshot.joined;
			snapshot.joined = null;
			String[] where = was.split(":", 2);
			probe.event("connection", Json.object("state", "left", "address", where[0], "port", Long.parseLong(where[1]),
				"reason", snapshot.disconnected));
		}
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
				Minecraft mc = Minecraft.getInstance();
				if (mc.getSingleplayerServer() != null || mc.level != null) {
					return "in a world" + (mc.getSingleplayerServer() != null ? " of its own" : "");
				}
				return Version.screen() instanceof ConnectScreen ? "joining a server already" : null;
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
				ModernTrace.start();
				Version.connect(address, (int) port);
				return null;
			});
			long inSince = -1;
			long nextEvent = started;
			while (true) {
				failed(connect);
				String refused = snapshot.disconnected;
				if (refused != null) {
					// the client is left at the title screen again, as it was asked from
					back(sides);
					snapshot.state = "menu";
					throw new ProbeException("Disconnected", "couldn't join " + where + ": " + refused, Json.object(
						"reason", refused, "address", address, "port", port, "trace", ModernTrace.lines()));
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
						"seconds", maxSeconds, "screen", snapshot.screen, "trace", ModernTrace.lines()));
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
		ModernTrace.stop();
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
			// as the pause menu's Disconnect: the server told, the world dropped, then the title screen
			FutureTask<Void> step = Sides.get().post(Side.CLIENT, () -> {
				Version.leaveServer();
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

	/** After a refused join: the title screen again, once the client has shown why. */
	private static void back(Sides sides) {
		sides.post(Side.CLIENT, () -> {
			Version.setScreen(new TitleScreen());
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

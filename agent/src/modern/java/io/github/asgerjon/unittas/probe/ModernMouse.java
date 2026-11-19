package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.player.LocalPlayer;

/**
 * mouse.rate (PROTOCOL.md 8.9; SPEC.md 19.7 step 12): the client's player's look turned at a rate, in degrees a tick,
 * every frame by that frame's share of game time, as a hand turns a mouse. The rate is kept here, on the client thread,
 * and applied right after the game's own mouse step each frame (the mouse.turned hook: MouseHandler.turnPlayer before
 * 1.21, handleAccumulatedMovement from it), and at each client tick's end up to that end, so the look at a tick's end
 * (what every answer and the server see) is the rate times the ticks, whatever the frame rate, and a new rate starts
 * where the old one ends, at the end of the tick its request runs in: none of a tick is lost between two rates. Each
 * turn goes through Entity.turn as the game's own mouse turns the player: given the degrees over its 0.15, so the turn
 * is exact in degrees, the pitch kept within straight up and down, and the last tick's rotation moved with it (what a
 * frame is drawn between). No sensitivity, no options file. It holds until the next mouse.rate; 0 and 0, player.look,
 * client.reset, a screen opening, and the world left or its player changed stop it, and it stays stopped (V37).
 */
final class ModernMouse {

	/** Entity.turn's degrees a unit: the game's own scale for the mouse's movement. */
	private static final double DEGREES_A_UNIT = 0.15;

	// the rate in force (degrees a tick; 0 and 0 for none), the player it turns, the game time (client ticks) it last
	// turned at, and the frames it has turned the look in: all on the client thread
	private static double yaw;
	private static double pitch;
	private static LocalPlayer turning;
	private static double turnedAt;
	private static long frames;

	private ModernMouse() {
	}

	static void bind(Probe probe) {
		probe.op("mouse.rate").does(ModernMouse::rate);
	}

	/**
	 * mouse.rate: the rate set, answered at once, in the tick it ran in, with the player's bearing as it is then: the
	 * tick, where it is, its look and its motion (what a controller steering every tick needs). Refused with a screen
	 * open (the mouse moves its cursor then) unless it is 0 and 0.
	 */
	private static JsonElement rate(Call call) throws ProbeException {
		Minecraft mc = Minecraft.getInstance();
		LocalPlayer player = mc.player;
		if (player == null || mc.level == null) {
			throw new ProbeException("NotReady", "mouse.rate needs a world", null);
		}
		double newYaw = degrees(call, "yaw");
		double newPitch = degrees(call, "pitch");
		boolean none = newYaw == 0.0 && newPitch == 0.0;
		Screen screen = Version.screen();
		if (screen != null && !none) {
			throw new ProbeException("NotReady", "mouse.rate turns the look with no screen open, and "
				+ Members.className(screen.getClass()) + " is: the mouse moves its cursor", null);
		}
		// the change, at this tick's end in game time: this tick counted (a step runs before its tick is counted,
		// Sides.ticked), no partial tick; the rate in force turns up to it first (the tick's end has, as a rule)
		double change = tickEnd();
		if (turning == player && screen == null) {
			turnTo(player, change);
		}
		stop();
		if (!none) {
			yaw = newYaw;
			pitch = newPitch;
			turning = player;
			turnedAt = change;
		}
		return Json.object("tick", Sides.get().ticks(Side.CLIENT), "pos", ModernValues.pos(player), "look",
			ModernValues.look(player), "motion", ModernValues.motion(player));
	}

	/** A rate's part: degrees a tick, a finite number. */
	private static double degrees(Call call, String name) throws ProbeException {
		JsonElement value = call.args.get(name);
		if (value == null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isNumber()) {
			throw ProbeException.badRequest(name, "mouse.rate needs yaw and pitch, in degrees a tick");
		}
		double degrees = value.getAsDouble();
		if (Double.isNaN(degrees) || Double.isInfinite(degrees)) {
			throw ProbeException.badRequest(name, name + " is a finite number of degrees a tick, not " + degrees);
		}
		return degrees;
	}

	/**
	 * The mouse.turned hook, after the game's own mouse step in each frame: the look turned by the rate, for the game
	 * time since the frame before (client ticks and the partial tick). A screen open, or another player or none (the
	 * world left, a respawn, another dimension), stops the rate first.
	 */
	static void frame() {
		LocalPlayer player = inForce();
		if (player != null && turnTo(player, Sides.get().ticks(Side.CLIENT) + Version.partialTick())) {
			frames++;
		}
	}

	/**
	 * At a client tick's end, before its steps run: the look turned up to that end, so it is the rate times the ticks
	 * there, whatever the frame rate. A screen open, or another player or none, stops the rate first.
	 */
	static void ticked() {
		LocalPlayer player = inForce();
		if (player != null) {
			turnTo(player, tickEnd());
		}
	}

	/** This client tick's end in game time, counted in client ticks: the tick counted, no partial tick. */
	private static double tickEnd() {
		return Sides.get().ticks(Side.CLIENT) + 1;
	}

	/**
	 * The player the rate turns, while it may: none (the rate stopped first) with a screen open, or with another
	 * player or none in the client (the world left, a respawn, another dimension).
	 */
	private static LocalPlayer inForce() {
		LocalPlayer player = turning;
		if (player == null) {
			return null;
		}
		Minecraft mc = Minecraft.getInstance();
		if (mc.player != player || mc.level == null || Version.screen() != null) {
			stop();
			return null;
		}
		return player;
	}

	/** The look turned by the rate for the game time from when it last turned to 'now'; whether it turned. */
	private static boolean turnTo(LocalPlayer player, double now) {
		double share = now - turnedAt;
		if (share <= 0.0) {
			return false;
		}
		turnedAt = now;
		player.turn(yaw * share / DEGREES_A_UNIT, pitch * share / DEGREES_A_UNIT);
		return true;
	}

	/** No rate: what 0 and 0, player.look and client.reset do. */
	static void stop() {
		yaw = 0.0;
		pitch = 0.0;
		turning = null;
		frames = 0;
	}

	/** The rate in force, as player.perceive says it: yaw and pitch in degrees a tick, and the frames it has turned. */
	static JsonObject report() {
		return Json.object("yaw", yaw, "pitch", pitch, "frames", frames);
	}
}

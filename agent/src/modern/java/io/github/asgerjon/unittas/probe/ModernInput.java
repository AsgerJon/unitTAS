package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.mojang.blaze3d.platform.InputConstants;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.player.LocalPlayer;

/**
 * The tests' input in 26.3 (PROTOCOL.md 8.9; SPEC.md 19.7 step 2), on the client thread, as 1.7.10's Input: looking,
 * the keys held, let go and pressed, the camera, and keys and text typed into the open screen. A key is a binding by its
 * name ("key.jump"), which stands for the key it is bound to, or a key by its code ({"code": n}): 26.3's codes are
 * SDL3's scancodes (InputConstants.KEY_*, space 44), where 1.7.10's are LWJGL's. As in 1.7.10, a key put down holds
 * every binding on it and presses each once. A screen is given a key as SDL3 gives it (its scancode, and its keycode:
 * the character for a key that types one, the scancode with bit 30 for the others), then the character it types.
 */
final class ModernInput {

	private ModernInput() {
	}

	static void bind(Probe probe) {
		// answered in the tick it ran in: the client's look is set at once, the server's copy follows with the client's
		// next movement, a tick behind, as a player's does (SPEC.md 19.7 step 12, V38)
		probe.op("player.look").does(ModernInput::look);
		probe.op("key.down").does(call -> {
			down(key(call));
			return new JsonObject();
		});
		probe.op("key.up").does(call -> {
			KeyMapping.set(key(call), false);
			return new JsonObject();
		});
		probe.op("key.tap").does(ModernInput::tapDown).settles(ModernInput::tapUp);
		probe.op("camera.set").does(ModernInput::camera).settles((call, value) -> ModernThings.waitClient(call, 2, value));
		probe.op("screen.type").does(ModernInput::type).settles(ModernInput::settle4);
		probe.op("screen.key").does(ModernInput::screenKey).settles(ModernInput::settle4);
	}

	private static JsonElement settle4(Call call, JsonElement value) throws ProbeException, InterruptedException {
		return ModernThings.waitClient(call, call.number("settle_ticks", 4, 0, 1200), value);
	}

	/**
	 * Turns the client player to look this way (degrees; yaw 0 is south, pitch 90 down), this tick and the last. A
	 * mouse.rate in force stops (ModernMouse).
	 */
	private static JsonElement look(Call call) throws ProbeException {
		LocalPlayer player = Minecraft.getInstance().player;
		if (player == null) {
			throw new ProbeException("NotReady", "player.look needs a world", null);
		}
		if (!call.has("yaw") || !call.has("pitch")) {
			throw ProbeException.badRequest("yaw", "player.look needs yaw and pitch, in degrees");
		}
		float yaw = (float) call.args.get("yaw").getAsDouble();
		float pitch = (float) call.args.get("pitch").getAsDouble();
		ModernMouse.stop();
		VersionCommon.setRot(player, yaw, pitch);
		player.yRotO = yaw;
		player.xRotO = pitch;
		return new JsonObject();
	}

	/** The key a request names: a binding's (by its name), or one by its SDL3 scancode. */
	private static InputConstants.Key key(Call call) throws ProbeException {
		JsonElement key = call.args.get("key");
		if (key != null && key.isJsonObject() && key.getAsJsonObject().has("code")) {
			return Version.rawKey(key.getAsJsonObject().get("code").getAsInt());
		}
		if (key == null || !key.isJsonPrimitive()) {
			throw ProbeException.badRequest("key", "key is a binding's name (\"key.jump\") or {\"code\": n}, n an SDL3"
				+ " scancode");
		}
		KeyMapping binding = Version.binding(key.getAsString());
		if (binding == null) {
			throw ProbeException.badRequest("key", "this game has no key binding " + key.getAsString());
		}
		// the key it is bound to, as the options file writes it ("key.keyboard.w")
		return InputConstants.getKey(binding.saveString());
	}

	/** Puts the key down, as pressing it does: every binding on it held, and pressed once. */
	private static void down(InputConstants.Key key) {
		KeyMapping.set(key, true);
		KeyMapping.click(key);
	}

	private static JsonElement tapDown(Call call) throws ProbeException {
		InputConstants.Key key = key(call);
		// the key, kept for the rest: its type (a keyboard's, a mouse's) and its value
		call.mark = ((long) key.getType().ordinal() << 32) | (key.getValue() & 0xffffffffL);
		down(key);
		return new JsonObject();
	}

	/** key.tap's rest: the ticks held, then the key let go (also when cancelled meanwhile), then one tick more. */
	private static JsonElement tapUp(Call call, JsonElement value) throws ProbeException, InterruptedException {
		long held = call.number("ticks", 1, 1, 72000);
		InputConstants.Key key = InputConstants.Type.values()[(int) (call.mark >>> 32)].getOrCreate((int) call.mark);
		try {
			ModernThings.waitClient(call, held, value);
		} finally {
			Sides.get().post(Side.CLIENT, () -> {
				KeyMapping.set(key, false);
				return null;
			});
		}
		return ModernThings.waitClient(call, 1, value);
	}

	/** The camera: 0 first person, 1 third person from behind, 2 from the front. */
	private static JsonElement camera(Call call) throws ProbeException {
		long view = call.number("view", -1, 0, 2);
		if (view < 0) {
			throw ProbeException.badRequest("view", "camera.set needs the view: 0, 1 or 2");
		}
		Version.setCamera((int) view);
		return new JsonObject();
	}

	// ---------------------------------------------------------------- typing into a screen

	private static Screen openScreen() throws ProbeException {
		Screen screen = Version.screen();
		if (screen == null) {
			throw new ProbeException("NotReady", "no screen is open to type into", null);
		}
		return screen;
	}

	/** Runs the screen's own handling; what it throws is the screen's failure, a GameError. */
	private static void typed(Screen screen, Runnable handling) throws ProbeException {
		try {
			handling.run();
		} catch (RuntimeException | Error e) {
			throw new ProbeException("GameError", Members.className(screen.getClass()) + " threw " + e, Json.object(
				"exception", Members.className(e.getClass()), "trace", Probe.trace(e)));
		}
	}

	private static JsonElement type(Call call) throws ProbeException {
		Screen screen = openScreen();
		String text = call.string("text", null);
		if (text == null) {
			throw ProbeException.badRequest("text", "screen.type needs the text");
		}
		for (int character : text.codePoints().toArray()) {
			typed(screen, () -> Version.charTyped(screen, character));
		}
		return new JsonObject();
	}

	private static JsonElement screenKey(Call call) throws ProbeException {
		Screen screen = openScreen();
		String name = call.string("key", null);
		int[] key = name == null ? null : Version.portableKey(name.toLowerCase(java.util.Locale.ROOT));
		if (key == null) {
			throw ProbeException.badRequest("key", "key is a letter, a digit, space, enter, escape, tab, backspace, delete,"
				+ " up, down, left, right, home, end, page_up, page_down or f1 to f12, not " + name);
		}
		typed(screen, () -> {
			Version.keyPressed(screen, key[0], key[1]);
			if (key[2] != 0) {
				Version.charTyped(screen, key[2]);
			}
		});
		return new JsonObject();
	}
}

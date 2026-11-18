package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.mojang.blaze3d.platform.InputConstants;
import com.mojang.blaze3d.platform.NativeImage;
import com.mojang.serialization.DynamicOps;
import com.mojang.serialization.JsonOps;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.Screenshot;
import net.minecraft.client.gui.components.ChatComponent;
import net.minecraft.client.gui.screens.ChatScreen;
import net.minecraft.client.gui.screens.ConnectScreen;
import net.minecraft.client.gui.screens.DisconnectedScreen;
import net.minecraft.client.gui.screens.LevelLoadingScreen;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.client.input.CharacterEvent;
import net.minecraft.client.input.KeyEvent;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.multiplayer.ServerData;
import net.minecraft.client.multiplayer.chat.GuiMessageSource;
import net.minecraft.client.multiplayer.resolver.ServerAddress;
import net.minecraft.client.resources.sounds.SoundInstance;
import net.minecraft.client.sounds.SoundManager;
import net.minecraft.network.DisconnectionDetails;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.ComponentSerialization;
import net.minecraft.world.entity.player.Player;
import org.lwjgl.sdl.SDLMouse;

import java.util.function.Consumer;

/**
 * What 26.3 does its own way, for the probe's code shared by the versions (agent/src/modern/java; SPEC.md 19.7 step
 * 6c): each version has a Version of its own with these same methods, compiled with the shared code against that
 * version's classes, so a version that lacks one doesn't build. What differs widely (the view, the looks, the worlds)
 * is in the version's own classes instead (V26View, V26Looks, V26Worlds).
 */
final class Version {

	private Version() {
	}

	// ---------------------------------------------------------------- the game

	/** The probe's port, as its hello says it. */
	static String port() {
		return VersionName.port();
	}

	/** The game's version, as it says itself. */
	static String minecraft() {
		return VersionName.minecraft();
	}

	/** The version's own operations, which differ too widely to share: the view and the looks. */
	static void bindOwn(Probe probe) {
		V26View.bind(probe);
		V26Looks.bind(probe);
	}

	/** The version's worlds: the core's WorldOps on its calls. */
	static GameWorlds worlds() {
		return new V26Worlds();
	}

	/** A chat line's kind from the hooked addMessage's arguments: a player's (chat), or the game's (system). */
	static String chatKind(Object[] arguments) {
		return arguments[2] == GuiMessageSource.PLAYER ? "chat" : "system";
	}

	/** The version's own hooks, which the shared entry passes on: 26.3 has none (its render states keep the frame). */
	static Object hook(String id, Object self, Object[] arguments, Object pass) {
		throw new IllegalArgumentException("the probe knows no hook " + id);
	}

	// ---------------------------------------------------------------- screens and the HUD

	static Screen screen() {
		return Minecraft.getInstance().gui.screen();
	}

	static void setScreen(Screen screen) {
		Minecraft.getInstance().gui.setScreen(screen);
	}

	/** Whether a loading overlay is up (the game's start, a resource reload). */
	static boolean loading() {
		return Minecraft.getInstance().gui.overlay() != null;
	}

	static ChatComponent chat() {
		return Minecraft.getInstance().gui.hud.getChat();
	}

	static boolean hudHidden() {
		return Minecraft.getInstance().gui.hud.isHidden();
	}

	/** The HUD hidden if shown, shown if hidden (F1's). */
	static void toggleHud() {
		Minecraft.getInstance().gui.hud.toggle();
	}

	/** The chat screen, opened with that text in its box. */
	static ChatScreen chatScreen(String text) {
		return new ChatScreen(text, false);
	}

	/** Whether the window holds the pointer (SDL3's relative mouse mode, which the game's grab sets). */
	static boolean pointerGrabbed() {
		Minecraft mc = Minecraft.getInstance();
		return SDLMouse.SDL_GetWindowRelativeMouseMode(mc.getWindow().handle());
	}

	/** The frame as the screen shows it; 26.3 hands it back a frame or two later, on the client thread. */
	static void screenshot(Consumer<NativeImage> taken) {
		Screenshot.takeScreenshot(Minecraft.getInstance().gameRenderer.mainRenderTarget(), taken::accept);
	}

	// ---------------------------------------------------------------- ids

	// ---------------------------------------------------------------- sounds

	static String soundId(SoundInstance sound) {
		return sound.getIdentifier().toString();
	}

	/** Whether the game has the sound: resolved as the engine does (getOrResolve, which the engine then reuses). */
	static boolean soundKnown(SoundInstance sound, SoundManager manager) {
		return sound.getOrResolve(manager) != null;
	}

	// ---------------------------------------------------------------- the inventory

	/** The game's own pick of what the crosshair meets, made afresh for the look as it is now (Minecraft's, private). */
	static void pick(float partialTick) {
		Members.call(Picking.PICK, Minecraft.getInstance(), partialTick);
	}

	private static final class Picking {

		static final java.lang.reflect.Method PICK = Members.method(Minecraft.class, "pick", float.class);
	}

	// ---------------------------------------------------------------- items' data, chat, reach, results

	/** A chat line as the game's own JSON, by its registries when a world is open. */
	static String chatJson(Component message) {
		Minecraft mc = Minecraft.getInstance();
		DynamicOps<JsonElement> ops = mc.level == null ? JsonOps.INSTANCE
			: mc.level.registryAccess().createSerializationContext(JsonOps.INSTANCE);
		return ComponentSerialization.CODEC.encodeStart(ops, message).result().map(JsonElement::toString).orElse("");
	}

	/** How far the player reaches a block: its attribute's, as the game's pick takes it. */
	static double blockReach(Player player) {
		return player.blockInteractionRange();
	}

	/** How far the player reaches an entity: its attribute's, as the game's pick takes it. */
	static double entityReach(Player player) {
		return player.entityInteractionRange();
	}

	// ---------------------------------------------------------------- the world, players and entities

	// ---------------------------------------------------------------- joining a server

	/**
	 * Joins a server as the multiplayer screen's Direct Connect does (ConnectScreen.startConnecting), the title screen
	 * its parent, where a refused join's screen leads back to. On the client thread.
	 */
	static void connect(String host, int port) {
		ConnectScreen.startConnecting(new TitleScreen(), Minecraft.getInstance(), new ServerAddress(host, port),
			new ServerData("unitTAS", host + ":" + port, ServerData.Type.OTHER), false, null);
	}

	/**
	 * Leaves the server as the pause menu's Disconnect does (disconnectFromWorld), then for the title screen, where a
	 * join starts (the game's own goes to its server list). On the client thread.
	 */
	static void leaveServer() {
		Minecraft.getInstance().disconnectFromWorld(ClientLevel.DEFAULT_QUIT_MESSAGE);
		setScreen(new TitleScreen());
	}

	/** What a disconnected screen says, as a player reads it: its title, then its reason. */
	static String disconnectReason(Screen screen) {
		DisconnectionDetails details = Members.get(Disconnecting.DETAILS, screen);
		return screen.getTitle().getString() + ": " + details.reason().getString();
	}

	/** Found at the first disconnected screen read, once the probe has its names. */
	private static final class Disconnecting {

		static final java.lang.reflect.Field DETAILS = Members.field(DisconnectedScreen.class, "details");
	}

	/** Whether the screen is the one a client shows while it receives a level (26.3 has one for both kinds). */
	static boolean levelLoading(Screen screen) {
		return screen instanceof LevelLoadingScreen;
	}

	// ---------------------------------------------------------------- input

	/** A raw key by its code: SDL3's scancode. */
	static InputConstants.Key rawKey(int code) {
		return InputConstants.Type.KEYBOARD.getOrCreate(code);
	}

	/** A binding by its name (key.jump); null for none. */
	static KeyMapping binding(String name) {
		return KeyMapping.get(name);
	}

	/** A screen given a character, as SDL3 gives one. */
	static void charTyped(Screen screen, int character) {
		screen.charTyped(new CharacterEvent(character));
	}

	/** A screen given a key, as SDL3 gives one: its scancode and its keycode. */
	static void keyPressed(Screen screen, int scancode, int keycode) {
		screen.keyPressed(new KeyEvent(scancode, keycode, 0));
	}

	/**
	 * A key by its portable name, as a screen is given it: [its scancode, its keycode (SDL3's: the character for a
	 * key that types one, the scancode with bit 30 for the rest), the character it types or 0]; null for a name not
	 * known.
	 */
	static int[] portableKey(String name) {
		if (name.length() == 1) {
			char c = name.charAt(0);
			if (c >= 'a' && c <= 'z') {
				return new int[] {InputConstants.KEY_A + (c - 'a'), c, c};
			}
			if (c >= '1' && c <= '9') {
				return new int[] {InputConstants.KEY_1 + (c - '1'), c, c};
			}
			if (c == '0') {
				return new int[] {InputConstants.KEY_0, c, c};
			}
			return null;
		}
		switch (name) {
			case "space": return new int[] {InputConstants.KEY_SPACE, ' ', ' '};
			case "enter": return new int[] {InputConstants.KEY_RETURN, '\r', 0};
			case "escape": return new int[] {InputConstants.KEY_ESCAPE, 27, 0};
			case "tab": return new int[] {InputConstants.KEY_TAB, '\t', 0};
			case "backspace": return new int[] {InputConstants.KEY_BACKSPACE, '\b', 0};
			case "delete": return new int[] {InputConstants.KEY_DELETE, 127, 0};
			case "up": return new int[] {InputConstants.KEY_UP, sdl(InputConstants.KEY_UP), 0};
			case "down": return new int[] {InputConstants.KEY_DOWN, sdl(InputConstants.KEY_DOWN), 0};
			case "left": return new int[] {InputConstants.KEY_LEFT, sdl(InputConstants.KEY_LEFT), 0};
			case "right": return new int[] {InputConstants.KEY_RIGHT, sdl(InputConstants.KEY_RIGHT), 0};
			case "home": return new int[] {InputConstants.KEY_HOME, sdl(InputConstants.KEY_HOME), 0};
			case "end": return new int[] {InputConstants.KEY_END, sdl(InputConstants.KEY_END), 0};
			case "page_up": return new int[] {InputConstants.KEY_PAGEUP, sdl(InputConstants.KEY_PAGEUP), 0};
			case "page_down": return new int[] {InputConstants.KEY_PAGEDOWN, sdl(InputConstants.KEY_PAGEDOWN), 0};
			default:
				break;
		}
		if (name.matches("f([1-9]|1[0-2])")) {
			int scancode = InputConstants.KEY_F1 + Integer.parseInt(name.substring(1)) - 1;
			return new int[] {scancode, sdl(scancode), 0};
		}
		return null;
	}

	/** SDL3's keycode for a key that types nothing: its scancode with bit 30 (SDLK_SCANCODE_MASK). */
	private static int sdl(int scancode) {
		return scancode | (1 << 30);
	}

	// ---------------------------------------------------------------- containers
}

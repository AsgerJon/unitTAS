package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.mojang.blaze3d.platform.InputConstants;
import com.mojang.blaze3d.platform.NativeImage;
import com.mojang.serialization.DynamicOps;
import com.mojang.serialization.JsonOps;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import net.minecraft.client.CameraType;
import net.minecraft.client.GuiMessageTag;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.Screenshot;
import net.minecraft.client.gui.components.ChatComponent;
import net.minecraft.client.gui.screens.ChatScreen;
import net.minecraft.client.gui.screens.ConnectScreen;
import net.minecraft.client.gui.screens.DisconnectedScreen;
import net.minecraft.client.gui.screens.LevelLoadingScreen;
import net.minecraft.client.gui.screens.ReceivingLevelScreen;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.client.gui.screens.inventory.CreativeModeInventoryScreen;
import net.minecraft.client.multiplayer.ClientPacketListener;
import net.minecraft.client.multiplayer.ServerData;
import net.minecraft.client.multiplayer.resolver.ServerAddress;
import net.minecraft.client.resources.sounds.SoundInstance;
import net.minecraft.client.sounds.SoundManager;
import net.minecraft.network.DisconnectionDetails;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.ComponentSerialization;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.util.FormattedCharSequence;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.ClickType;
import org.lwjgl.glfw.GLFW;

/**
 * What 1.21.1 does its own way, for the probe's code shared by the versions (agent/src/modern/java; SPEC.md 19.7 step
 * 6c): the same methods as every version's Version, compiled with the shared code against 1.21.1's classes (in
 * Mojang's names, from its stubs; renamed to the obfuscated ones as the probe loads). 1.21.1 keeps its screen on
 * Minecraft and its HUD's hiding in the options, has ResourceLocation for ids, GLFW for input, plain NBT for an
 * entity's data, and names a click's mode ClickType.
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
		V1_21_1View.bind(probe);
		V1_21_1Looks.bind(probe);
	}

	/** The version's worlds: the core's WorldOps on its calls. */
	static GameWorlds worlds() {
		return new V1_21_1Worlds();
	}

	/**
	 * A chat line's kind from the hooked addMessage's arguments (the line, its signature, its tag): the game's
	 * (system: its own tag, which addMessage(Component) gives), or a player's (chat: no tag, or a chat tag).
	 */
	static String chatKind(Object[] arguments) {
		Object tag = arguments[2];
		return tag == GuiMessageTag.system() || tag == GuiMessageTag.systemSinglePlayer() ? "system" : "chat";
	}

	/**
	 * The version's own hooks, which the shared entry passes on (its hooks file's view.frame and view.compiled: the
	 * view's frame and its sections' builds, which 1.21.1 keeps no state of). A BEFORE hook: the pass mark goes on.
	 */
	static Object hook(String id, Object self, Object[] arguments, Object pass) {
		switch (id) {
			case "view.frame":
				V1_21_1View.frame(arguments);
				return pass;
			case "view.compiled":
				V1_21_1View.compiled(arguments[0]);
				return pass;
			default:
				throw new IllegalArgumentException("the probe knows no hook " + id);
		}
	}

	// ---------------------------------------------------------------- screens and the HUD

	static Screen screen() {
		return Minecraft.getInstance().screen;
	}

	static void setScreen(Screen screen) {
		Minecraft.getInstance().setScreen(screen);
	}

	/** Whether a loading overlay is up (the game's start, a resource reload). */
	static boolean loading() {
		return Minecraft.getInstance().getOverlay() != null;
	}

	static ChatComponent chat() {
		return Minecraft.getInstance().gui.getChat();
	}

	static boolean hudHidden() {
		return Minecraft.getInstance().options.hideGui;
	}

	/** The HUD hidden if shown, shown if hidden (F1's: the options' hideGui). */
	static void toggleHud() {
		Minecraft mc = Minecraft.getInstance();
		mc.options.hideGui = !mc.options.hideGui;
	}

	/** The chat screen, opened with that text in its box. */
	static ChatScreen chatScreen(String text) {
		return new ChatScreen(text);
	}

	/** Whether the window holds the pointer (GLFW's cursor disabled, which the game's grab sets). */
	static boolean pointerGrabbed() {
		return GLFW.glfwGetInputMode(Minecraft.getInstance().getWindow().getWindow(), GLFW.GLFW_CURSOR)
			== GLFW.GLFW_CURSOR_DISABLED;
	}

	/** The frame as the screen shows it; 1.21.1 reads it at once, on the client thread. */
	static void screenshot(Consumer<NativeImage> taken) {
		taken.accept(Screenshot.takeScreenshot(Minecraft.getInstance().getMainRenderTarget()));
	}

	// ---------------------------------------------------------------- ids

	// ---------------------------------------------------------------- sounds

	static String soundId(SoundInstance sound) {
		return sound.getLocation().toString();
	}

	/**
	 * Whether the game has the sound, the sound resolved so its volume and pitch read. 1.21.1's resolve picks a variant
	 * at random each time, so the probe hears a sound after the engine played it (its sound.play hook is AFTER) and
	 * resolves it only where the engine didn't (no sound engine loaded), when that changes nothing it played.
	 */
	static boolean soundKnown(SoundInstance sound, SoundManager manager) {
		if (sound.getSound() == null) {
			sound.resolve(manager);
		}
		return manager.getSoundEvent(sound.getLocation()) != null;
	}

	// ---------------------------------------------------------------- the inventory

	/** The game's own pick of what the crosshair meets, made afresh for the look as it is now (GameRenderer's). */
	static void pick(float partialTick) {
		Minecraft.getInstance().gameRenderer.pick(partialTick);
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
	 * Leaves the server as the pause menu's Disconnect does for a server not the client's own (no saving screen),
	 * then for the title screen, where a join starts (the game's own goes to its server list). On the client thread.
	 */
	static void leaveServer() {
		Minecraft mc = Minecraft.getInstance();
		if (mc.level != null) {
			mc.level.disconnect();
		}
		mc.disconnect();
		mc.setScreen(new TitleScreen());
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

	/** Whether the screen is one a client shows while it receives a level: its own world's, or a server's. */
	static boolean levelLoading(Screen screen) {
		return screen instanceof LevelLoadingScreen || screen instanceof ReceivingLevelScreen;
	}

	// ---------------------------------------------------------------- input

	/** A raw key by its code: GLFW's key code. */
	static InputConstants.Key rawKey(int code) {
		return InputConstants.Type.KEYSYM.getOrCreate(code);
	}

	/** A binding by its name (key.jump); null for none. KeyMapping's map of them is private in 1.21.1. */
	static KeyMapping binding(String name) {
		Map<String, KeyMapping> all = Members.get(Bindings.ALL, null);
		return all.get(name);
	}

	/** Found at the first binding asked for, once the probe has its names (a Version is used before that). */
	private static final class Bindings {

		static final java.lang.reflect.Field ALL = Members.field(KeyMapping.class, "ALL");
	}

	/** A screen given a character, as GLFW gives one. */
	static void charTyped(Screen screen, int character) {
		screen.charTyped((char) character, 0);
	}

	/** A screen given a key, as GLFW gives one: its key code and its scancode. */
	static void keyPressed(Screen screen, int key, int scancode) {
		screen.keyPressed(key, scancode, 0);
	}

	/**
	 * A key by its portable name, as a screen is given it: [its GLFW key code, its scancode (the platform's, as GLFW
	 * says it), the character it types or 0]; null for a name not known.
	 */
	static int[] portableKey(String name) {
		if (name.length() == 1) {
			char c = name.charAt(0);
			if (c >= 'a' && c <= 'z') {
				return glfw(InputConstants.KEY_A + (c - 'a'), c);
			}
			if (c >= '1' && c <= '9') {
				return glfw(InputConstants.KEY_1 + (c - '1'), c);
			}
			if (c == '0') {
				return glfw(InputConstants.KEY_0, c);
			}
			return null;
		}
		switch (name) {
			case "space": return glfw(InputConstants.KEY_SPACE, ' ');
			case "enter": return glfw(InputConstants.KEY_RETURN, 0);
			case "escape": return glfw(InputConstants.KEY_ESCAPE, 0);
			case "tab": return glfw(InputConstants.KEY_TAB, 0);
			case "backspace": return glfw(InputConstants.KEY_BACKSPACE, 0);
			case "delete": return glfw(InputConstants.KEY_DELETE, 0);
			case "up": return glfw(InputConstants.KEY_UP, 0);
			case "down": return glfw(InputConstants.KEY_DOWN, 0);
			case "left": return glfw(InputConstants.KEY_LEFT, 0);
			case "right": return glfw(InputConstants.KEY_RIGHT, 0);
			case "home": return glfw(InputConstants.KEY_HOME, 0);
			case "end": return glfw(InputConstants.KEY_END, 0);
			case "page_up": return glfw(InputConstants.KEY_PAGEUP, 0);
			case "page_down": return glfw(InputConstants.KEY_PAGEDOWN, 0);
			default:
				break;
		}
		if (name.matches("f([1-9]|1[0-2])")) {
			return glfw(InputConstants.KEY_F1 + Integer.parseInt(name.substring(1)) - 1, 0);
		}
		return null;
	}

	private static int[] glfw(int key, int character) {
		return new int[] {key, GLFW.glfwGetKeyScancode(key), character};
	}

	// ---------------------------------------------------------------- containers

	// ---- what 1.16.1 does another way (SPEC.md 19.7 step 11b): the shared code asks each version

	/** The camera's view: 0 first person, 1 behind, 2 in front. */
	static int camera() {
		return Minecraft.getInstance().options.getCameraType().ordinal();
	}

	/** The camera's view, set (0, 1 or 2, as camera() says it). */
	static void setCamera(int view) {
		Minecraft.getInstance().options.setCameraType(CameraType.values()[view]);
	}

	/** The creative inventory's screen, as its key opens it. */
	static Screen creativeScreen(Minecraft mc) {
		return new CreativeModeInventoryScreen(mc.player, mc.player.connection.enabledFeatures(),
			mc.options.operatorItemsTab().get());
	}

	/** The chat's command usage lines (CommandSuggestions' own) as plain text. */
	static List<String> usageLines(List<?> lines) {
		List<String> plain = new ArrayList<>();
		for (Object each : lines) {
			StringBuilder line = new StringBuilder();
			((FormattedCharSequence) each).accept((index, style, codePoint) -> {
				line.appendCodePoint(codePoint);
				return true;
			});
			plain.add(line.toString());
		}
		return plain;
	}

	/** A line sent as the chat sends it: a command as one, slash and all. */
	static void sendChat(ClientPacketListener connection, String text) {
		if (text.startsWith("/")) {
			connection.sendCommand(text.substring(1));
		} else {
			connection.sendChat(text);
		}
	}

	/** The chat line the hooked chat.line method was given (its first argument). */
	static Component chatLine(Object[] arguments) {
		return (Component) arguments[0];
	}
}

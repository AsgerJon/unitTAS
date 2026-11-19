package io.github.asgerjon.unittas.probe;

import com.mojang.blaze3d.pipeline.RenderTarget;
import com.mojang.blaze3d.platform.InputConstants;
import com.mojang.blaze3d.platform.NativeImage;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import net.minecraft.ChatFormatting;
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
import net.minecraft.client.multiplayer.MultiPlayerGameMode;
import net.minecraft.client.multiplayer.ServerData;
import net.minecraft.client.renderer.chunk.ChunkRenderDispatcher;
import net.minecraft.client.resources.sounds.SoundInstance;
import net.minecraft.client.sounds.SoundManager;
import net.minecraft.network.chat.ChatType;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.ClickType;
import org.lwjgl.glfw.GLFW;

/**
 * What 1.16.1 does its own way, for the probe's code shared by the versions (agent/src/modern/java; SPEC.md 19.7 step
 * 6c): the same methods as every version's Version, compiled with the shared code against 1.16.1's classes (in
 * Mojang's names, from its stubs; renamed to the obfuscated ones as the probe loads). 1.16.1 keeps its screen on
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
		V1_16_1View.bind(probe);
		V1_16_1Looks.bind(probe);
	}

	/** The version's worlds: the core's WorldOps on its calls. */
	static GameWorlds worlds() {
		return new V1_16_1Worlds();
	}

	/**
	 * A chat line's kind from the hooked Gui.handleChat's arguments (its type, the line, its sender): a player's (chat:
	 * ChatType.CHAT), or the game's (system: SYSTEM). 1.16.1's lines have no tags.
	 */
	static String chatKind(Object[] arguments) {
		return arguments[0] == ChatType.CHAT ? "chat" : "system";
	}

	/**
	 * The version's own hooks, which the shared entry passes on (its hooks file's view.frame and view.compiled: the
	 * view's frame and its sections' builds, which 1.16.1 keeps no state of). A BEFORE hook: the pass mark goes on.
	 */
	static Object hook(String id, Object self, Object[] arguments, Object pass) {
		switch (id) {
			case "view.frame":
				V1_16_1View.frame(arguments);
				return pass;
			case "view.compiled":
				V1_16_1View.compiling((ChunkRenderDispatcher.RenderChunk) self);
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

	/** The frame as the screen shows it; 1.16.1 reads it at once, on the client thread, at the window's size. */
	static void screenshot(Consumer<NativeImage> taken) {
		RenderTarget target = Minecraft.getInstance().getMainRenderTarget();
		taken.accept(Screenshot.takeScreenshot(target.width, target.height, target));
	}

	// ---------------------------------------------------------------- ids

	// ---------------------------------------------------------------- sounds

	static String soundId(SoundInstance sound) {
		return sound.getLocation().toString();
	}

	/**
	 * Whether the game has the sound, the sound resolved so its volume and pitch read. 1.16.1's resolve picks a variant
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

	/**
	 * How far the game is into the tick after the last one counted, 0 to 1, as this frame is drawn.
	 * Minecraft.getFrameTime's: its timer's. With the client's ticks, mouse.rate's clock (ModernMouse).
	 */
	static float partialTick() {
		return Minecraft.getInstance().getFrameTime();
	}

	/** The game's own pick of what the crosshair meets, made afresh for the look as it is now (GameRenderer's). */
	static void pick(float partialTick) {
		Minecraft.getInstance().gameRenderer.pick(partialTick);
	}

	// ---------------------------------------------------------------- items' data, chat, reach, results

	/** A chat line as the game's own JSON. */
	static String chatJson(Component message) {
		return Component.Serializer.toJson(message);
	}

	/**
	 * How far the player reaches a block: its game mode's pick range (4.5; 5 in creative), as 1.16.1's pick takes it.
	 * The player is the client's own, whose game mode it is.
	 */
	static double blockReach(Player player) {
		return Minecraft.getInstance().gameMode.getPickRange();
	}

	/**
	 * How far the player reaches an entity, as 1.16.1's pick takes it: 3 blocks, or in creative (its far pick range) as
	 * far as the block pick reaches, where its ray ends.
	 */
	static double entityReach(Player player) {
		MultiPlayerGameMode mode = Minecraft.getInstance().gameMode;
		return mode.hasFarPickRange() ? mode.getPickRange() : 3.0;
	}

	// ---------------------------------------------------------------- the world, players and entities

	// ---------------------------------------------------------------- joining a server

	/**
	 * Joins a server as the multiplayer screen's Direct Connect does (1.16.1: a ConnectScreen of the server's data,
	 * which connects as it is made), the title screen its parent, where a refused join's screen leads back to. On the
	 * client thread.
	 */
	static void connect(String host, int port) {
		Minecraft mc = Minecraft.getInstance();
		mc.setScreen(new ConnectScreen(new TitleScreen(), mc, new ServerData("unitTAS", host + ":" + port, false)));
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
		mc.clearLevel();
		mc.setScreen(new TitleScreen());
	}

	/** What a disconnected screen says, as a player reads it: its title, then its reason. */
	static String disconnectReason(Screen screen) {
		Component reason = Members.get(Disconnecting.REASON, screen);
		return screen.getTitle().getString() + ": " + reason.getString();
	}

	/** Found at the first disconnected screen read, once the probe has its names. */
	private static final class Disconnecting {

		static final java.lang.reflect.Field REASON = Members.field(DisconnectedScreen.class, "reason");
	}

	/** Whether the screen is one a client shows while it receives a level: its own world's, or a server's. */
	static boolean levelLoading(Screen screen) {
		return screen instanceof LevelLoadingScreen || screen instanceof ReceivingLevelScreen;
	}

	// ---------------------------------------------------------------- input

	/** A raw key by its code: GLFW's key code (1.16.1's InputConstants names no keys: GLFW's own constants below). */
	static InputConstants.Key rawKey(int code) {
		return InputConstants.Type.KEYSYM.getOrCreate(code);
	}

	/** A binding by its name (key.jump); null for none. KeyMapping's map of them is private in 1.16.1. */
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
				return glfw(GLFW.GLFW_KEY_A + (c - 'a'), c);
			}
			if (c >= '1' && c <= '9') {
				return glfw(GLFW.GLFW_KEY_1 + (c - '1'), c);
			}
			if (c == '0') {
				return glfw(GLFW.GLFW_KEY_0, c);
			}
			return null;
		}
		switch (name) {
			case "space": return glfw(GLFW.GLFW_KEY_SPACE, ' ');
			case "enter": return glfw(GLFW.GLFW_KEY_ENTER, 0);
			case "escape": return glfw(GLFW.GLFW_KEY_ESCAPE, 0);
			case "tab": return glfw(GLFW.GLFW_KEY_TAB, 0);
			case "backspace": return glfw(GLFW.GLFW_KEY_BACKSPACE, 0);
			case "delete": return glfw(GLFW.GLFW_KEY_DELETE, 0);
			case "up": return glfw(GLFW.GLFW_KEY_UP, 0);
			case "down": return glfw(GLFW.GLFW_KEY_DOWN, 0);
			case "left": return glfw(GLFW.GLFW_KEY_LEFT, 0);
			case "right": return glfw(GLFW.GLFW_KEY_RIGHT, 0);
			case "home": return glfw(GLFW.GLFW_KEY_HOME, 0);
			case "end": return glfw(GLFW.GLFW_KEY_END, 0);
			case "page_up": return glfw(GLFW.GLFW_KEY_PAGE_UP, 0);
			case "page_down": return glfw(GLFW.GLFW_KEY_PAGE_DOWN, 0);
			default:
				break;
		}
		if (name.matches("f([1-9]|1[0-2])")) {
			return glfw(GLFW.GLFW_KEY_F1 + Integer.parseInt(name.substring(1)) - 1, 0);
		}
		return null;
	}

	private static int[] glfw(int key, int character) {
		return new int[] {key, GLFW.glfwGetKeyScancode(key), character};
	}

	// ---------------------------------------------------------------- containers

	// ---- what 1.16.1 does another way (SPEC.md 19.7 step 11b): the shared code asks each version

	/** The camera's view: 0 first person, 1 behind, 2 in front (1.16.1: Options' thirdPersonView). */
	static int camera() {
		return Minecraft.getInstance().options.thirdPersonView;
	}

	/** The camera's view, set (0, 1 or 2, as camera() says it). */
	static void setCamera(int view) {
		Minecraft.getInstance().options.thirdPersonView = view;
	}

	/** The creative inventory's screen, as its key opens it. */
	static Screen creativeScreen(Minecraft mc) {
		return new CreativeModeInventoryScreen(mc.player);
	}

	/** The chat's command usage lines (1.16.1 keeps them as text with formatting codes) as plain text. */
	static List<String> usageLines(List<?> lines) {
		List<String> plain = new ArrayList<>();
		for (Object each : lines) {
			plain.add(ChatFormatting.stripFormatting((String) each));
		}
		return plain;
	}

	/** A line sent as the chat sends it (1.16.1's player sends a command as a chat line, slash and all). */
	static void sendChat(ClientPacketListener connection, String text) {
		Minecraft.getInstance().player.chat(text);
	}

	/**
	 * The chat line the hooked chat.line method (Gui.handleChat: its type, the line, its sender) was given; none for
	 * the action bar's (GAME_INFO), which isn't the chat's.
	 */
	static Component chatLine(Object[] arguments) {
		return arguments[0] == ChatType.GAME_INFO ? null : (Component) arguments[1];
	}
}

package io.github.asgerjon.unittas;

import io.github.asgerjon.unittas.probe.Input;
import io.github.asgerjon.unittas.probe.Pictures;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiChat;
import net.minecraft.client.gui.GuiScreen;
import net.minecraft.client.settings.KeyBinding;
import net.minecraft.entity.Entity;
import net.minecraft.entity.player.EntityPlayerMP;
import net.minecraft.item.Item;
import net.minecraft.item.ItemStack;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.EnumDifficulty;
import net.minecraft.world.World;
import net.minecraft.world.WorldServer;

import java.io.File;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.function.Function;

/**
 * A unitTAS test class, in the manner of Python's unittest.TestCase: methods named `test...` are the tests, setUp and
 * tearDown run around each, and the asserts read as unittest's. A test runs on its own thread and drives the real game:
 * steps go to the client or server thread ({@link #onClient}, {@link #onServer}) and come back with their result.
 * Each test starts in creative at the spawn point with an empty inventory and no other entities.
 */
public abstract class TasTestCase {

	/** Thrown by {@link #skipTest}: the test is reported as skipped. */
	public static final class Skip extends RuntimeException {
		Skip(String reason) {
			super(reason);
		}
	}

	private TasGame game;

	final void attach(TasGame game) {
		this.game = game;
	}

	/** Before each test, after the player was put back (see the README for what the reset puts back, and what not). */
	protected void setUp() {
	}

	/** After each test, also when it failed. */
	protected void tearDown() {
	}

	/**
	 * Once before the class's first test, in the class's world (a fresh one, unless the class is {@link SharedWorld})
	 * and after a reset of the player, as unittest's setUpClass. It runs on an instance of its own, so what it makes
	 * for the tests goes in static fields. The reset still runs before every test: what setUpClass leaves must survive
	 * it (blocks, game rules, a mod's state), not entities, items or effects. A failure here is an error and the
	 * class's tests don't run; skipTest here skips them all.
	 */
	protected void setUpClass() {
	}

	/** Once after the class's last test, on an instance of its own; not when setUpClass failed or the run stopped. */
	protected void tearDownClass() {
	}

	/** The world this test runs in, by the number the report gives it: 1 for the run's first, one more for each new. */
	protected final int worldNumber() {
		return game.worldNumber();
	}

	/** How long one test may take before it is stopped as an error. */
	protected int timeoutSeconds() {
		return 60;
	}

	// ---------------------------------------------------------------- the game

	/** Runs the step on the client thread and returns its result. */
	protected final <T> T onClient(Callable<T> step) {
		return game.client(step);
	}

	protected final void onClient(Runnable step) {
		game.client(() -> {
			step.run();
			return null;
		});
	}

	/** Runs the step on the server thread and returns its result. */
	protected final <T> T onServer(Callable<T> step) {
		return game.server(step);
	}

	protected final void onServer(Runnable step) {
		game.server(() -> {
			step.run();
			return null;
		});
	}

	/** Lets the client tick this often (20 a second). */
	protected final void ticks(int ticks) {
		String before = game.doing();
		game.doing("letting " + ticks + " client tick" + (ticks == 1 ? "" : "s") + " pass");
		try {
			game.clientTicks(ticks);
		} finally {
			game.doing(before);
		}
	}

	protected final void serverTicks(int ticks) {
		String before = game.doing();
		game.doing("letting " + ticks + " server tick" + (ticks == 1 ? "" : "s") + " pass");
		try {
			game.serverTicks(ticks);
		} finally {
			game.doing(before);
		}
	}

	/** Checks the condition on the server each tick until it holds; fails after maxTicks. */
	protected final void waitUntil(String what, Callable<Boolean> condition, int maxTicks) {
		String before = game.doing();
		try {
			for (int tick = 0; tick <= maxTicks; tick++) {
				game.doing("waiting for " + what + " (tick " + tick + " of " + maxTicks + ", on the server)");
				if (Boolean.TRUE.equals(game.server(condition))) {
					return;
				}
				game.serverTicks(1);
			}
		} finally {
			game.doing(before);
		}
		throw new AssertionError("waited " + maxTicks + " ticks for " + what);
	}

	/**
	 * Checks the condition on the client each tick until it holds; fails after maxTicks. For what the server changed
	 * and the client must have before the test goes on (an item set with setHeld, before a click that uses it).
	 */
	protected final void waitUntilOnClient(String what, Callable<Boolean> condition, int maxTicks) {
		String before = game.doing();
		try {
			for (int tick = 0; tick <= maxTicks; tick++) {
				game.doing("waiting for " + what + " (tick " + tick + " of " + maxTicks + ", on the client)");
				if (Boolean.TRUE.equals(game.client(condition))) {
					return;
				}
				game.clientTicks(1);
			}
		} finally {
			game.doing(before);
		}
		throw new AssertionError("waited " + maxTicks + " ticks for " + what);
	}

	/** The player on the server side; use inside {@link #onServer} (outside it, the report warns where). */
	protected static EntityPlayerMP player() {
		TasGame.expectServerThread("player()");
		return TasGame.serverPlayer();
	}

	/** The player's world on the server side; use inside {@link #onServer} (outside it, the report warns where). */
	protected static WorldServer world() {
		TasGame.expectServerThread("world()");
		return (WorldServer) TasGame.serverPlayer().worldObj;
	}

	protected static Minecraft mc() {
		return Minecraft.getMinecraft();
	}

	protected final String playerName() {
		return onServer(() -> player().getCommandSenderName());
	}

	// ---------------------------------------------------------------- sounds

	/** Forgets the sounds heard so far in this test (each test starts with none). */
	protected final void clearSounds() {
		UnitTasMode.clearSounds();
	}

	/** The sounds the client played so far in this test, by name ("minecraft:random.bow"), oldest first. */
	protected final List<String> soundsHeard() {
		synchronized (UnitTasMode.SOUNDS_HEARD) {
			return new ArrayList<>(UnitTasMode.SOUNDS_HEARD);
		}
	}

	/**
	 * Waits on the client until the sound has played in this test; fails after maxTicks, naming what was heard, or at
	 * once if the game was asked for it but doesn't have it (it would play nothing).
	 */
	protected final void waitForSound(String sound, int maxTicks) {
		String before = game.doing();
		try {
			for (int tick = 0; tick <= maxTicks; tick++) {
				game.doing("waiting to hear " + sound + " (tick " + tick + " of " + maxTicks + ")");
				if (soundsHeard().contains(sound)) {
					return;
				}
				if (UnitTasMode.SOUNDS_UNKNOWN.contains(sound)) {
					throw new AssertionError(sound + " was played, but the game has no such sound, so nothing is heard"
						+ " (a sound exists only if a sounds.json names it)");
				}
				game.clientTicks(1);
			}
		} finally {
			game.doing(before);
		}
		throw new AssertionError("didn't hear " + sound + " in " + maxTicks + " ticks; heard " + soundsHeard());
	}

	/** The difficulty for this test (each test starts in Easy). */
	protected final void difficulty(EnumDifficulty difficulty) {
		onClient(() -> {
			mc().gameSettings.difficulty = difficulty;
		});
		onServer(() -> {
			for (WorldServer world : MinecraftServer.getServer().worldServers) {
				world.difficultySetting = difficulty;
				world.setAllowedSpawnTypes(difficulty != EnumDifficulty.PEACEFUL, true);
			}
		});
	}

	// ---------------------------------------------------------------- commands and chat

	/**
	 * Runs the command as the player, as the server runs a typed one (modern form first, 1.7.10's after), without the
	 * chat's 256-character limit; waits for the replies to reach the chat.
	 */
	protected final TasCommand command(String text) {
		int mark = game.chatMark();
		int result = game.server(() -> runCommand(text));
		game.clientTicks(3);
		return new TasCommand(text, result, game.chatSince(mark));
	}

	/**
	 * Runs the command as the player, now: for use inside a server step, so its effect can be read in the same tick
	 * (a summoned mob before it takes a step). The replies still go to the chat.
	 */
	protected static int runCommand(String text) {
		TasGame.expectServerThread("runCommand()");
		return MinecraftServer.getServer().getCommandManager().executeCommand(TasGame.serverPlayer(), text);
	}

	/** Where the chat stands now; {@link #chatSince} gives what came after (for messages that no command answered). */
	protected final int chatMark() {
		return game.chatMark();
	}

	/** The chat's lines since the mark, as plain text, oldest first. */
	protected final List<String> chatSince(int mark) {
		List<String> lines = new ArrayList<>();
		for (TasGame.ChatLine line : game.chatSince(mark)) {
			lines.add(line.plain);
		}
		return lines;
	}

	/** Opens the chat and types the text key by key, as a player would; read the suggestions, then enter() or close(). */
	protected final TasChat type(String text) {
		onClient(() -> {
			mc().displayGuiScreen(new GuiChat());
		});
		ticks(1);
		TasChat chat = new TasChat(game);
		chat.typeMore(text);
		return chat;
	}

	/**
	 * Sends GuiScreen.keyTyped to the open screen (dev names first, then the obfuscated ones). What the screen throws
	 * comes out as itself: it is the screen's failure, not unitTAS's.
	 */
	protected static void keyTyped(GuiScreen screen, char character, int keyCode) {
		Input.keyTyped(screen, character, keyCode);
	}

	// ---------------------------------------------------------------- items and entities

	/** A copy of the held stack, or null. */
	protected final ItemStack held() {
		return onServer(() -> ItemStack.copyItemStack(player().getHeldItem()));
	}

	/** Copies of the stacks in the player's main inventory, hotbar first. */
	protected final List<ItemStack> inventory() {
		return onServer(() -> {
			List<ItemStack> stacks = new ArrayList<>();
			for (ItemStack stack : player().inventory.mainInventory) {
				if (stack != null) {
					stacks.add(stack.copy());
				}
			}
			return stacks;
		});
	}

	/** Puts the stack (a copy) in the player's selected hotbar slot; null empties it. */
	protected final void setHeld(ItemStack stack) {
		onServer(() -> {
			player().inventory.setInventorySlotContents(player().inventory.currentItem, ItemStack.copyItemStack(stack));
			player().inventoryContainer.detectAndSendChanges();
		});
	}

	/** Makes the entity at the position and spawns it; returns it, to be read only inside {@link #onServer}. */
	protected final <E extends Entity> E spawn(Function<World, E> make, double x, double y, double z) {
		return onServer(() -> {
			E entity = make.apply(world());
			entity.setLocationAndAngles(x, y, z, 0.0F, 0.0F);
			world().spawnEntityInWorld(entity);
			return entity;
		});
	}

	/** `minecraft:wool:14` (registry name and damage), or `nothing`. */
	protected static String id(ItemStack stack) {
		if (stack == null) {
			return "nothing";
		}
		// getMetadata: the stack's damage value (MCP stable_12's name for it; some environments say getItemDamage)
		return Item.itemRegistry.getNameForObject(stack.getItem()) + ":" + stack.getMetadata();
	}

	/** The entities of the type within the radius of the player; use inside {@link #onServer} (outside it, a warning). */
	@SuppressWarnings("unchecked")
	protected static <E extends Entity> List<E> entitiesNear(Class<E> type, double radius) {
		TasGame.expectServerThread("entitiesNear()");
		EntityPlayerMP player = TasGame.serverPlayer();
		return (List<E>) player.worldObj.getEntitiesWithinAABB(type, player.boundingBox.expand(radius, radius, radius));
	}

	// ---------------------------------------------------------------- input

	/** Turns the player to look this way (degrees; yaw 0 is south, pitch 90 down). */
	protected final void look(float yaw, float pitch) {
		onClient(() -> {
			Input.look(mc(), yaw, pitch);
		});
		ticks(1);
	}

	/** Holds the key down for this many ticks, then lets go. */
	protected final void hold(KeyBinding key, int ticks) {
		onClient(() -> {
			Input.down(key.getKeyCode());
		});
		ticks(ticks);
		onClient(() -> {
			Input.up(key.getKeyCode());
		});
		ticks(1);
	}

	/** Puts the key down and leaves it down (as holding right click to keep a shield raised) until {@link #keyUp}. */
	protected final void keyDown(KeyBinding key) {
		onClient(() -> {
			Input.down(key.getKeyCode());
		});
	}

	protected final void keyUp(KeyBinding key) {
		onClient(() -> {
			Input.up(key.getKeyCode());
		});
	}

	/** The camera: 0 first person, 1 third person from behind, 2 from the front (each test starts in first person). */
	protected final void cameraView(int view) {
		onClient(() -> {
			Input.camera(mc(), view);
		});
		ticks(2);
	}

	/** Presses the key once (down for one tick). */
	protected final void tap(KeyBinding key) {
		hold(key, 1);
	}

	/** This run's results folder (report.txt, screenshots/), for a test that writes a file of its own there. */
	protected final File resultsFolder() {
		return game.request().results;
	}

	// ---------------------------------------------------------------- screenshots

	/** Saves what the screen shows now as screenshots/name.png in the results; returns that path. */
	protected final String screenshot(String name) {
		return screenshot(game, name);
	}

	static String screenshot(TasGame game, String name) {
		// no chat over the view (the reference shots clear theirs too), then two ticks so the frame shows it all
		game.client(() -> {
			clearChat();
			return null;
		});
		game.clientTicks(2);
		String file = name.replaceAll("[^A-Za-z0-9_.-]", "_") + ".png";
		game.client(() -> {
			Minecraft mc = Minecraft.getMinecraft();
			Pictures.save(mc, game.request().results, file);
			return null;
		});
		return "screenshots/" + file;
	}

	/**
	 * Empties the chat's lines. Not clearChatMessages: a mod may cancel that one (to keep the chat between worlds,
	 * say).
	 */
	@SuppressWarnings("rawtypes")
	static void clearChat() {
		Pictures.clearChat(Minecraft.getMinecraft());
	}

	// ---------------------------------------------------------------- asserts, as unittest's

	protected static void assertEqual(Object first, Object second) {
		assertEqual(first, second, null);
	}

	protected static void assertEqual(Object first, Object second, String msg) {
		if (!Objects.equals(first, second)) {
			fail(repr(first) + " != " + repr(second) + lookAlike(first, second), msg);
		}
	}

	protected static void assertNotEqual(Object first, Object second) {
		assertNotEqual(first, second, null);
	}

	protected static void assertNotEqual(Object first, Object second, String msg) {
		if (Objects.equals(first, second)) {
			fail(repr(first) + " == " + repr(second), msg);
		}
	}

	protected static void assertTrue(boolean expr) {
		assertTrue(expr, null);
	}

	protected static void assertTrue(boolean expr, String msg) {
		if (!expr) {
			fail("False is not true", msg);
		}
	}

	protected static void assertFalse(boolean expr) {
		assertFalse(expr, null);
	}

	protected static void assertFalse(boolean expr, String msg) {
		if (expr) {
			fail("True is not false", msg);
		}
	}

	protected static void assertIsNone(Object obj) {
		assertIsNone(obj, null);
	}

	protected static void assertIsNone(Object obj, String msg) {
		if (obj != null) {
			fail(repr(obj) + " is not None", msg);
		}
	}

	protected static void assertIsNotNone(Object obj) {
		assertIsNotNone(obj, null);
	}

	protected static void assertIsNotNone(Object obj, String msg) {
		if (obj == null) {
			fail("unexpectedly None", msg);
		}
	}

	/** The member is in the collection, or (for text) the part is in the text. */
	protected static void assertIn(Object member, Object container) {
		assertIn(member, container, null);
	}

	protected static void assertIn(Object member, Object container, String msg) {
		if (!contains(container, member)) {
			fail(repr(member) + " not found in " + repr(container), msg);
		}
	}

	protected static void assertNotIn(Object member, Object container) {
		assertNotIn(member, container, null);
	}

	protected static void assertNotIn(Object member, Object container, String msg) {
		if (contains(container, member)) {
			fail(repr(member) + " unexpectedly found in " + repr(container), msg);
		}
	}

	protected static void assertGreater(double first, double second) {
		assertGreater(first, second, null);
	}

	protected static void assertGreater(double first, double second, String msg) {
		if (!(first > second)) {
			fail(first + " not greater than " + second, msg);
		}
	}

	/** Within delta of each other. Unlike unittest's, the third argument is that delta, not a number of places. */
	protected static void assertAlmostEqual(double first, double second, double delta) {
		assertAlmostEqual(first, second, delta, null);
	}

	protected static void assertAlmostEqual(double first, double second, double delta, String msg) {
		if (Math.abs(first - second) > delta) {
			fail(first + " != " + second + " within " + delta + " delta", msg);
		}
	}

	/** The command said something containing the text (a success or any other line). */
	protected static void assertSaid(TasCommand command, String part) {
		for (String line : command.lines()) {
			if (line.contains(part)) {
				return;
			}
		}
		fail(repr(part) + " not said by " + command.text() + "; the chat was " + repr(command.lines()), null);
	}

	/** The command answered with a red error containing the text. */
	protected static void assertError(TasCommand command, String part) {
		for (String line : command.errors()) {
			if (line.contains(part)) {
				return;
			}
		}
		fail("no error " + repr(part) + " from " + command.text() + "; the chat was " + repr(command.lines()), null);
	}

	protected static void assertNoError(TasCommand command) {
		if (!command.errors().isEmpty()) {
			fail(command.text() + " failed: " + repr(command.errors()), null);
		}
	}

	protected static void fail(String msg) {
		throw new AssertionError(msg);
	}

	protected static void skipTest(String reason) {
		throw new Skip(reason);
	}

	private static void fail(String standard, String msg) {
		throw new AssertionError(msg == null ? standard : standard + " : " + msg);
	}

	private static boolean contains(Object container, Object member) {
		if (container instanceof String) {
			return member != null && ((String) container).contains(member.toString());
		}
		if (container instanceof Collection<?>) {
			return ((Collection<?>) container).contains(member);
		}
		if (container instanceof Map<?, ?>) {
			return ((Map<?, ?>) container).containsKey(member);
		}
		return false;
	}

	/**
	 * For two values that aren't equal but read the same: why (1 and 1L are of different types; two ItemStacks are
	 * never equal, ItemStack has no equals of its own, so compare id(...) and the stack size instead).
	 */
	private static String lookAlike(Object first, Object second) {
		if (first == null || second == null || !repr(first).equals(repr(second))) {
			return "";
		}
		if (first.getClass() != second.getClass()) {
			return " (a " + first.getClass().getSimpleName() + " and a " + second.getClass().getSimpleName() + ")";
		}
		if (first instanceof ItemStack) {
			return " (ItemStacks are only equal to themselves: compare id(...) and stackSize)";
		}
		return " (two " + first.getClass().getSimpleName() + "s that read the same but aren't equal)";
	}

	/** Python's repr, near enough: strings quoted, lists in brackets. */
	static String repr(Object value) {
		if (value instanceof String) {
			return "'" + value + "'";
		}
		if (value instanceof Collection<?>) {
			List<String> parts = new ArrayList<>();
			for (Object element : (Collection<?>) value) {
				parts.add(repr(element));
			}
			return "[" + String.join(", ", parts) + "]";
		}
		if (value instanceof ItemStack) {
			ItemStack stack = (ItemStack) value;
			return stack.stackSize + "x " + id(stack);
		}
		return String.valueOf(value);
	}
}

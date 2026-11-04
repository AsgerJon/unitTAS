package io.github.asgerjon.unittas;

import net.minecraft.client.gui.GuiScreen;
import net.minecraft.entity.player.EntityPlayerMP;

import java.util.List;

/**
 * A mod's own part of a run, for what unitTAS can't know of the mod: its own settings, its own state of the player,
 * its own chat screen. A class that implements this and is marked {@link TasPlugin} is made at start-up and called
 * at each step below; every method has a default that does nothing, so a mod writes only what it needs.
 */
public interface TasHooks {

	/**
	 * As the run starts, on the client thread: the mod's own settings as its tests expect them (keys held rather than
	 * toggled, say). Keep the player's own settings to put back in {@link #afterRun}.
	 */
	default void beforeRun() {
	}

	/** As the run ends, before the game quits, on the client thread: put back what {@link #beforeRun} changed. */
	default void afterRun() {
	}

	/**
	 * Each time a test world is made (the run's first, and the fresh one each class gets unless it is
	 * {@link SharedWorld}), on the server thread, once its game rules are set and before the class's setUpClass: what
	 * the mod wants in every world its tests run in. Not in save mode, where the saves are what they are.
	 */
	default void setUpWorld() {
	}

	/** Before each test world is closed, and after the run's last test, on the server thread. Not in save mode. */
	default void tearDownWorld() {
	}

	/**
	 * Between tests, on the server thread, after unitTAS has put the player back (creative, an empty inventory, at
	 * the spawn point): whatever the mod keeps of the player besides, as an off-hand slot.
	 */
	default void resetPlayer(EntityPlayerMP player) {
	}

	/** The text in the chat screen's input, or null for 1.7.10's own (GuiChat's input field). On the client thread. */
	default String chatText(GuiScreen chat) {
		return null;
	}

	/**
	 * The suggestions the chat screen shows, or null for 1.7.10's own: the completions the server sent for the last
	 * Tab. On the client thread.
	 */
	default List<String> chatSuggestions(GuiScreen chat) {
		return null;
	}

	/** The line above the chat's input (a command's usage, or its error), or null: 1.7.10's chat has none. */
	default List<String> chatUsage(GuiScreen chat) {
		return null;
	}
}

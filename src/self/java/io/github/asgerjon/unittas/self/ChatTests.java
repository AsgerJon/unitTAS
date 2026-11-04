package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasChat;
import io.github.asgerjon.unittas.TasCommand;
import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;
import org.lwjgl.input.Keyboard;

/**
 * Typing in 1.7.10's own chat screen: TasChat finds GuiChat's input field and the server's tab completions by their
 * types, with no mod's chat hooks in the game.
 */
@TasSuite("self")
public class ChatTests extends TasTestCase {

	/** What was typed key by key is what the input holds. */
	public void testTypedTextIsRead() {
		TasChat chat = type("/time se");
		assertEqual("/time se", chat.text());
		chat.close();
	}

	/** Tab asks the server; its one completion fills the input and is the suggestion. */
	public void testTabCompletesFromTheServer() {
		TasChat chat = type("/tim").key(Keyboard.KEY_TAB);
		assertEqual("/time", chat.text());
		assertIn("/time", chat.suggestions());
		chat.close();
	}

	/** Enter sends the line as a command, and its answer comes back in the chat. */
	public void testEnterRunsTheCommand() {
		TasCommand said = type("/time set 6000").enter();
		assertSaid(said, "Set the time to 6000");
	}
}

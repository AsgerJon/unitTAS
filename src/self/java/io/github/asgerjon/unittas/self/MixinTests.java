package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;
import io.github.asgerjon.unittas.UnitTasMode;
import net.minecraft.client.audio.PositionedSoundRecord;
import net.minecraft.util.ResourceLocation;
import org.lwjgl.input.Mouse;
import org.lwjgl.opengl.Display;

/**
 * unitTAS's own mixins applied in the game: each test shows one mixin a run needs at work. A mixin that didn't apply
 * would have stopped the game already (mixins.unittas.json is required); these show the applied ones do what
 * they're for.
 */
@TasSuite("self")
public class MixinTests extends TasTestCase {

	/** MixinMinecraft: a run's window is titled unitTAS from the start, so a window rule can tell it apart. */
	public void testWindowTitle() {
		assertEqual(UnitTasMode.WINDOW_TITLE, onClient(() -> Display.getTitle()));
	}

	/** MixinMouseHelper: the game never takes the mouse pointer during a run, even when it asks to. */
	public void testPointerLeftFree() {
		onClient(() -> mc().mouseHelper.grabMouseCursor());
		ticks(2);
		assertFalse(onClient(() -> Mouse.isGrabbed()), "the game took the mouse pointer");
	}

	/** MixinSoundHandler: a sound the client plays is heard by name, muted or not. */
	public void testSoundHeard() {
		onClient(() -> mc().getSoundHandler().playSound(
			PositionedSoundRecord.createPositionedSoundRecord(new ResourceLocation("gui.button.press"), 1.0F)));
		waitForSound("minecraft:gui.button.press", 20);
	}
}

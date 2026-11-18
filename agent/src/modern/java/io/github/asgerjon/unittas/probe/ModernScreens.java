package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.PauseScreen;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.client.gui.screens.inventory.CreativeModeInventoryScreen;
import net.minecraft.client.gui.screens.inventory.InventoryScreen;

/**
 * The client's screens (PROTOCOL.md 8.9): the bodies of screen.open and screen.close, a client's alone (SPEC.md 19.7
 * step 10b: apart from the shared bodies, ModernThings, which a dedicated server runs too). Each settles a client tick.
 */
final class ModernScreens {

	private ModernScreens() {
	}

	static void bind(Probe probe) {
		probe.op("screen.open").does(ModernScreens::open).settles(ModernScreens::oneTick);
		probe.op("screen.close").does(ModernScreens::close).settles(ModernScreens::oneTick);
	}

	private static JsonElement oneTick(Call call, JsonElement value) throws ProbeException, InterruptedException {
		return ModernThings.waitClient(call, 1, value);
	}

	private static JsonElement open(Call call) throws ProbeException {
		Minecraft mc = Minecraft.getInstance();
		JsonElement given = call.args.get("screen");
		if (given != null && given.isJsonObject()) {
			Object made = Reflect.make(call, given.getAsJsonObject());
			if (!(made instanceof Screen)) {
				throw ProbeException.badRequest("screen", Members.className(made.getClass()) + " is no screen");
			}
			Version.setScreen((Screen) made);
			return new JsonObject();
		}
		String name = call.string("screen", null);
		if (!"pause".equals(name) && mc.player == null) {
			throw new ProbeException("NotReady", name + " needs a world", null);
		}
		Screen screen;
		if ("chat".equals(name)) {
			screen = Version.chatScreen(call.string("text", ""));
		} else if ("inventory".equals(name)) {
			screen = new InventoryScreen(mc.player);
		} else if ("creative".equals(name)) {
			screen = new CreativeModeInventoryScreen(mc.player, mc.player.connection.enabledFeatures(),
				mc.options.operatorItemsTab().get());
		} else if ("pause".equals(name)) {
			screen = new PauseScreen(true);
		} else {
			throw ProbeException.badRequest("screen", "screen is chat, inventory, creative or pause, not " + name);
		}
		Version.setScreen(screen);
		return new JsonObject();
	}

	/** As Esc closes it: a container's screen through the player's own close, which tells the server too (8.9). */
	private static JsonElement close(Call call) {
		Minecraft mc = Minecraft.getInstance();
		if (Version.screen() instanceof AbstractContainerScreen && mc.player != null) {
			mc.player.closeContainer();
		} else {
			Version.setScreen(null);
		}
		return new JsonObject();
	}
}

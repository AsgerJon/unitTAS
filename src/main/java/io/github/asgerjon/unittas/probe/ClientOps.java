package io.github.asgerjon.unittas.probe;

import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiChat;
import net.minecraft.client.gui.GuiScreen;
import net.minecraft.client.gui.inventory.GuiContainer;

/**
 * The bodies of the operations that need the client's classes, given at preInit (they are declared, without them, when
 * the probe starts, before any Minecraft class may be touched). Each runs on the client thread.
 */
final class ClientOps {

	private ClientOps() {
	}

	static void bind(Probe probe) {
		probe.op("screen.get").does(call -> {
			GuiScreen screen = Minecraft.getMinecraft().currentScreen;
			if (screen == null) {
				return null;
			}
			return Json.object(
				"class", screen.getClass().getName(),
				"chat", screen instanceof GuiChat,
				"container", screen instanceof GuiContainer,
				"pauses", screen.doesGuiPauseGame());
		});
	}
}

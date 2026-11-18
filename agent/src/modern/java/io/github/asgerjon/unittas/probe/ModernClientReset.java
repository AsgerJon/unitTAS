package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.CameraType;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;

/**
 * The reset's client part (PROTOCOL.md 8.4, 9.5), a client's alone (SPEC.md 19.7 step 10b): the body of client.reset,
 * apart from the server's parts (ModernReset), which a dedicated server's probe runs too.
 */
final class ModernClientReset {

	private ModernClientReset() {
	}

	static void bind(Probe probe) {
		probe.op("client.reset").does(ModernClientReset::reset).settles((call, value) ->
			ModernThings.waitClient(call, call.number("settle_ticks", 3, 0, 1200), value));
	}

	/** client.reset: no screen, no keys held, the first hotbar slot, first person, the HUD shown; no rain on the client. */
	private static JsonElement reset(Call call) throws ProbeException {
		Minecraft mc = Minecraft.getInstance();
		if (mc.player == null || mc.level == null) {
			throw new ProbeException("NotReady", "client.reset needs a world: the client has no player",
				Json.object("state", call.probe.snapshot.state));
		}
		if (Version.screen() != null) {
			Version.setScreen(null);
		}
		KeyMapping.releaseAll();
		// the first hotbar slot, so a given item is the held one
		VersionCommon.selectSlot(mc.player.getInventory(), 0);
		mc.options.setCameraType(CameraType.FIRST_PERSON);
		if (Version.hudHidden()) {
			Version.toggleHud();
		}
		// the client's own rain and thunder, to match the server's clear weather (code on the client asks it)
		mc.level.setRainLevel(0.0F);
		mc.level.setThunderLevel(0.0F);
		return new JsonObject();
	}
}

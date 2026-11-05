package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.TasPlugins;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.Minecraft;
import net.minecraft.entity.player.EntityPlayerMP;

import java.util.List;

/**
 * The reset's three operations (PROTOCOL.md 8.4), given at preInit; unittas.reset runs them in 9.5's order. Their
 * parts are Reset's, the Java runner's too.
 */
final class ResetOps {

	private ResetOps() {
	}

	static void bind(Probe probe) {
		probe.op("client.reset").does(ResetOps::client).settles((call, value) -> {
			long ticks = call.number("settle_ticks", 3, 0, 1200);
			try {
				Sides.get().waitTicks(Side.CLIENT, ticks, Sides.STALL_SECONDS);
			} catch (Sides.Stalled stalled) {
				throw Ops.stalled(call.probe, stalled);
			}
			return value;
		});
		probe.op("player.reset").does(ResetOps::player);
		probe.op("world.reset").does(call -> {
			Reset.world();
			return new JsonObject();
		});
	}

	/** client.reset: the client's part and its own weather, safe to run twice (9.5 does). */
	private static JsonElement client(Call call) throws ProbeException {
		Minecraft mc = Minecraft.getMinecraft();
		if (mc.thePlayer == null) {
			throw new ProbeException("NotReady", "client.reset needs a world: the client has no player",
				Json.object("state", call.probe.snapshot.state));
		}
		Reset.client(mc);
		Reset.clientWeather(mc);
		return new JsonObject();
	}

	/**
	 * player.reset: a player outside the overworld is brought back first, and that is all the call does (it answers
	 * respawned, and is called again once the client has arrived). Otherwise the player's part, then the mods'
	 * resetPlayer, unless "hooks": "after" leaves them to the caller.
	 */
	private static JsonElement player(Call call) throws ProbeException {
		EntityPlayerMP player = GameOps.serverPlayer(call, call.string("player", null));
		if (Reset.respawnIfAway(player)) {
			return Json.object("respawned", true);
		}
		double[] at = {Reset.START_X, Reset.START_Y, Reset.START_Z};
		if (call.has("at")) {
			JsonElement given = call.args.get("at");
			if (!given.isJsonArray() || given.getAsJsonArray().size() != 3) {
				throw ProbeException.badRequest("at", "at is [x, y, z]");
			}
			for (int i = 0; i < 3; i++) {
				at[i] = given.getAsJsonArray().get(i).getAsDouble();
			}
		}
		JsonObject look = call.object("look");
		float yaw = look != null && look.has("yaw") ? look.get("yaw").getAsFloat() : 0.0F;
		float pitch = look != null && look.has("pitch") ? look.get("pitch").getAsFloat() : 0.0F;
		String hooks = call.string("hooks", "now");
		if (!hooks.equals("now") && !hooks.equals("after")) {
			throw ProbeException.badRequest("hooks", "hooks is now or after, not " + hooks);
		}
		Reset.player(player, at[0], at[1], at[2], yaw, pitch);
		if (hooks.equals("now")) {
			List<Object[]> outcomes = TasPlugins.run(each -> each.resetPlayer(player));
			for (Object[] outcome : outcomes) {
				Throwable thrown = (Throwable) outcome[1];
				if (thrown != null) {
					throw new ProbeException("GameError", outcome[0] + ".resetPlayer threw " + thrown + ": the player isn't"
						+ " fully reset", Json.object("plugin", outcome[0], "exception", thrown.getClass().getName(),
						"trace", Probe.trace(thrown)));
				}
			}
		}
		return Json.object("respawned", false);
	}
}

package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.Difficulty;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.List;

/**
 * The reset in 26.3 (PROTOCOL.md 8.4, 9.5; README's "What tests share"), as 1.7.10's Reset and ServerReset have it,
 * by 26.3's calls and with its own parts: the off hand (cleared with the rest), the hidden HUD, the camera type. Its
 * server's two operations, which unittas.reset runs in 9.5's order with the client's (ModernClientReset): no client
 * class (SPEC.md 19.7 step 10b), as a dedicated server's probe runs them too.
 */
final class ModernReset {

	/** Where the player starts: on 26.3's flat world's grass (its surface y -61), at the spawn. */
	static final double START_X = 0.5;
	static final double START_Y = -60.0;
	static final double START_Z = 0.5;

	private ModernReset() {
	}

	static void bind(Probe probe) {
		probe.op("player.reset").does(ModernReset::player);
		probe.op("world.reset").does(call -> {
			world(ModernServer.get());
			return new JsonObject();
		});
	}

	/**
	 * player.reset: a player outside the overworld is brought back first, and that is all the call does (it answers
	 * respawned, and is called again once the client has arrived). Otherwise the player's part. 26.3 has no plugins
	 * of its own yet, so "hooks" ("now" or "after") is checked and there are no resetPlayer hooks to run.
	 */
	private static JsonElement player(Call call) throws ProbeException {
		ServerPlayer player = ModernThings.serverPlayer(call.string("player", null));
		String hooks = call.string("hooks", "now");
		if (!hooks.equals("now") && !hooks.equals("after")) {
			throw ProbeException.badRequest("hooks", "hooks is now or after, not " + hooks);
		}
		double[] at = {START_X, START_Y, START_Z};
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
		MinecraftServer server = ModernServer.get();
		if (VersionCommon.levelOf(player).dimension() != Level.OVERWORLD) {
			// back to the overworld, where the reset puts it; the client arrives some ticks later
			VersionCommon.teleport(player, server.overworld(), at[0], at[1], at[2], yaw, pitch);
			return Json.object("respawned", true);
		}
		reset(player, at[0], at[1], at[2], yaw, pitch);
		return Json.object("respawned", false);
	}

	/** The player's part, on the server thread, for a player in the overworld. */
	static void reset(ServerPlayer player, double x, double y, double z, float yaw, float pitch) {
		// the client's container, not only its screen: the close packet makes the client close it, as Esc does
		player.closeContainer();
		// out of a bed an earlier test left the player in, and no bed of its to respawn at
		if (player.isSleeping()) {
			player.stopSleepInBed(true, true);
		}
		VersionCommon.clearRespawn(player);
		// the first hotbar slot on the server too, as on the client, and told to it: set on one side only, the two
		// disagree on what is held
		VersionCommon.selectSlot(VersionCommon.inventory(player), 0);
		VersionCommon.sendHeldSlot(player, 0);
		// everything held: the main slots, the armour and the off hand, and the cursor's stack
		VersionCommon.inventory(player).clearContent();
		VersionCommon.setCarried(player, ItemStack.EMPTY);
		player.stopUsingItem();
		player.inventoryMenu.broadcastChanges();
		VersionCommon.sendInventory(player);
		player.removeAllEffects();
		// arrows and stingers from earlier tests stay drawn stuck in the player, over what the next test's shots show
		player.setArrowCount(0);
		player.setStingerCount(0);
		// its world's own game mode (creative in the run's test world, survival in a survival world or save): a class's
		// world in survival keeps a survival player through the reset (found by meantwell on 26.3)
		player.setGameMode(VersionCommon.level(player).getServer().getWorldData().getGameType());
		// creative keeps the player flying if it was
		VersionCommon.abilities(player).flying = false;
		player.onUpdateAbilities();
		player.setExperienceLevels(0);
		player.setExperiencePoints(0);
		player.totalExperience = 0;
		player.clearFire();
		player.setHealth(player.getMaxHealth());
		player.getFoodData().setFoodLevel(20);
		VersionCommon.setSaturation(player, 20.0F);
		VersionCommon.resetFall(player);
		player.stopRiding();
		player.setDeltaMovement(Vec3.ZERO);
		player.connection.teleport(x, y, z, yaw, pitch);
	}

	/**
	 * Every dimension's part, on the server thread: Easy, no entities but players (a lightning bolt is one in 26.3),
	 * clear weather held: tests that want weather set it themselves.
	 */
	static void world(MinecraftServer server) {
		server.setDifficulty(Difficulty.EASY, true);
		for (ServerLevel level : server.getAllLevels()) {
			List<Entity> others = new ArrayList<>();
			for (Entity each : level.getAllEntities()) {
				if (!(each instanceof Player)) {
					others.add(each);
				}
			}
			for (Entity each : others) {
				VersionCommon.discard(each);
			}
		}
		VersionCommon.serverWorlds().setWeather(false, false, true);
	}
}

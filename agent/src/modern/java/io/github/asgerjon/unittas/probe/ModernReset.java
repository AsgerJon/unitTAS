package io.github.asgerjon.unittas.probe;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.asgerjon.unittas.probe.link.Json;
import net.minecraft.client.CameraType;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.Difficulty;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.GameType;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.List;

/**
 * The reset in 26.3 (PROTOCOL.md 8.4, 9.5; README's "What tests share"), as 1.7.10's Reset and ServerReset have it,
 * by 26.3's calls and with its own parts: the off hand (cleared with the rest), the hidden HUD, the camera type. Its
 * three operations, which unittas.reset runs in 9.5's order.
 */
final class ModernReset {

	/** Where the player starts: on 26.3's flat world's grass (its surface y -61), at the spawn. */
	static final double START_X = 0.5;
	static final double START_Y = -60.0;
	static final double START_Z = 0.5;

	private ModernReset() {
	}

	static void bind(Probe probe) {
		probe.op("client.reset").does(ModernReset::client).settles((call, value) ->
			ModernThings.waitClient(call, call.number("settle_ticks", 3, 0, 1200), value));
		probe.op("player.reset").does(ModernReset::player);
		probe.op("world.reset").does(call -> {
			world(ModernThings.server());
			return new JsonObject();
		});
	}

	/** client.reset: no screen, no keys held, the first hotbar slot, first person, the HUD shown; no rain on the client. */
	private static JsonElement client(Call call) throws ProbeException {
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
		Version.selectSlot(mc.player.getInventory(), 0);
		mc.options.setCameraType(CameraType.FIRST_PERSON);
		if (Version.hudHidden()) {
			Version.toggleHud();
		}
		// the client's own rain and thunder, to match the server's clear weather (code on the client asks it)
		mc.level.setRainLevel(0.0F);
		mc.level.setThunderLevel(0.0F);
		return new JsonObject();
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
		MinecraftServer server = ModernThings.server();
		if (player.level().dimension() != Level.OVERWORLD) {
			// back to the overworld, where the reset puts it; the client arrives some ticks later
			Version.teleport(player, server.overworld(), at[0], at[1], at[2], yaw, pitch);
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
		Version.clearRespawn(player);
		// the first hotbar slot on the server too, as on the client, and told to it: set on one side only, the two
		// disagree on what is held
		Version.selectSlot(player.getInventory(), 0);
		Version.sendHeldSlot(player, 0);
		// everything held: the main slots, the armour and the off hand, and the cursor's stack
		player.getInventory().clearContent();
		player.containerMenu.setCarried(ItemStack.EMPTY);
		player.stopUsingItem();
		player.inventoryMenu.broadcastChanges();
		player.inventoryMenu.sendAllDataToRemote();
		player.removeAllEffects();
		// arrows and stingers from earlier tests stay drawn stuck in the player, over what the next test's shots show
		player.setArrowCount(0);
		player.setStingerCount(0);
		player.setGameMode(GameType.CREATIVE);
		// creative keeps the player flying if it was
		player.getAbilities().flying = false;
		player.onUpdateAbilities();
		player.setExperienceLevels(0);
		player.setExperiencePoints(0);
		player.totalExperience = 0;
		player.clearFire();
		player.setHealth(player.getMaxHealth());
		player.getFoodData().setFoodLevel(20);
		player.getFoodData().setSaturation(20.0F);
		player.resetFallDistance();
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
				each.discard();
			}
		}
		Version.worlds().setWeather(false, false, true);
	}
}
